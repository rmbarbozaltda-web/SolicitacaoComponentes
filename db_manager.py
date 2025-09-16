import sqlite3
import pandas as pd
import datetime
import streamlit as st

# Detecta ambiente do Streamlit Cloud (você pode adicionar essa verificação)
import os
is_streamlit_cloud = os.environ.get('IS_STREAMLIT_CLOUD', False)

if not is_streamlit_cloud:
    try:
        import pyodbc
    except ImportError:
        # Fallback quando pyodbc não está disponível
        st.warning("pyodbc não disponível, usando implementação alternativa")
        # Classe simulada ou alternativa
        class PyodbcMock:
            # Implementar métodos necessários que simulam pyodbc
            pass
        pyodbc = PyodbcMock()

from database import get_protheus_connection # Importa a função de conexão com Protheus

DB_LOCAL = 'garantia.db'

# --- Funções para interagir com o banco de dados local (SQLite) ---
def get_db_connection():
    """Retorna uma conexão com o banco de dados SQLite local."""
    conn = sqlite3.connect(DB_LOCAL)
    conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
    return conn

def log_historico(solicitacao_id, usuario, acao, detalhes=""):
    """Registra uma ação no histórico da solicitação."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO historico (solicitacao_id, timestamp, usuario, acao, detalhes) VALUES (?, ?, ?, ?, ?)",
            (solicitacao_id, timestamp, usuario, acao, detalhes)
        )
        conn.commit()

def setup_centros_custo_gestores():
    """
    Cria a tabela de centros de custo e seus gestores responsáveis.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Verificar se a tabela já existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='centros_custo'")
        if not cursor.fetchone():
            cursor.execute("""
            CREATE TABLE centros_custo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL,
                setor TEXT NOT NULL,
                gestor TEXT NOT NULL,
                gestor_email TEXT
            )
            """)
            
            # Inserir os centros de custo iniciais
            cursor.executemany(
                "INSERT INTO centros_custo (codigo, setor, gestor, gestor_email) VALUES (?, ?, ?, ?)",
                [
                    ('040023', 'Garantia', 'gestor.garantia', 'gestor.garantia@empresa.com'),
                    ('040031', 'Assistência', 'gestor.assistencia', 'gestor.assistencia@empresa.com'),
                    ('040024', 'Instalações', 'gestor.instalacoes', 'gestor.instalacoes@empresa.com'),
                ]
            )
            
            conn.commit()
            print("Tabela de centros de custo criada e populada com sucesso.")
        
        # Adicionar coluna centro_custo à tabela solicitacoes, se não existir
        cursor.execute("PRAGMA table_info(solicitacoes)")
        colunas = [info[1] for info in cursor.fetchall()]
        
        if 'centro_custo' not in colunas:
            cursor.execute("ALTER TABLE solicitacoes ADD COLUMN centro_custo TEXT")
            cursor.execute("ALTER TABLE solicitacoes ADD COLUMN setor TEXT")
            conn.commit()
            print("Colunas 'centro_custo' e 'setor' adicionadas à tabela 'solicitacoes'")

def get_centros_custo():
    """Retorna todos os centros de custo disponíveis."""
    try:
        with get_db_connection() as conn:
            query = "SELECT * FROM centros_custo ORDER BY setor"
            df = pd.read_sql_query(query, conn)
            
            # Debug: verifica se obtivemos resultados
            if df.empty:
                print("Aviso: Nenhum centro de custo encontrado no banco de dados.")
            else:
                print(f"Encontrados {len(df)} centros de custo.")
                
            return df
    except Exception as e:
        print(f"Erro ao recuperar centros de custo: {str(e)}")
        # Em vez de retornar DataFrame vazio, lança exceção para debug
        raise

def verificar_e_reconfigurar_centros_custo():
    """
    Verifica se a tabela de centros de custo está corretamente configurada e
    reconfigura se necessário.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verifica se a tabela existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='centros_custo'")
            if not cursor.fetchone():
                print("A tabela centros_custo não existe. Criando...")
                cursor.execute("""
                CREATE TABLE centros_custo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL,
                    setor TEXT NOT NULL,
                    gestor TEXT NOT NULL,
                    gestor_email TEXT
                )
                """)
            
            # Verifica se há dados na tabela
            cursor.execute("SELECT COUNT(*) FROM centros_custo")
            count = cursor.fetchone()[0]
            
            if count == 0:
                print("A tabela centros_custo está vazia. Inserindo dados padrão...")
                # Use os nomes de usuário que correspondem aos seus gestores em auth.py
                cursor.executemany(
                    "INSERT INTO centros_custo (codigo, setor, gestor, gestor_email) VALUES (?, ?, ?, ?)",
                    [
                        ('040023', 'Garantia', 'rafael.barboza', 'rafael.barboza@empresa.com'),
                        ('040031', 'Assistência', 'adriana.masini', 'adriana.masini@empresa.com'),
                        ('040024', 'Instalações', 'gestor.instalacoes', 'gestor.instalacoes@empresa.com'),
                    ]
                )
                conn.commit()
                print("Dados inseridos com sucesso na tabela centros_custo.")
            
            # Mostra os centros de custo configurados
            cursor.execute("SELECT * FROM centros_custo")
            centros = cursor.fetchall()
            print("Centros de custo configurados:")
            for centro in centros:
                print(f"  {centro}")
                
            return True
    except Exception as e:
        print(f"Erro ao verificar/reconfigurar centros de custo: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def get_gestor_by_centro_custo(centro_custo):
    """Retorna o gestor responsável pelo centro de custo especificado."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT gestor, gestor_email FROM centros_custo WHERE codigo = ?",
            (centro_custo,)
        )
        result = cursor.fetchone()
        return {'gestor': result[0], 'email': result[1]} if result else None

