import pyodbc
import streamlit as st

# Função para criar e retornar uma conexão com o banco de dados Protheus
@st.cache_resource
def get_protheus_connection():
    """
    Cria e retorna uma conexão com o banco de dados Protheus (interno).
    As credenciais são baseadas nos scripts funcionais fornecidos.
    """
    try:
        connection_string = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            "SERVER=192.168.3.205;"  # <-- CORRIGIDO: IP do script funcional
            "DATABASE=PROTHEUS_PRODUCAO;" # <-- CORRIGIDO: Nome do banco do script funcional
            "UID=almoxarifado;"           # <-- CORRIGIDO: Usuário do script funcional
            "PWD=almoxarifado;"           # <-- CORRIGIDO: Senha do script funcional
            "TrustServerCertificate=yes;" # <-- ADICIONADO: Parâmetro essencial que faltava
            "Encrypt=yes;"                # Adicionado para consistência com o script funcional
        )
        conn = pyodbc.connect(connection_string, timeout=30)
        print("Conexão com PROTHEUS (interno) bem-sucedida!")
        return conn
    except pyodbc.Error as ex:
        print(f"Erro ao conectar ao PROTHEUS (interno): {ex}")
        # Exibe o erro no Streamlit e para a execução
        st.error(f"Falha na conexão com o banco de dados Protheus (interno). Verifique o console para detalhes. Erro: {ex}")
        st.stop()
    except Exception as e:
        print(f"Um erro inesperado ocorreu na conexão com PROTHEUS: {e}")
        st.error(f"Um erro inesperado ocorreu na conexão com o Protheus. Detalhes: {e}")
        st.stop()

# Função para criar e retornar uma conexão com o banco de dados DTS
@st.cache_resource
def get_dts_connection():
    """
    Cria e retorna uma conexão com o banco de dados DTS (externo).
    """
    try:
        connection_string = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            "SERVER=177.136.226.250;"
            "DATABASE=TOPEMA_PRD;"
            "UID=TOPEMA_DR;"
            "PWD=T0p_X9iF*^@C~$;"
            "TrustServerCertificate=yes;" # Adicionado para consistência
        )
        conn = pyodbc.connect(connection_string, timeout=30)
        print("Conexão com DTS (externo) bem-sucedida!")
        return conn
    except pyodbc.Error as ex:
        print(f"Erro ao conectar ao DTS (externo): {ex}")
        # Exibe o erro no Streamlit e para a execução
        st.error(f"Falha na conexão com o banco de dados DTS (externo). Verifique o console para detalhes. Erro: {ex}")
        st.stop()
    except Exception as e:
        print(f"Um erro inesperado ocorreu na conexão com DTS: {e}")
        st.error(f"Um erro inesperado ocorreu na conexão com o DTS. Detalhes: {e}")
        st.stop()

# Função para testar as conexões ao iniciar o app
def test_connections():
    print("Testando conexão com PROTHEUS (interno)...")
    protheus_conn = get_protheus_connection()
    if protheus_conn:
        # Não precisa fechar aqui, o cache_resource gerencia
        pass

    print("\nTestando conexão com DTS (externo)...")
    dts_conn = get_dts_connection()
    if dts_conn:
        # Não precisa fechar aqui, o cache_resource gerencia
        pass







