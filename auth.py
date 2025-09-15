import streamlit as st

# Usuários de exemplo com suas senhas, papéis e e-mails (quando aplicável)
# Em um ambiente real, isso viria de um banco de dados seguro
USERS = {
    "carlos.amaral": {"password": "123", "role": "Tecnico"},
    "antonio.fernandes": {"password": "123", "role": "Tecnico"},
    "admin1": {"password": "123", "role": "Administrativo"},
    "rafael.barboza": {"password": "123", "role": "Gestor Garantia", "email": "rafael.barboza@empresa.com"},
    "adriana.masini": {"password": "123", "role": "Gestor Garantia", "email": "adriana.masini@empresa.com"},
    "marcio.ferreira": {"password": "123", "role": "Almoxarifado"},
    "adm": {"password": "admin", "role": "ADM"},
    "carlos": {"password": "123", "role": "Tecnico", "email": "carlos@empresa.com"},
    "rafael": {"password": "123", "role": "Gestor Garantia", "email": "rafael@empresa.com"},
    "marcio": {"password": "123", "role": "Almoxarifado", "email": "marcio@empresa.com"},
    
    # Novos usuários para os gestores específicos por centro de custo
    "gestor.garantia": {"password": "123", "role": "Gestor Garantia", "email": "posvendas01@topema.com", "centro_custo": "040023"},
    "gestor.assistencia": {"password": "123", "role": "Gestor Assistencia", "email": "gestor.assistencia@empresa.com", "centro_custo": "040031"},
    "gestor.instalacoes": {"password": "123", "role": "Gestor Instalacoes", "email": "gestor.instalacoes@empresa.com", "centro_custo": "040024"},
}

def authenticate(username, password):
    """Autentica o usuário e retorna seu papel se as credenciais forem válidas."""
    user_info = USERS.get(username)
    if user_info and user_info["password"] == password:
        return user_info
    return None

def get_user_role():
    """Retorna o papel do usuário logado."""
    return st.session_state.get("user_role")

def get_user_centro_custo():
    """Retorna o centro de custo do usuário logado, se disponível."""
    username = st.session_state.get("username")
    if username:
        return USERS.get(username, {}).get("centro_custo")
    return None

def get_logged_in_username():
    """Retorna o nome do usuário logado."""
    return st.session_state.get("username")

def get_logged_in_user_email():
    """Retorna o email do usuário logado."""
    username = st.session_state.get("username")
    if username:
        return USERS.get(username, {}).get("email")
    return None

def is_logged_in():
    """Verifica se há um usuário logado."""
    return "logged_in" in st.session_state and st.session_state.logged_in

def has_permission(required_roles):
    """Verifica se o usuário logado tem uma das permissões necessárias."""
    if not is_logged_in():
        return False
    
    user_role = get_user_role()
    
    # ADM tem acesso a tudo
    if user_role == "ADM":
        return True
    
    # Se é algum tipo de gestor verificando permissão genérica de "Gestor Garantia"
    if user_role in ["Gestor Garantia", "Gestor Assistencia", "Gestor Instalacoes"]:
        # Se a lista de papéis solicitados inclui "Gestor Garantia" ou o papel específico
        if "Gestor Garantia" in required_roles or user_role in required_roles:
            return True
    
    # Verificação direta de papel
    return user_role in required_roles

def is_specific_gestor(centro_custo):
    """
    Verifica se o usuário logado é o gestor específico do centro de custo fornecido.
    """
    if not is_logged_in():
        return False
    
    username = get_logged_in_username()
    user_info = USERS.get(username, {})
    user_centro_custo = user_info.get("centro_custo")
    
    # Se o usuário tem o papel ADM, ele pode acessar qualquer centro de custo
    if user_info.get("role") == "ADM":
        return True
    
    # Para gestores antigos sem centro_custo específico, permitir acesso a qualquer um
    if user_info.get("role") in ["Gestor Garantia"] and not user_centro_custo:
        return True
    
    return user_centro_custo == centro_custo

def login_page():
    """Renderiza a página de login."""
    st.title("Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        user_info = authenticate(username, password)
        if user_info:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.user_role = user_info["role"]
            # Armazenar o centro_custo na sessão, se disponível
            if "centro_custo" in user_info:
                st.session_state.user_centro_custo = user_info["centro_custo"]
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")

def logout():
    """Desloga o usuário."""
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_role = None
    if "user_centro_custo" in st.session_state:
        del st.session_state.user_centro_custo
    st.success("Você foi desconectado.")
    st.rerun()