def get_solicitacoes_pendentes_aprovacao_by_gestor(gestor):
    """
    Retorna solicitações pendentes de aprovação para um gestor específico,
    baseado no centro de custo associado ao gestor.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Primeiro, obtemos o(s) centro(s) de custo que este gestor gerencia
        cursor.execute("""
            SELECT codigo FROM centros_custo 
            WHERE gestor = ?
        """, (gestor,))
        
        centros_custo = [row[0] for row in cursor.fetchall()]
        
        # Se não encontrarmos centros de custo para este gestor,
        # verificamos se ele é um gestor do tipo antigo
        if not centros_custo:
            # Para gestores antigos, retornamos todas as solicitações pendentes
            # que não têm centro_custo específico
            query = """
            SELECT * FROM solicitacoes 
            WHERE status_atual = 'Pendente Aprovação'
            AND (centro_custo IS NULL OR centro_custo = '')
            ORDER BY data_criacao DESC
            """
            return pd.read_sql_query(query, conn)
        
        # Se há centros de custo associados, filtramos por eles
        placeholders = ', '.join(['?' for _ in centros_custo])
        query = f"""
        SELECT * FROM solicitacoes 
        WHERE status_atual = 'Pendente Aprovação'
        AND centro_custo IN ({placeholders})
        ORDER BY data_criacao DESC
        """
        
        return pd.read_sql_query(query, conn, params=centros_custo)
    
def diagnostico_centros_custo():
    """
    Função de diagnóstico para verificar a configuração de centros de custo.
    
    Returns:
    --------
    pandas.DataFrame ou str:
        DataFrame contendo os dados da tabela centros_custo, ou
        string de erro se ocorrer algum problema.
    """
    try:
        with get_db_connection() as conn:
            # Verifica se a tabela existe
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='centros_custo'")
            if not cursor.fetchone():
                return "Tabela centros_custo não existe."
            
            # Obtém os dados da tabela centros_custo
            query = "SELECT * FROM centros_custo"
            df_centros = pd.read_sql_query(query, conn)
            
            # Verifica se há dados na tabela
            if df_centros.empty:
                return "A tabela centros_custo existe, mas não contém registros."
                
            # Obtém dados adicionais para diagnóstico
            
            # 1. Verifica quais gestores têm solicitações pendentes
            query_solicitacoes = """
            SELECT centro_custo, COUNT(*) as num_solicitacoes
            FROM solicitacoes
            WHERE status_atual = 'Pendente Aprovação'
            GROUP BY centro_custo
            """
            df_solicitacoes = pd.read_sql_query(query_solicitacoes, conn)
            
            # 2. Verifica todos os usuários com permissões de gestor no auth module
            # Isto será feito em outra função, verificar_usuarios_gestores()
            
            return {
                "centros_custo": df_centros,
                "solicitacoes_por_centro": df_solicitacoes
            }
    
    except Exception as e:
        import traceback
        return f"Erro ao verificar centros de custo: {str(e)}\n{traceback.format_exc()}"


def verificar_usuarios_gestores():
    """
    Verifica se os usuários gestores no módulo auth correspondem 
    aos gestores na tabela centros_custo.
    
    Returns:
    --------
    dict:
        Dicionário contendo listas de gestores do banco e do auth,
        além de listas de inconsistências.
    """
    try:
        import auth  # Importe o módulo de autenticação
        
        with get_db_connection() as conn:
            query = "SELECT codigo, setor, gestor FROM centros_custo"
            df_gestores = pd.read_sql_query(query, conn)
            
            if df_gestores.empty:
                return {"erro": "Não há gestores cadastrados na tabela centros_custo"}
            
            gestores_db = df_gestores.to_dict('records')
            
            # Obter gestores do módulo auth
            gestores_auth = []
            for username, user_info in auth.USERS.items():
                if user_info.get("role", "") in ["Gestor Garantia", "Gestor Assistencia", "Gestor Instalacoes"]:
                    gestores_auth.append({
                        "username": username,
                        "role": user_info.get("role", ""),
                        "email": user_info.get("email", "Não definido")
                    })
            
            # Verificar se todos os gestores do DB estão em auth
            gestores_db_usernames = [g['gestor'] for g in gestores_db]
            gestores_auth_usernames = [g['username'] for g in gestores_auth]
            
            missing_in_auth = [g for g in gestores_db_usernames if g not in gestores_auth_usernames]
            missing_in_db = [g for g in gestores_auth_usernames if g not in gestores_db_usernames]
            
            return {
                "gestores_db": gestores_db,
                "gestores_auth": gestores_auth,
                "missing_in_auth": missing_in_auth,
                "missing_in_db": missing_in_db
            }
    
    except Exception as e:
        import traceback
        return {"erro": f"Erro ao verificar gestores: {str(e)}\n{traceback.format_exc()}"}

def get_clientes_pedidos_equipamentos():
    """
    Busca clientes, pedidos e equipamentos da tabela 'pedidos_info' no DB local.
    Retorna um DataFrame com os dados necessários para os dropdowns.
    """
    with get_db_connection() as conn:
        query = """
        SELECT DISTINCT
            "CNPJ/CPF" AS cliente_cnpj_cpf,
            "Nome/Razão Social" AS cliente_nome_razao,
            "Data Venda" AS data_venda,
            "Nº PDV" AS numero_pdv,
            "SKU Protheus" AS equipamento_sku,
            "Descrição do Produto" AS equipamento_descricao
        FROM pedidos_info
        ORDER BY "Nome/Razão Social", "Data Venda" DESC, "Nº PDV";
        """
        df = pd.read_sql_query(query, conn)
        return df
    
def adicionar_campo_observacoes():
    """Adiciona o campo observacoes à tabela itens_solicitacao se ele não existir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Verifica se a coluna já existe
        cursor.execute("PRAGMA table_info(itens_solicitacao)")
        colunas = [info[1] for info in cursor.fetchall()]
        
        if 'observacoes' not in colunas:
            cursor.execute("ALTER TABLE itens_solicitacao ADD COLUMN observacoes TEXT")
            conn.commit()
            print("Campo 'observacoes' adicionado à tabela 'itens_solicitacao'")
        else:
            print("O campo 'observacoes' já existe na tabela 'itens_solicitacao'")

