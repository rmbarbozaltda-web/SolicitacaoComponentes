import pyodbc
import pandas as pd
from tqdm import tqdm
import time
import sqlite3
from decimal import Decimal
import datetime # Importado para usar datas

DB_LOCAL = 'garantia.db'

def inicializar_e_migrar_db():
    """
    Garante que o banco de dados SQLite e todas as tabelas necessárias existam.
    Também aplica migrações, como adicionar novas colunas a tabelas existentes,
    para manter o schema compatível com a aplicação.
    """
    print("Verificando e inicializando a estrutura do banco de dados local...")
    with sqlite3.connect(DB_LOCAL) as conn:
        cursor = conn.cursor()
        # 1. Garante que todas as tabelas do sistema existam
        print(" -> Criando tabelas, se não existirem...")
        # Tabela principal de solicitações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS solicitacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_criacao TEXT,
                solicitante TEXT,
                solicitante_email TEXT,
                cliente_cnpj TEXT,
                cliente_nome TEXT,
                pedido_venda TEXT,
                equipamento_sku TEXT,
                equipamento_nome TEXT,
                status_atual TEXT, -- Novo: 'Pendente Aprovação', 'Aprovada', 'Rejeitada', 'Disponível para Retirada', 'Não Disponível', 'Retirada Confirmada', 'Devolução Pendente Almoxarifado', 'Devolução Concluída', 'Finalizada'
                data_ultimo_status TEXT,
                aprovador TEXT, -- Novo: Usuário que aprovou/rejeitou
                data_aprovacao TEXT, -- Novo: Data da aprovação/rejeição
                motivo_rejeicao TEXT, -- Novo: Motivo se a solicitação foi rejeitada
                almoxarife_liberacao TEXT, -- Novo: Usuário do almoxarifado que liberou
                data_liberacao TEXT, -- Novo: Data da liberação pelo almoxarifado
                motivo_nao_disponivel TEXT, -- Novo: Motivo se o almoxarifado não pôde separar
                retirado_por TEXT,
                data_retirada TEXT, -- Novo: Data da confirmação de retirada pelo solicitante
                data_devolucao_solicitada TEXT, -- Novo: Data em que o solicitante registrou a devolução
                data_devolucao_confirmada TEXT, -- Novo: Data em que o almoxarifado confirmou a devolução
                almoxarife_devolucao_confirmacao TEXT, -- Novo: Usuário do almoxarifado que confirmou a devolução
                data_finalizacao TEXT -- Novo: Data de finalização do processo
            )
        ''')
        # Tabela com os itens de cada solicitação
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS itens_solicitacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao_id INTEGER,
                componente_sku TEXT,
                componente_desc TEXT,
                quantidade_solicitada INTEGER,
                quantidade_liberada INTEGER DEFAULT 0, -- Novo: Quantidade separada pelo almoxarifado
                quantidade_retirada INTEGER DEFAULT 0, -- Novo: Quantidade efetivamente retirada
                quantidade_devolvida INTEGER DEFAULT 0, -- Quantidade devolvida pelo solicitante
                FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes (id)
            )
        ''')
        # Tabela de histórico para auditoria completa
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao_id INTEGER,
                timestamp TEXT,
                usuario TEXT,
                acao TEXT,
                detalhes TEXT,
                FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes (id)
            )
        ''')
        # 2. Lógica de Migração: Adiciona colunas se elas não existirem
        print(" -> Verificando a necessidade de migrações na tabela 'solicitacoes'...")
        cursor.execute("PRAGMA table_info(solicitacoes)")
        colunas_existentes_solicitacoes = [info[1] for info in cursor.fetchall()]
        novas_colunas_solicitacoes = [
            ('solicitante_email', 'TEXT'), ('retirado_por', 'TEXT'),
            ('status_aprovacao', 'TEXT'), ('aprovador', 'TEXT'), ('data_aprovacao', 'TEXT'),
            ('motivo_rejeicao', 'TEXT'), ('almoxarife_liberacao', 'TEXT'), ('data_liberacao', 'TEXT'),
            ('motivo_nao_disponivel', 'TEXT'), ('data_retirada', 'TEXT'),
            ('data_devolucao_solicitada', 'TEXT'), ('data_devolucao_confirmada', 'TEXT'),
            ('almoxarife_devolucao_confirmacao', 'TEXT'), ('data_finalizacao', 'TEXT')
        ]
        for col_name, col_type in novas_colunas_solicitacoes:
            if col_name not in colunas_existentes_solicitacoes:
                print(f" -> Adicionando coluna '{col_name}' na tabela 'solicitacoes'...")
                cursor.execute(f"ALTER TABLE solicitacoes ADD COLUMN {col_name} {col_type};")
        print(" -> Verificando a necessidade de migrações na tabela 'itens_solicitacao'...")
        cursor.execute("PRAGMA table_info(itens_solicitacao)")
        colunas_existentes_itens = [info[1] for info in cursor.fetchall()]
        novas_colunas_itens = [
            ('quantidade_liberada', 'INTEGER DEFAULT 0'),
            ('quantidade_retirada', 'INTEGER DEFAULT 0')
        ]
        for col_name, col_type in novas_colunas_itens:
            if col_name not in colunas_existentes_itens:
                print(f" -> Adicionando coluna '{col_name}' na tabela 'itens_solicitacao'...")
                cursor.execute(f"ALTER TABLE itens_solicitacao ADD COLUMN {col_name} {col_type};")
        conn.commit()
    
    # 3. Configuração da tabela de centros de custo e gestores
    print(" -> Configurando tabela de centros de custo e gestores...")
    import db_manager  # Importamos aqui para usar a função
    db_manager.setup_centros_custo_gestores()  # Chamada para configurar a tabela de centros de custo
    
    print("Estrutura do banco de dados verificada e atualizada com sucesso.")


# O restante da função gerar_base_completa e o if __name__ == '__main__': permanecem os mesmos
# Certifique-se de que a função inicializar_e_migrar_db() é chamada antes de qualquer operação no DB local.
# O código abaixo é o que você já tinha, apenas re-incluído para contexto.

def gerar_base_completa():
    """
    Executa a lógica de busca nos bancos de dados Protheus e DTS,
    processa os dados e salva o resultado em uma tabela no banco de dados local SQLite.
    """
    # Passo 0: Garante que a estrutura do DB local está correta ANTES de tudo.
    inicializar_e_migrar_db()
    print("\nIniciando a geração da base de dados de pedidos...")
    # Conexão 1 - PROTHEUS_PRODUCAO
    try:
        conn1 = pyodbc.connect(
            'DRIVER={ODBC Driver 18 for SQL Server};'
            'SERVER=192.168.3.205;'
            'DATABASE=PROTHEUS_PRODUCAO;'
            'UID=almoxarifado;'
            'PWD=almoxarifado;'
            'TrustServerCertificate=yes;'
        )
        print("Conexão com PROTHEUS bem-sucedida.")
    except Exception as e:
        print(f"Falha ao conectar no PROTHEUS: {e}")
        return
    # Conexão 2 - TOPEMA_PRD (DTS)
    try:
        conn2 = pyodbc.connect(
            'DRIVER={ODBC Driver 18 for SQL Server};'
            'SERVER=177.136.226.250;'
            'DATABASE=TOPEMA_PRD;'
            'UID=TOPEMA_DR;'
            'PWD=T0p_X9iF*^@C~$;'
            'TrustServerCertificate=yes;'
        )
        print("Conexão com DTS bem-sucedida.")
    except Exception as e:
        print(f"Falha ao conectar no DTS: {e}")
        conn1.close()
        return
    inicio = time.time()
    print("Iniciando extração de pedidos do Protheus...")
    # 1. Pegando os pedidos únicos do Protheus
    df_pedidos = pd.read_sql_query("SELECT DISTINCT C5_NUM AS NumeroPedido FROM SC5010 WHERE D_E_L_E_T_ = ''", conn1)
    print(f"Encontrados {len(df_pedidos)} pedidos únicos.")
    resultados = []
    # 2. Para cada pedido, executa a procedure no DTS
    for numero in tqdm(df_pedidos['NumeroPedido'], desc='Processando pedidos no DTS', unit='pedido'):
        try:
            with conn2.cursor() as cursor2:
                # Adaptação para garantir que o numero seja string, se necessário pela procedure
                cursor2.execute("EXEC XSP_0044_DTS_PedidosVendasInfo @CD_PEDIDOVENDA = ?", str(numero))
                columns = [column[0] for column in cursor2.description]
                rows = cursor2.fetchall()
                for row in rows:
                    resultados.append(dict(zip(columns, row)))
        except Exception as e:
            print(f"\nErro ao processar pedido {numero}: {e}")
            continue
    conn1.close()
    conn2.close()
    print("Conexões com Protheus e DTS fechadas.")
    if not resultados:
        print("Nenhum resultado foi retornado pela procedure. Encerrando.")
        return
    df_resultado = pd.DataFrame(resultados)
    df_resultado.drop_duplicates(inplace=True)
    # --- AJUSTE DE TIPOS DE DADOS ---
    print("Ajustando tipos de dados para compatibilidade com SQLite...")
    for col in df_resultado.columns:
        if any(isinstance(x, Decimal) for x in df_resultado[col].dropna()):
            df_resultado[col] = df_resultado[col].astype(float)
    # Salva o resultado em uma tabela 'pedidos_info' no nosso banco local
    try:
        with sqlite3.connect(DB_LOCAL) as conn_local:
            # Usamos 'replace' para que cada execução apague a tabela antiga e crie uma nova
            df_resultado.to_sql('pedidos_info', conn_local, if_exists='replace', index=False)
        fim = time.time()
        print("\n----------------------------------------------------")
        print(f"SUCESSO! Base de dados 'pedidos_info' atualizada em {DB_LOCAL}.")
        print(f"Total de {len(df_resultado)} registros salvos.")
        print(f"Tempo total de execução: {round(fim - inicio, 2)} segundos.")
        print("----------------------------------------------------")
    except Exception as e:
        print(f"\nERRO ao salvar os dados no banco local SQLite: {e}")

if __name__ == '__main__':
    gerar_base_completa()

