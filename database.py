import streamlit as st
import os

# Verifica se estamos executando no Streamlit Cloud
is_streamlit_cloud = os.environ.get('STREAMLIT_SHARING', False) or 'streamlit.app' in os.environ.get('HOSTNAME', '')

# Tenta importar pyodbc apenas se não estiver no Streamlit Cloud
if not is_streamlit_cloud:
    try:
        import pyodbc
    except ImportError:
        st.warning("pyodbc não disponível, usando implementação alternativa")

# Classe para simular uma conexão de banco de dados no Streamlit Cloud
class MockConnection:
    def __init__(self, db_name):
        self.db_name = db_name
        print(f"Usando conexão simulada para {db_name}")
    
    def cursor(self):
        return MockCursor(self.db_name)
    
    def commit(self):
        print(f"Mock commit em {self.db_name}")
        pass
    
    def close(self):
        print(f"Mock close em {self.db_name}")
        pass
    
    def execute(self, query):
        print(f"Mock execute em {self.db_name}: {query}")
        return MockCursor(self.db_name)

class MockCursor:
    def __init__(self, db_name):
        self.db_name = db_name
    
    def execute(self, query, params=None):
        # Registra a query para debug
        print(f"Simulando execução no {self.db_name}: {query}")
        if params:
            print(f"Parâmetros: {params}")
        return self
    
    def fetchall(self):
        if self.db_name == "PROTHEUS_PRODUCAO":
            # Dados simulados para Protheus
            return [("B1_COD1", "Produto 1", 10), ("B1_COD2", "Produto 2", 20)]
        else:
            # Dados simulados para DTS
            return [("DTS_COD1", "DTS Item 1", 15), ("DTS_COD2", "DTS Item 2", 25)]
    
    def fetchone(self):
        if self.db_name == "PROTHEUS_PRODUCAO":
            return ("B1_COD1", "Produto 1", 10)
        else:
            return ("DTS_COD1", "DTS Item 1", 15)
    
    def close(self):
        print(f"Fechando cursor simulado para {self.db_name}")

# Função para criar e retornar uma conexão com o banco de dados Protheus
@st.cache_resource
def get_protheus_connection():
    """
    Cria e retorna uma conexão com o banco de dados Protheus (interno).
    As credenciais são baseadas nos scripts funcionais fornecidos.
    """
    if is_streamlit_cloud:
        st.warning("Executando em ambiente Streamlit Cloud: usando conexão simulada para Protheus")
        return MockConnection("PROTHEUS_PRODUCAO")
    
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
    except Exception as e:
        print(f"Erro ao conectar ao PROTHEUS (interno): {e}")
        # Exibe o erro no Streamlit e para a execução
        st.error(f"Falha na conexão com o banco de dados Protheus (interno). Verifique o console para detalhes. Erro: {e}")
        if not is_streamlit_cloud:
            st.stop()
        else:
            st.warning("Usando conexão simulada como fallback")
            return MockConnection("PROTHEUS_PRODUCAO")

# Função para criar e retornar uma conexão com o banco de dados DTS
@st.cache_resource
def get_dts_connection():
    """
    Cria e retorna uma conexão com o banco de dados DTS (externo).
    """
    if is_streamlit_cloud:
        st.warning("Executando em ambiente Streamlit Cloud: usando conexão simulada para DTS")
        return MockConnection("TOPEMA_PRD")
    
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
    except Exception as e:
        print(f"Erro ao conectar ao DTS (externo): {e}")
        # Exibe o erro no Streamlit e para a execução
        st.error(f"Falha na conexão com o banco de dados DTS (externo). Verifique o console para detalhes. Erro: {e}")
        if not is_streamlit_cloud:
            st.stop()
        else:
            st.warning("Usando conexão simulada como fallback")
            return MockConnection("TOPEMA_PRD")

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