# Execute uma vez na importação para garantir que o campo exista
adicionar_campo_observacoes()    

def get_componentes_by_sku_protheus(equipamento_sku):
    """
    Busca os componentes (BOM) de um equipamento específico no Protheus (tabela SG1010),
    incluindo subcomponentes para itens que começam com E ou S.
    
    equipamento_sku: O SKU (código) do equipamento pai.
    Retorna um DataFrame com os componentes, suas descrições, quantidades, níveis e relações.
    """
    conn_protheus = None
    try:
        conn_protheus = get_protheus_connection()
        if not conn_protheus:
            st.error("Falha ao conectar ao Protheus para buscar componentes.")
            return pd.DataFrame()
        
        # 1. Query para componentes de nível 1 (diretos do equipamento)
        query_nivel1 = f"""
        SELECT
            SG1.G1_COMP AS Componente,
            SB1.B1_DESC AS Descricao_Componente,
            SG1.G1_QUANT AS Quantidade,
            SB1.B1_UM AS Unidade_Medida,
            1 AS Nivel,
            '{equipamento_sku}' AS Pai_Componente
        FROM
            SG1010 SG1
        INNER JOIN
            SB1010 SB1 ON SG1.G1_COMP = SB1.B1_COD AND SB1.D_E_L_E_T_ = ''
        WHERE
            SG1.G1_COD = '{equipamento_sku}'
            AND SG1.D_E_L_E_T_ = ''
        ORDER BY
            SG1.G1_COMP
        """
        
        df_nivel1 = pd.read_sql_query(query_nivel1, conn_protheus)
        
        # Se não encontrou componentes de nível 1, retorna DataFrame vazio
        if df_nivel1.empty:
            return pd.DataFrame()
        
        # Inicializa o DataFrame final com os componentes de nível 1
        df_componentes = df_nivel1.copy()
        
        # 2. Para cada componente de nível 1 que começa com 'E' ou 'S', busca subcomponentes de nível 2
        for idx, row in df_nivel1.iterrows():
            componente = row['Componente']
            if componente.startswith('E') or componente.startswith('S'):
                query_nivel2 = f"""
                SELECT
                    SG1.G1_COMP AS Componente,
                    SB1.B1_DESC AS Descricao_Componente,
                    SG1.G1_QUANT AS Quantidade,
                    SB1.B1_UM AS Unidade_Medida,
                    2 AS Nivel,
                    '{componente}' AS Pai_Componente
                FROM
                    SG1010 SG1
                INNER JOIN
                    SB1010 SB1 ON SG1.G1_COMP = SB1.B1_COD AND SB1.D_E_L_E_T_ = ''
                WHERE
                    SG1.G1_COD = '{componente}'
                    AND SG1.D_E_L_E_T_ = ''
                ORDER BY
                    SG1.G1_COMP
                """
                
                df_nivel2 = pd.read_sql_query(query_nivel2, conn_protheus)
                
                # Adiciona os componentes de nível 2 ao DataFrame final
                if not df_nivel2.empty:
                    df_componentes = pd.concat([df_componentes, df_nivel2], ignore_index=True)
                    
                    # 3. Para cada componente de nível 2 que começa com 'E' ou 'S', busca subcomponentes de nível 3
                    for idx2, row2 in df_nivel2.iterrows():
                        componente2 = row2['Componente']
                        if componente2.startswith('E') or componente2.startswith('S'):
                            query_nivel3 = f"""
                            SELECT
                                SG1.G1_COMP AS Componente,
                                SB1.B1_DESC AS Descricao_Componente,
                                SG1.G1_QUANT AS Quantidade,
                                SB1.B1_UM AS Unidade_Medida,
                                3 AS Nivel,
                                '{componente2}' AS Pai_Componente
                            FROM
                                SG1010 SG1
                            INNER JOIN
                                SB1010 SB1 ON SG1.G1_COMP = SB1.B1_COD AND SB1.D_E_L_E_T_ = ''
                            WHERE
                                SG1.G1_COD = '{componente2}'
                                AND SG1.D_E_L_E_T_ = ''
                            ORDER BY
                                SG1.G1_COMP
                            """
                            
                            df_nivel3 = pd.read_sql_query(query_nivel3, conn_protheus)
                            
                            # Adiciona os componentes de nível 3 ao DataFrame final
                            if not df_nivel3.empty:
                                df_componentes = pd.concat([df_componentes, df_nivel3], ignore_index=True)
        
        return df_componentes
    
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        if sqlstate == '42S02':
            st.error(f"Erro no Protheus: Tabela SG1010 ou SB1010 não encontrada. Detalhes: {ex}")
        elif sqlstate == '42S22':
            st.error(f"Erro no Protheus: Coluna inválida na query de componentes. Verifique os nomes das colunas. Detalhes: {ex}")
        else:
            st.error(f"Erro ao buscar componentes no Protheus: {ex}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao buscar componentes no Protheus: {e}")
        return pd.DataFrame()
    finally:
        # A conexão do Protheus é gerenciada por st.cache_resource (em database.py), não precisa fechar aqui
        pass

def get_estoque_componentes(components_list=None):
    """
    Busca informações de estoque dos componentes.
    Parameters:
    -----------
    components_list : list, optional
        Lista de códigos de componentes a serem consultados.
        Se None, retorna informações de todos os componentes.
    Returns:
    --------
    pandas.DataFrame
        DataFrame com informações de estoque dos componentes
    """
    try:
        # Obtenha a conexão Protheus
        conn_protheus = get_protheus_connection()
        if not conn_protheus:
            st.error("Falha ao conectar ao Protheus para buscar informações de estoque.")
            return pd.DataFrame()
            
        query = """
        SELECT
            B1.B1_COD AS Codigo,
            B1.B1_DESC AS Descricao,
            COALESCE(B2.B2_QATU, 0) AS Quantidade_Atual,
            COALESCE(B2.B2_QEMP, 0) AS Quantidade_Empenhada,
            COALESCE(B2.B2_RESERVA, 0) AS Quantidade_Reservada,
            COALESCE(B2.B2_QATU, 0) - COALESCE(B2.B2_QEMP, 0) - COALESCE(B2.B2_RESERVA, 0) AS Saldo_Disponivel,
            B2.B2_LOCAL AS Armazem,
            FORN_PRINC.A2_NOME AS Nome_Fornecedor,
            PROD_FORN.A5_NOMPROD AS Descricao_Produto_Fornecedor,
            ULT_PED.C7_DATPRF AS Previsao_Entrega_Ultimo_Pedido
        FROM
            SB1010 B1
            LEFT JOIN SB2010 B2 ON B1.B1_COD = B2.B2_COD
                               AND B2.D_E_L_E_T_ = ' '
            LEFT JOIN (
                SELECT
                    A5_PRODUTO,
                    A5_FORNECE,
                    A5_LOJA,
                    A5_CODPRF,
                    A5_NOMPROD,
                    ROW_NUMBER() OVER (PARTITION BY A5_PRODUTO ORDER BY A5_FORNECE) AS rn
                FROM
                    SA5010
                WHERE
                    D_E_L_E_T_ = ' '
                GROUP BY
                    A5_PRODUTO, A5_FORNECE, A5_LOJA, A5_CODPRF, A5_NOMPROD
            ) PROD_FORN ON B1.B1_COD = PROD_FORN.A5_PRODUTO AND PROD_FORN.rn = 1
            LEFT JOIN SA2010 FORN_PRINC ON PROD_FORN.A5_FORNECE = FORN_PRINC.A2_COD
                                       AND PROD_FORN.A5_LOJA = FORN_PRINC.A2_LOJA
                                       AND FORN_PRINC.D_E_L_E_T_ = ' '
            LEFT JOIN (
                SELECT
                    C7_PRODUTO,
                    C7_NUM,
                    C7_EMISSAO,
                    C7_DATPRF,
                    ROW_NUMBER() OVER (PARTITION BY C7_PRODUTO ORDER BY C7_EMISSAO DESC, C7_NUM DESC) AS rn
                FROM
                    SC7010
                WHERE
                    D_E_L_E_T_ = ' '
                    AND C7_RESIDUO <> 'S'
            ) ULT_PED ON B1.B1_COD = ULT_PED.C7_PRODUTO AND ULT_PED.rn = 1
        WHERE
            B1.D_E_L_E_T_ = ' '
        """
        
        # Se houver uma lista específica de componentes, filtra por eles
        if components_list and len(components_list) > 0:
            # Sanitiza os valores da lista para evitar SQL injection
            components_str = "', '".join([comp.replace("'", "''") for comp in components_list])
            query += f" AND B1.B1_COD IN ('{components_str}')"
            
        df_estoque = pd.read_sql(query, conn_protheus)
        
        # O problema está aqui: a conexão não está sendo fechada corretamente
        # Não fechar conexão que é gerenciada pelo st.cache_resource
        
        return df_estoque
    except Exception as e:
        st.error(f"Erro ao obter estoque de componentes: {str(e)}")
        return pd.DataFrame()  # Retorna DataFrame vazio em caso de erro

def criar_solicitacao(solicitante, solicitante_email, cliente_cnpj, cliente_nome, pedido_venda,
                      equipamento_sku, equipamento_nome, itens_solicitados, centro_custo=None, setor=None,
                      email_sender_module=None, app_base_url=None):
    """
    Cria uma nova solicitação e seus itens no banco de dados.
    Retorna o ID da nova solicitação.
    
    Parameters:
    -----------
    solicitante : str
        Nome do usuário que está criando a solicitação.
    solicitante_email : str
        E-mail do solicitante.
    cliente_cnpj : str
        CNPJ do cliente.
    cliente_nome : str
        Nome do cliente.
    pedido_venda : str
        Número do pedido de venda.
    equipamento_sku : str
        SKU do equipamento.
    equipamento_nome : str
        Nome do equipamento.
    itens_solicitados : list
        Lista de dicionários contendo informações dos itens solicitados.
    centro_custo : str, optional
        Código do centro de custo.
    setor : str, optional
        Nome do setor.
    email_sender_module : module, optional
        Módulo para envio de e-mails (passado como parâmetro para evitar importação circular).
    app_base_url : str, optional
        URL base do aplicativo (passada como parâmetro para evitar importação circular).
    
    Returns:
    --------
    int
        ID da solicitação criada.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        data_criacao = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status_inicial = 'Pendente Aprovação'
        
        # Verifica se há itens sem estoque suficiente
        tem_itens_sem_estoque = any(
            not item.get('tem_estoque', True)
            for item in itens_solicitados
        )
        
        # Se fornecido um centro de custo, busca o setor correspondente
        if centro_custo and not setor:
            cursor.execute("SELECT setor FROM centros_custo WHERE codigo = ?", (centro_custo,))
            result = cursor.fetchone()
            if result:
                setor = result[0]
        
        cursor.execute(
            """
            INSERT INTO solicitacoes (
                data_criacao, solicitante, solicitante_email, cliente_cnpj, cliente_nome,
                pedido_venda, equipamento_sku, equipamento_nome, status_atual, data_ultimo_status,
                centro_custo, setor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data_criacao, solicitante, solicitante_email, cliente_cnpj, cliente_nome,
                pedido_venda, equipamento_sku, equipamento_nome, status_inicial, data_criacao,
                centro_custo, setor
            )
        )
        solicitacao_id = cursor.lastrowid
        
        for item in itens_solicitados:
            # Verifica informações de estoque do item
            tem_estoque = item.get('tem_estoque', True) # Default para True se não estiver presente
            saldo_disponivel = item.get('saldo_disponivel', 0) # Default para 0 se não estiver presente
            
            # Define observações com base no status de estoque
            observacoes = None
            if not tem_estoque:
                observacoes = f"Produto sem estoque suficiente. Saldo disponível: {saldo_disponivel}"
            
            cursor.execute(
                """
                INSERT INTO itens_solicitacao (
                    solicitacao_id, componente_sku, componente_desc, quantidade_solicitada, observacoes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (solicitacao_id, item['sku'], item['descricao'], item['quantidade'], observacoes)
            )
        
        conn.commit()
        
        # Adiciona log com informação sobre itens sem estoque
        log_msg = f"Status inicial: {status_inicial}"
        if tem_itens_sem_estoque:
            log_msg += ". ATENÇÃO: Solicitação contém itens sem estoque suficiente."
        
        log_historico(solicitacao_id, solicitante, 'Solicitação Criada', log_msg)
        
        # Preparar dados para o e-mail, se os módulos necessários foram fornecidos
        if email_sender_module is not None and app_base_url is not None:
            try:
                # Preparar informações para o e-mail
                solicitacao_info = {
                    'id': solicitacao_id,
                    'data_criacao': data_criacao,
                    'solicitante': solicitante,
                    'solicitante_email': solicitante_email,
                    'cliente_cnpj': cliente_cnpj,
                    'cliente_nome': cliente_nome,
                    'pedido_venda': pedido_venda,
                    'equipamento_sku': equipamento_sku,
                    'equipamento_nome': equipamento_nome,
                    'centro_custo': centro_custo,
                    'setor': setor
                }
                
                # Enviar e-mail para o gestor correspondente
                email_sent = email_sender_module.send_email_to_gestor(
                    solicitacao_id,
                    solicitacao_info,
                    itens_solicitados,
                    app_base_url
                )
                
                if not email_sent:
                    # Registra o problema no log, mas não interrompe o processo
                    log_historico(
                        solicitacao_id,
                        solicitante,
                        'Aviso',
                        "Não foi possível enviar e-mail de notificação ao gestor responsável."
                    )
                else:
                    log_historico(
                        solicitacao_id,
                        solicitante,
                        'Notificação',
                        f"E-mail enviado ao gestor responsável pelo centro de custo {centro_custo}."
                    )
            except Exception as e:
                # Registra a exceção no log
                log_historico(
                    solicitacao_id,
                    solicitante,
                    'Erro',
                    f"Erro ao tentar enviar e-mail para o gestor: {str(e)}"
                )
        elif centro_custo:
            # Se temos centro de custo mas não podemos enviar e-mail, registramos isso
            log_historico(
                solicitacao_id,
                solicitante,
                'Aviso',
                "Módulo de e-mail não fornecido. Não foi possível notificar o gestor responsável."
            )
        
        # Retorna o ID da solicitação criada
        return solicitacao_id


def get_solicitacoes_pendentes_aprovacao():
    """Retorna todas as solicitações com status 'Pendente Aprovação'."""
    with get_db_connection() as conn:
        query = """
        SELECT * FROM solicitacoes WHERE status_atual = 'Pendente Aprovação' ORDER BY data_criacao DESC
        """
        return pd.read_sql_query(query, conn)

def get_solicitacoes_aprovadas_pendentes_liberacao():
    """Retorna todas as solicitações com status 'Aprovada' (pendentes de liberação do almoxarifado)."""
    with get_db_connection() as conn:
        query = """
        SELECT * FROM solicitacoes WHERE status_atual = 'Aprovada' ORDER BY data_aprovacao DESC
        """
        return pd.read_sql_query(query, conn)

def get_solicitacoes_pendentes_retirada():
    """Retorna todas as solicitações com status 'Disponível para Retirada'."""
    with get_db_connection() as conn:
        query = """
        SELECT * FROM solicitacoes WHERE status_atual = 'Disponível para Retirada' ORDER BY data_liberacao DESC
        """
        return pd.read_sql_query(query, conn)

def get_solicitacoes_pendentes_devolucao_almoxarifado():
    """Retorna todas as solicitações com status 'Devolução Pendente Almoxarifado'."""
    with get_db_connection() as conn:
        query = """
        SELECT * FROM solicitacoes WHERE status_atual = 'Devolução Pendente Almoxarifado' ORDER BY data_devolucao_solicitada DESC
        """
        return pd.read_sql_query(query, conn)

def get_solicitacao_by_id(solicitacao_id):
    """Retorna uma solicitação específica pelo ID."""
    with get_db_connection() as conn:
        query = "SELECT * FROM solicitacoes WHERE id = ?"
        df = pd.read_sql_query(query, conn, params=(solicitacao_id,))
        return df.iloc[0].to_dict() if not df.empty else None

def get_itens_solicitacao(solicitacao_id):
    """Retorna os itens de uma solicitação específica."""
    with get_db_connection() as conn:
        query = "SELECT * FROM itens_solicitacao WHERE solicitacao_id = ?"
        return pd.read_sql_query(query, conn, params=(solicitacao_id,))

def get_historico_solicitacao(solicitacao_id):
    """Retorna o histórico de uma solicitação específica."""
    with get_db_connection() as conn:
        query = "SELECT * FROM historico WHERE solicitacao_id = ? ORDER BY timestamp ASC"
        return pd.read_sql_query(query, conn, params=(solicitacao_id,))
    
def get_solicitacoes_para_confirmar_retirada(solicitante=None):
    """
    Retorna solicitações no status 'Aguardando Retirada' ou 'Retirada Parcial'
    para confirmação de retirada.
    Pode ser filtrado por solicitante.
    """
    with get_db_connection() as conn:
        query = """
            SELECT
                s.id,
                s.data_criacao,
                s.solicitante,
                s.cliente_nome,
                s.pedido_venda,
                s.equipamento_nome,
                s.status_atual,
                s.data_ultimo_status
            FROM solicitacoes s
            WHERE s.status_atual IN ('Aguardando Retirada', 'Retirada Parcial')
        """
        params = []
        if solicitante:
            query += " AND s.solicitante = ?"
            params.append(solicitante)

        query += " ORDER BY s.data_criacao DESC"
        return pd.read_sql_query(query, conn, params=params)

def confirmar_retirada(solicitacao_id, user_confirming, itens_retirados_info):
    """
    Confirma a retirada de itens de uma solicitação, atualiza o status
    e registra no histórico.
    Verifica se o user_confirming é o solicitante da solicitação.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Obter informações da solicitação e verificar autoria
        cursor.execute("SELECT solicitante, status_atual FROM solicitacoes WHERE id = ?", (solicitacao_id,))
        solicitacao_data = cursor.fetchone()

        if not solicitacao_data:
            st.error(f"Solicitação com ID {solicitacao_id} não encontrada.")
            return False

        solicitante_original = solicitacao_data[0]
        status_atual = solicitacao_data[1]

        # VERIFICAÇÃO DE AUTORIA: Apenas o solicitante original pode confirmar retirada
        if user_confirming != solicitante_original:
            st.error(f"Permissão negada: Somente o solicitante '{solicitante_original}' pode confirmar a retirada desta solicitação.")
            return False # Retorna False para indicar falha na operação

        # 2. Obter itens da solicitação
        # Usamos 'componente_sku' aqui pois é o nome da coluna no seu 'itens_solicitacao'
        cursor.execute("SELECT id, componente_sku, quantidade_solicitada, quantidade_retirada FROM itens_solicitacao WHERE solicitacao_id = ?", (solicitacao_id,))
        itens_db = cursor.fetchall()
        itens_db_map = {item[1]: {'id': item[0], 'solicitada': item[2], 'retirada': item[3]} for item in itens_db}

        total_itens_solicitados = 0
        total_itens_retirados_apos_confirmacao = 0 # Soma das quantidades já retiradas + as que serão retiradas agora

        # Primeiro, calcule o total de itens solicitados para a validação do status final
        for item_db in itens_db:
            total_itens_solicitados += item_db[2] # quantidade_solicitada

        for item_info in itens_retirados_info:
            item_protheus = item_info['item_protheus'] # Usamos 'item_protheus' do input, que mapeia para 'componente_sku'
            quantidade_retirada_agora = item_info['quantidade_retirada']

            if item_protheus in itens_db_map:
                item_db = itens_db_map[item_protheus]
                nova_quantidade_retirada = item_db['retirada'] + quantidade_retirada_agora

                # Validação: Não pode retirar mais do que o solicitado
                if nova_quantidade_retirada > item_db['solicitada']:
                    st.error(f"Erro: Quantidade retirada para o item '{item_protheus}' excede a quantidade solicitada ({item_db['solicitada']}).")
                    return False

                # Atualiza a quantidade retirada no banco de dados
                cursor.execute(
                    "UPDATE itens_solicitacao SET quantidade_retirada = ? WHERE id = ?",
                    (nova_quantidade_retirada, item_db['id'])
                )
                # Atualiza o total de itens retirados para verificar o status da solicitação
                # Subtraímos a quantidade que já estava retirada e adicionamos a nova total
                total_itens_retirados_apos_confirmacao += nova_quantidade_retirada
            else:
                st.warning(f"Item '{item_protheus}' não encontrado na solicitação {solicitacao_id}. Ignorando.")


        # 3. Atualizar status da solicitação
        novo_status = ""
        # Recalcular o total_itens_retirados_apos_confirmacao com base nos itens atualizados
        # Isso é importante caso alguns itens não tenham sido passados em itens_retirados_info
        cursor.execute("SELECT SUM(quantidade_retirada) FROM itens_solicitacao WHERE solicitacao_id = ?", (solicitacao_id,))
        current_total_retirado = cursor.fetchone()[0] or 0

        if current_total_retirado == 0:
            novo_status = "Aguardando Retirada" # Se nada foi retirado ainda
        elif current_total_retirado < total_itens_solicitados:
            novo_status = "Retirada Parcial"
        else:
            novo_status = "Retirada Concluída"

        # Apenas atualiza o status se ele realmente mudou
        if novo_status != status_atual:
            cursor.execute(
                "UPDATE solicitacoes SET status_atual = ?, data_ultimo_status = ? WHERE id = ?",
                (novo_status, datetime.datetime.now(), solicitacao_id)
            )
            # 4. Registrar no histórico
            log_historico(solicitacao_id, user_confirming, f"Retirada de itens confirmada. Novo status: {novo_status}")
        else:
             log_historico(solicitacao_id, user_confirming, f"Retirada de itens confirmada. Status permaneceu: {novo_status}")


        conn.commit()
        return True # Retorna True para indicar sucesso

def update_status_solicitacao(solicitacao_id, novo_status, usuario, detalhes_historico="", **kwargs):
    """
    Atualiza o status de uma solicitação e registra no histórico.
    kwargs pode incluir aprovador, data_aprovacao, motivo_rejeicao, etc.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        data_atual = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        set_clauses = [f"status_atual = '{novo_status}'", f"data_ultimo_status = '{data_atual}'"]
        params = []
        for key, value in kwargs.items():
            if value is not None: # Apenas adiciona se o valor não for None
                set_clauses.append(f"{key} = ?")
                params.append(value)
            else: # Se for None, podemos querer setar a coluna para NULL
                set_clauses.append(f"{key} = NULL")
        query = f"UPDATE solicitacoes SET {', '.join(set_clauses)} WHERE id = ?"
        params.append(solicitacao_id)
        cursor.execute(query, tuple(params))
        conn.commit()
        log_historico(solicitacao_id, usuario, f"Status alterado para: {novo_status}", detalhes_historico)

def update_itens_solicitacao_liberacao(solicitacao_id, itens_liberados, usuario):
    """Atualiza as quantidades liberadas para os itens de uma solicitação."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for item in itens_liberados:
            cursor.execute(
                """
                UPDATE itens_solicitacao
                SET quantidade_liberada = ?
                WHERE id = ? AND solicitacao_id = ?
                """,
                (item['quantidade_liberada'], item['id'], solicitacao_id)
            )
        conn.commit()
        log_historico(solicitacao_id, usuario, "Itens Liberados", "Quantidades liberadas pelo almoxarifado atualizadas.")

def update_itens_solicitacao_retirada(solicitacao_id, usuario):
    """
    Atualiza as quantidades retiradas para os itens de uma solicitação,
    assumindo que a quantidade retirada é igual à quantidade liberada.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE itens_solicitacao
            SET quantidade_retirada = quantidade_liberada
            WHERE solicitacao_id = ?
            """,
            (solicitacao_id,)
        )
        conn.commit()
        log_historico(solicitacao_id, usuario, "Itens Retirados", "Quantidades retiradas confirmadas pelo solicitante.")

def update_itens_solicitacao_devolucao(solicitacao_id, itens_devolvidos, usuario):
    """
    Atualiza as quantidades devolvidas para os itens de uma solicitação.
    Este é o registro inicial da devolução pelo solicitante.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for item in itens_devolvidos:
            cursor.execute(
                """
                UPDATE itens_solicitacao
                SET quantidade_devolvida = ?
                WHERE id = ? AND solicitacao_id = ?
                """,
                (item['quantidade_devolvida'], item['id'], solicitacao_id)
            )
        conn.commit()
        log_historico(solicitacao_id, usuario, "Devolução Solicitada", "Solicitante registrou componentes para devolução.")

def confirm_itens_solicitacao_devolucao_almoxarifado(solicitacao_id, usuario):
    """
    Confirma a devolução dos itens pelo almoxarifado.
    Neste ponto, a quantidade devolvida já foi registrada pelo solicitante,
    o almoxarifado apenas confirma o processo.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Não há atualização de quantidade aqui, apenas a confirmação do processo
        # A quantidade_devolvida já foi setada pelo solicitante
        conn.commit() # Apenas commit para garantir que o log seja salvo
        log_historico(solicitacao_id, usuario, "Devolução Confirmada (Almoxarifado)", "Almoxarifado confirmou o recebimento dos componentes devolvidos.")

def get_all_solicitacoes():
    """Retorna todas as solicitações para o histórico geral."""
    with get_db_connection() as conn:
        query = "SELECT * FROM solicitacoes ORDER BY data_criacao DESC"
        return pd.read_sql_query(query, conn)
    
def get_all_historico():
    """Retorna todo o histórico de todas as solicitações."""
    with get_db_connection() as conn:
        query = "SELECT * FROM historico ORDER BY timestamp ASC"
        return pd.read_sql_query(query, conn)
    
def get_all_itens_solicitacao():
    """
    Retorna todos os itens de solicitação com detalhes da solicitação para montar
    um relatório consolidado de peças.
    """
    with get_db_connection() as conn:
        query = """
        SELECT 
            i.id as item_id,
            i.solicitacao_id,
            i.componente_sku,
            i.componente_desc,
            i.quantidade_solicitada,
            i.quantidade_liberada,
            i.quantidade_retirada,
            i.quantidade_devolvida,
            s.data_criacao,
            s.solicitante,
            s.cliente_nome,
            s.pedido_venda,
            s.equipamento_sku,
            s.equipamento_nome,
            s.status_atual,
            s.data_aprovacao,
            s.data_liberacao,
            s.data_retirada,
            s.data_devolucao_confirmada,
            s.data_finalizacao
        FROM 
            itens_solicitacao i
        LEFT JOIN 
            solicitacoes s ON i.solicitacao_id = s.id
        ORDER BY 
            s.data_criacao DESC, i.componente_sku
        """
        return pd.read_sql_query(query, conn)

# Teste de conexão com o DB local (opcional, para depuração)
if __name__ == '__main__':
    # Garante que o DB local e as tabelas estejam criadas/atualizadas
    from gerar_base_pedidos import inicializar_e_migrar_db
    inicializar_e_migrar_db()
    print("Testando get_clientes_pedidos_equipamentos...")
    df_info = get_clientes_pedidos_equipamentos()
    if not df_info.empty:
        print(f"Clientes/Pedidos/Equipamentos encontrados: {len(df_info)}")
        print(df_info.head())
    else:
        print("Nenhum cliente/pedido/equipamento encontrado. Certifique-se de que gerar_base_pedidos.py foi executado.")

    # Exemplo de como buscar componentes (requer um SKU Protheus válido no seu Protheus)
    # Substitua 'SEU_SKU_PROTHEUS_AQUI' por um SKU real para testar
    print("\nTestando get_componentes_by_sku_protheus...")
    sample_sku = "SEU_SKU_PROTHEUS_AQUI" # <<<<<<< ATUALIZE COM UM SKU REAL DO SEU PROTHEUS
    df_componentes = get_componentes_by_sku_protheus(sample_sku)
    if not df_componentes.empty:
        print(f"Componentes para {sample_sku}:")
        print(df_componentes.head())
    else:
        print(f"Nenhum componente encontrado para {sample_sku} ou erro na conexão/query. Verifique o SKU e as configurações do Protheus.")
    print("\nTestes básicos do db_manager concluídos.")


