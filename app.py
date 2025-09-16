import streamlit as st
import auth
import db_manager
import pandas as pd
import datetime
import email_sender
from urllib.parse import urlparse, parse_qs
import io 

from database import get_protheus_connection, get_dts_connection
from page_dashboard import page_dashboard

db_manager.init_database()


# --- Configurações Iniciais ---
st.set_page_config(layout="wide", page_title="Gestão de Solicitação de Componentes - Garantia")

# Inicializa o estado da sessão se não existir
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_role = None

# --- Funções de Ajuda ---
def get_current_app_base_url():
    """Tenta obter a URL base do aplicativo Streamlit."""
    # Em ambiente local, pode ser "http://localhost:8501"
    # Em um ambiente deployado, o Streamlit pode fornecer via headers ou variáveis de ambiente.
    # Para simplicidade, vamos usar um valor padrão e instruir o usuário a ajustar.
    if "STREAMLIT_SERVER_URL" in st.secrets:
        return st.secrets["STREAMLIT_SERVER_URL"]
    return "http://localhost:8501" # MUDAR ISSO PARA A URL REAL DO SEU APP EM PRODUÇÃO!

def display_solicitacao_details(solicitacao_id):
    """Exibe os detalhes de uma solicitação e seu histórico."""
    solicitacao = db_manager.get_solicitacao_by_id(solicitacao_id)
    if solicitacao:
        st.subheader(f"Detalhes da Solicitação #{solicitacao_id}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Status Atual:** {solicitacao['status_atual']}")
            st.write(f"**Data Criação:** {solicitacao['data_criacao']}")
            st.write(f"**Solicitante:** {solicitacao['solicitante']}")
            st.write(f"**Cliente:** {solicitacao['cliente_nome']} ({solicitacao['cliente_cnpj']})")
        with col2:
            st.write(f"**Pedido Venda:** {solicitacao['pedido_venda']}")
            st.write(f"**Equipamento:** {solicitacao['equipamento_nome']} (SKU: {solicitacao['equipamento_sku']})")
            if solicitacao['aprovador']:
                st.write(f"**Aprovador:** {solicitacao['aprovador']} em {solicitacao['data_aprovacao']}")
            if solicitacao['motivo_rejeicao']:
                st.write(f"**Motivo Rejeição:** {solicitacao['motivo_rejeicao']}")
        with col3:
            if solicitacao['almoxarife_liberacao']:
                st.write(f"**Liberado por:** {solicitacao['almoxarife_liberacao']} em {solicitacao['data_liberacao']}")
            if solicitacao['motivo_nao_disponivel']:
                st.write(f"**Motivo Não Disponível:** {solicitacao['motivo_nao_disponivel']}")
            if solicitacao['retirado_por']:
                st.write(f"**Retirado por:** {solicitacao['retirado_por']} em {solicitacao['data_retirada']}")

        st.markdown("---")
        st.subheader("Componentes da Solicitação")
        itens = db_manager.get_itens_solicitacao(solicitacao_id)
        if not itens.empty:
            st.dataframe(itens[[
                'componente_sku', 'componente_desc', 'quantidade_solicitada',
                'quantidade_liberada', 'quantidade_retirada', 'quantidade_devolvida'
            ]].rename(columns={
                'componente_sku': 'SKU',
                'componente_desc': 'Descrição',
                'quantidade_solicitada': 'Solicitada',
                'quantidade_liberada': 'Liberada',
                'quantidade_retirada': 'Retirada',
                'quantidade_devolvida': 'Devolvida'
            }), use_container_width=True)
        else:
            st.info("Nenhum componente encontrado para esta solicitação.")

        st.markdown("---")
        st.subheader("Histórico da Solicitação")
        historico = db_manager.get_historico_solicitacao(solicitacao_id)
        if not historico.empty:
            st.dataframe(historico[['timestamp', 'usuario', 'acao', 'detalhes']], use_container_width=True)
        else:
            st.info("Nenhum histórico encontrado para esta solicitação.")
    else:
        st.error("Solicitação não encontrada.")

def page_solicitacao():
    if not auth.has_permission(["Tecnico", "Administrativo"]):
        st.warning("Você não tem permissão para acessar esta página.")
        return
    st.title("Nova Solicitação de Componentes")
    # Função auxiliar para garantir um valor mínimo seguro
    def safe_value(value, default=1):
        if value is None or value < 1:
            return default
        return value
    df_info = db_manager.get_clientes_pedidos_equipamentos()
    if df_info.empty:
        st.warning("Nenhum dado de cliente/pedido/equipamento disponível. Por favor, execute 'gerar_base_pedidos.py' para popular a base de dados.")
        return
    
    # Carregamos os centros de custo disponíveis
    try:
        df_centros_custo = db_manager.get_centros_custo()
        
        if df_centros_custo.empty:
            st.error("Não há centros de custo cadastrados. Contate o administrador.")
            return
            
        # Debug: mostrar número de centros de custo encontrados
        st.info(f"Encontrados {len(df_centros_custo)} centros de custo.")
    except Exception as e:
        st.error(f"Erro ao carregar centros de custo: {str(e)}")
        return
        
    # 1. Selecionar Centro de Custo
    st.subheader("Selecionar Centro de Custo")
    # Criamos opções para o selectbox combinando código e setor
    centro_custo_options = [f"{row['codigo']} - {row['setor']}" for _, row in df_centros_custo.iterrows()]
    centro_custo_selecionado = st.selectbox("Centro de Custo", [""] + centro_custo_options)
    
    # Inicializar variáveis
    selected_cc_codigo = None
    selected_cc_setor = None
    cliente_selecionado_str = "" # Inicializa com valor vazio para evitar UnboundLocalError
    selected_cliente_cnpj = None
    selected_cliente_nome = None
    selected_pedido_venda = None
    selected_equipamento_sku = None
    selected_equipamento_nome = None
    
    if centro_custo_selecionado:
        try:
            parts = centro_custo_selecionado.split(" - ")
            if len(parts) >= 2:
                selected_cc_codigo = parts[0]
                selected_cc_setor = parts[1]
                st.success(f"Centro de custo selecionado: {selected_cc_codigo} - {selected_cc_setor}")
            else:
                st.error(f"Formato inválido para centro de custo: {centro_custo_selecionado}")
                return
        except Exception as e:
            st.error(f"Erro ao processar centro de custo: {str(e)}")
            return
            
        # Continua o fluxo existente de seleção de cliente, pedido, equipamento
        # 2. Selecionar Cliente
        clientes = df_info.apply(lambda row: f"{row['cliente_cnpj_cpf']} - {row['cliente_nome_razao']}", axis=1).unique()
        cliente_selecionado_str = st.selectbox("Selecione o Cliente", [""] + list(clientes))
        if cliente_selecionado_str:
            selected_cliente_cnpj = cliente_selecionado_str.split(" - ")[0]
            selected_cliente_nome = cliente_selecionado_str.split(" - ")[1]
            df_pedidos_cliente = df_info[df_info['cliente_cnpj_cpf'] == selected_cliente_cnpj]
            # 3. Selecionar Pedido de Venda
            pedidos = df_pedidos_cliente.apply(lambda row: f"{row['data_venda']} – {row['numero_pdv']}", axis=1).unique()
            pedido_selecionado_str = st.selectbox("Selecione o Pedido de Venda", [""] + list(pedidos))
            if pedido_selecionado_str:
                selected_pedido_venda = pedido_selecionado_str.split(" – ")[1]
                df_equipamentos_pedido = df_pedidos_cliente[df_pedidos_cliente['numero_pdv'] == selected_pedido_venda]
                # 4. Selecionar Equipamento
                equipamentos = df_equipamentos_pedido.apply(lambda row: f"{row['equipamento_sku']} – {row['equipamento_descricao']}", axis=1).unique()
                equipamento_selecionado_str = st.selectbox("Selecione o Equipamento", [""] + list(equipamentos))
                if equipamento_selecionado_str:
                    selected_equipamento_sku = equipamento_selecionado_str.split(" – ")[0]
                    selected_equipamento_nome = equipamento_selecionado_str.split(" – ")[1]
                st.markdown("---")
                st.subheader(f"Componentes para o Equipamento: {selected_equipamento_nome} (SKU: {selected_equipamento_sku})")
                # 4. Carregar Componentes do Protheus
                df_componentes = db_manager.get_componentes_by_sku_protheus(selected_equipamento_sku)
                if df_componentes.empty:
                    st.warning(f"Nenhum componente encontrado para o SKU '{selected_equipamento_sku}' no Protheus. Verifique a query em `db_manager.py` ou se o SKU possui BOM.")
                    return
                # Inicializa o estado para os componentes selecionados
                if "selected_components" not in st.session_state:
                    st.session_state.selected_components = {}
                if selected_equipamento_sku not in st.session_state.selected_components:
                    st.session_state.selected_components[selected_equipamento_sku] = {}
                # Buscar informações de estoque para todos os componentes de uma vez
                todos_componentes = df_componentes['Componente'].tolist()
                df_estoque = db_manager.get_estoque_componentes(todos_componentes)
                # Criar dicionário para acesso rápido às informações de estoque
                estoque_dict = {}
                if not df_estoque.empty:
                    for _, row in df_estoque.iterrows():
                        estoque_dict[row['Codigo']] = {
                            'saldo': row['Saldo_Disponivel'],
                            'fornecedor': row['Nome_Fornecedor'] if pd.notna(row['Nome_Fornecedor']) else "Não cadastrado",
                            'previsao_entrega': row['Previsao_Entrega_Ultimo_Pedido'] if pd.notna(row['Previsao_Entrega_Ultimo_Pedido']) else None
                        }
                # Criar uma organização hierárquica para exibição
                st.write("Selecione os componentes e suas quantidades:")
                # Opções para filtrar por nível
                nivel_options = df_componentes['Nivel'].unique().tolist()
                nivel_options.sort() # Ordena os níveis
                nivel_filter = st.multiselect("Filtrar por Nível", nivel_options, default=nivel_options)
                # Filtra componentes pelos níveis selecionados
                df_componentes_filtered = df_componentes[df_componentes['Nivel'].isin(nivel_filter)]
                # Opção para visualização: lista simples ou hierárquica
                view_mode = st.radio("Modo de Visualização", ["Lista Simples", "Estrutura Hierárquica"], index=0)
                if view_mode == "Lista Simples":
                    component_list_placeholder = st.empty()
                    with component_list_placeholder.container():
                        for index, row in df_componentes_filtered.iterrows():
                            nivel = row['Nivel']
                            component_sku = row['Componente']
                            pai_componente = row.get('Pai_Componente', 'root')
                            component_desc = row['Descricao_Componente']
                            default_qty = int(row['Quantidade']) if pd.notna(row['Quantidade']) else 1
                            # Obter informações de estoque
                            estoque_info = estoque_dict.get(component_sku, {'saldo': 0, 'fornecedor': "Não encontrado", 'previsao_entrega': None})
                            tem_estoque = estoque_info['saldo'] >= default_qty
                            # Formata a exibição com base no nível
                            prefix = " " * (nivel - 1)
                            if nivel > 1:
                                prefix += "↳ "
                            col_chk, col_desc, col_qty, col_estoque = st.columns([0.1, 0.5, 0.2, 0.2])
                            is_selected = component_sku in st.session_state.selected_components[selected_equipamento_sku]
                            with col_chk:
                                # Usar um identificador único combinando nível, pai e SKU para evitar colisões
                                checkbox_key = f"chk_n{nivel}_{component_sku}_{index}"
                                if col_chk.checkbox("", value=is_selected, key=checkbox_key):
                                    if not is_selected:
                                        st.session_state.selected_components[selected_equipamento_sku][component_sku] = {
                                            "sku": component_sku,
                                            "descricao": component_desc,
                                            "quantidade": max(1, default_qty),
                                            "nivel": nivel,
                                            "tem_estoque": tem_estoque,
                                            "saldo_disponivel": estoque_info['saldo']
                                        }
                                else:
                                    if is_selected:
                                        del st.session_state.selected_components[selected_equipamento_sku][component_sku]
                            with col_desc:
                                component_text = f"{prefix}**{component_sku}** - {component_desc} (Nível {nivel})"
                                if not tem_estoque:
                                    component_text += " 🚫" # Símbolo para indicar falta de estoque
                                st.write(component_text)
                            with col_qty:
                                if component_sku in st.session_state.selected_components[selected_equipamento_sku]:
                                    current_qty = st.session_state.selected_components[selected_equipamento_sku][component_sku]["quantidade"]
                                    current_qty = safe_value(current_qty)
                                    # Usar o mesmo padrão de chave única para todos os widgets relacionados
                                    qty_key = f"qty_n{nivel}_{component_sku}_{index}"
                                    # Botões de + e -
                                    col_minus, col_num, col_plus = st.columns([0.3, 0.4, 0.3])
                                    with col_minus:
                                        if st.button("➖", key=f"minus_n{nivel}_{component_sku}_{index}", help="Diminuir quantidade"):
                                            if current_qty > 1:
                                                st.session_state.selected_components[selected_equipamento_sku][component_sku]["quantidade"] -= 1
                                                st.rerun()
                                    with col_num:
                                        st.number_input("Qtd", min_value=1, value=current_qty, key=qty_key, label_visibility="collapsed",
                                                        on_change=lambda s=selected_equipamento_sku, c=component_sku, k=qty_key: st.session_state.selected_components[s][c].update({"quantidade": st.session_state[k]}))
                                    with col_plus:
                                        if st.button("➕", key=f"plus_n{nivel}_{component_sku}_{index}", help="Aumentar quantidade"):
                                            st.session_state.selected_components[selected_equipamento_sku][component_sku]["quantidade"] += 1
                                            st.rerun()
                            with col_estoque:
                                if tem_estoque:
                                    st.write(f"📦 Estoque: {estoque_info['saldo']:.0f}")
                                else:
                                    if estoque_info['previsao_entrega']:
                                        st.write(f"⚠️ Sem estoque. Previsão: {estoque_info['previsao_entrega']}")
                                    else:
                                        st.write("⚠️ Sem estoque")
                    # Resumo da solicitação para visualização de Lista Simples
                    st.markdown("---")
                    st.subheader("Resumo da Solicitação")
                    if st.session_state.selected_components[selected_equipamento_sku]:
                        summary_data = []
                        produtos_sem_estoque = False
                        for comp_info in st.session_state.selected_components[selected_equipamento_sku].values():
                            estoque_info = estoque_dict.get(comp_info["sku"], {'saldo': 0})
                            tem_estoque = estoque_info['saldo'] >= comp_info["quantidade"]
                            status_estoque = "✅ Em estoque" if tem_estoque else "❌ Sem estoque"
                            if not tem_estoque:
                                produtos_sem_estoque = True
                            summary_data.append([
                                comp_info["sku"],
                                comp_info["descricao"],
                                comp_info["quantidade"],
                                status_estoque
                            ])
                        df_summary = pd.DataFrame(summary_data, columns=["SKU", "Descrição", "Quantidade", "Status Estoque"])
                        st.dataframe(df_summary, use_container_width=True)
                        # Aviso para produtos sem estoque
                        if produtos_sem_estoque:
                            st.warning("⚠️ Alguns componentes não possuem estoque suficiente. A solicitação será enviada com a observação 'Produto sem estoque' para o almoxarifado.")
                        
                        # Exibe o resumo dos dados da solicitação antes de enviar (para debug)
                        with st.expander("Verificar dados da solicitação", expanded=False):
                            st.write("Centro de custo:", selected_cc_codigo)
                            st.write("Setor:", selected_cc_setor)
                            st.write("Cliente:", selected_cliente_nome)
                            st.write("Solicitante:", auth.get_logged_in_username())
                            
                        if st.button("Enviar Solicitação", type="primary", key="enviar_solicitacao_lista_simples"):
                            try:
                                # Verificar se todos os dados essenciais estão preenchidos
                                if not selected_cc_codigo or not selected_cc_setor:
                                    st.error("Centro de custo não selecionado corretamente.")
                                    return
                                    
                                import email_sender
                                
                                solicitacao_id = db_manager.criar_solicitacao(
                                    solicitante=auth.get_logged_in_username(),
                                    solicitante_email=auth.get_logged_in_user_email(),
                                    cliente_cnpj=selected_cliente_cnpj,
                                    cliente_nome=selected_cliente_nome,
                                    pedido_venda=selected_pedido_venda,
                                    equipamento_sku=selected_equipamento_sku,
                                    equipamento_nome=selected_equipamento_nome,
                                    itens_solicitados=list(st.session_state.selected_components[selected_equipamento_sku].values()),
                                    centro_custo=selected_cc_codigo,
                                    setor=selected_cc_setor,
                                    email_sender_module=email_sender,
                                    app_base_url=get_current_app_base_url()
                                )
                                st.success(f"Solicitação #{solicitacao_id} criada com sucesso! Aguardando aprovação do gestor.")
                                
                                # Verificar se a solicitação foi criada corretamente com o centro de custo
                                solicitacao = db_manager.get_solicitacao_by_id(solicitacao_id)
                                if solicitacao:
                                    st.write(f"Centro de custo registrado: {solicitacao.get('centro_custo', 'Não registrado')}")
                                    st.write(f"Setor registrado: {solicitacao.get('setor', 'Não registrado')}")
                                
                                # Limpa após envio
                                st.session_state.selected_components[selected_equipamento_sku] = {}
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao enviar solicitação: {e}")
                                import traceback
                                st.error(traceback.format_exc())
                    else:
                        st.info("Selecione pelo menos um componente para continuar.")
                else: # Estrutura Hierárquica
                    # Exibir componentes de nível 1 primeiro
                    nivel1_componentes = df_componentes[df_componentes['Nivel'] == 1]
                    for idx1, row1 in nivel1_componentes.iterrows():
                        component1_sku = row1['Componente']
                        component1_desc = row1['Descricao_Componente']
                        default_qty1 = int(row1['Quantidade']) if pd.notna(row1['Quantidade']) else 1
                        # Verificar estoque do componente nível 1
                        estoque_info1 = estoque_dict.get(component1_sku, {'saldo': 0, 'fornecedor': "Não encontrado", 'previsao_entrega': None})
                        tem_estoque1 = estoque_info1['saldo'] >= default_qty1
                        # Adiciona indicador de falta de estoque ao título do expander
                        expander_title = f"**{component1_sku}** - {component1_desc}"
                        if not tem_estoque1:
                            expander_title += " 🚫"
                        with st.expander(expander_title, expanded=False):
                            # Checkbox e quantidade para componente de nível 1
                            col_chk1, col_qty1, col_est1 = st.columns([0.5, 0.3, 0.2])
                            is_selected1 = component1_sku in st.session_state.selected_components[selected_equipamento_sku]
                            with col_chk1:
                                # Usar o índice único idx1 para evitar colisões de chaves
                                if st.checkbox(f"Selecionar {component1_sku}", value=is_selected1, key=f"chk_n1_{component1_sku}_{idx1}"):
                                    if not is_selected1:
                                        st.session_state.selected_components[selected_equipamento_sku][component1_sku] = {
                                            "sku": component1_sku,
                                            "descricao": component1_desc,
                                            "quantidade": max(1, default_qty1),
                                            "nivel": 1,
                                            "tem_estoque": tem_estoque1,
                                            "saldo_disponivel": estoque_info1['saldo']
                                        }
                                else:
                                    if is_selected1:
                                        del st.session_state.selected_components[selected_equipamento_sku][component1_sku]
                            with col_qty1:
                                if component1_sku in st.session_state.selected_components[selected_equipamento_sku]:
                                    current_qty1 = st.session_state.selected_components[selected_equipamento_sku][component1_sku]["quantidade"]
                                    current_qty1 = safe_value(current_qty1)
                                    st.number_input("Quantidade", min_value=1, value=current_qty1, key=f"qty_n1_{component1_sku}_{idx1}",
                                                on_change=lambda s=selected_equipamento_sku, c=component1_sku, k=f"qty_n1_{component1_sku}_{idx1}":
                                                st.session_state.selected_components[s][c].update({"quantidade": st.session_state[k]}))
                            with col_est1:
                                if tem_estoque1:
                                    st.write(f"📦 Estoque: {estoque_info1['saldo']:.0f}")
                                else:
                                    if estoque_info1['previsao_entrega']:
                                        st.write(f"⚠️ Sem estoque. Previsão: {estoque_info1['previsao_entrega']}")
                                    else:
                                        st.write("⚠️ Sem estoque")
                            # Se for componente com possíveis subcomponentes (começa com E ou S)
                            if component1_sku.startswith('E') or component1_sku.startswith('S'):
                                # Busca subcomponentes de nível 2
                                nivel2_componentes = df_componentes[(df_componentes['Nivel'] == 2) &
                                                                (df_componentes['Pai_Componente'] == component1_sku)]
                                if not nivel2_componentes.empty:
                                    st.markdown("#### Subcomponentes:")
                                    for idx2, row2 in nivel2_componentes.iterrows():
                                        component2_sku = row2['Componente']
                                        component2_desc = row2['Descricao_Componente']
                                        default_qty2 = int(row2['Quantidade']) if pd.notna(row2['Quantidade']) else 1
                                        # Verificar estoque do componente nível 2
                                        estoque_info2 = estoque_dict.get(component2_sku, {'saldo': 0, 'fornecedor': "Não encontrado", 'previsao_entrega': None})
                                        tem_estoque2 = estoque_info2['saldo'] >= default_qty2
                                        # Adiciona indicador de falta de estoque ao título
                                        component2_title = f"**↳ {component2_sku}** - {component2_desc}"
                                        if not tem_estoque2:
                                            component2_title += " 🚫"
                                        st.markdown(component2_title)
                                        col_chk2, col_qty2, col_est2 = st.columns([0.5, 0.3, 0.2])
                                        is_selected2 = component2_sku in st.session_state.selected_components[selected_equipamento_sku]
                                        with col_chk2:
                                            # Usar combinação de nível, pai e SKU
                                            if st.checkbox(f"Selecionar {component2_sku}", value=is_selected2, key=f"chk_n2_{component1_sku}_{component2_sku}_{idx2}"):
                                                if not is_selected2:
                                                    st.session_state.selected_components[selected_equipamento_sku][component2_sku] = {
                                                        "sku": component2_sku,
                                                        "descricao": component2_desc,
                                                        "quantidade": max(1, default_qty2),
                                                        "nivel": 2,
                                                        "tem_estoque": tem_estoque2,
                                                        "saldo_disponivel": estoque_info2['saldo']
                                                    }
                                            else:
                                                if is_selected2:
                                                    del st.session_state.selected_components[selected_equipamento_sku][component2_sku]
                                        with col_qty2:
                                            if component2_sku in st.session_state.selected_components[selected_equipamento_sku]:
                                                current_qty2 = st.session_state.selected_components[selected_equipamento_sku][component2_sku]["quantidade"]
                                                current_qty2 = safe_value(current_qty2)
                                                st.number_input("Quantidade", min_value=1, value=current_qty2, key=f"qty_n2_{component1_sku}_{component2_sku}_{idx2}",
                                                            on_change=lambda s=selected_equipamento_sku, c=component2_sku, k=f"qty_n2_{component1_sku}_{component2_sku}_{idx2}":
                                                            st.session_state.selected_components[s][c].update({"quantidade": st.session_state[k]}))
                                        with col_est2:
                                            if tem_estoque2:
                                                st.write(f"📦 Estoque: {estoque_info2['saldo']:.0f}")
                                            else:
                                                if estoque_info2['previsao_entrega']:
                                                    st.write(f"⚠️ Sem estoque. Previsão: {estoque_info2['previsao_entrega']}")
                                                else:
                                                    st.write("⚠️ Sem estoque")
                                        # Se for componente com possíveis sub-subcomponentes (começa com E ou S)
                                        if component2_sku.startswith('E') or component2_sku.startswith('S'):
                                            # Busca subcomponentes de nível 3
                                            nivel3_componentes = df_componentes[(df_componentes['Nivel'] == 3) &
                                                                            (df_componentes['Pai_Componente'] == component2_sku)]
                                            if not nivel3_componentes.empty:
                                                for idx3, row3 in nivel3_componentes.iterrows():
                                                    component3_sku = row3['Componente']
                                                    component3_desc = row3['Descricao_Componente']
                                                    default_qty3 = int(row3['Quantidade']) if pd.notna(row3['Quantidade']) else 1
                                                    # Verificar estoque do componente nível 3
                                                    estoque_info3 = estoque_dict.get(component3_sku, {'saldo': 0, 'fornecedor': "Não encontrado", 'previsao_entrega': None})
                                                    tem_estoque3 = estoque_info3['saldo'] >= default_qty3
                                                    # Adiciona indicador de falta de estoque ao título
                                                    component3_title = f"&nbsp;&nbsp;&nbsp;**↳ {component3_sku}** - {component3_desc}"
                                                    if not tem_estoque3:
                                                        component3_title += " 🚫"
                                                    st.markdown(component3_title)
                                                    col_chk3, col_qty3, col_est3 = st.columns([0.5, 0.3, 0.2])
                                                    is_selected3 = component3_sku in st.session_state.selected_components[selected_equipamento_sku]
                                                    with col_chk3:
                                                        # Usar uma chave composta ainda mais específica
                                                        if st.checkbox(f"Selecionar {component3_sku}", value=is_selected3, key=f"chk_n3_{component1_sku}_{component2_sku}_{component3_sku}_{idx3}"):
                                                            if not is_selected3:
                                                                st.session_state.selected_components[selected_equipamento_sku][component3_sku] = {
                                                                    "sku": component3_sku,
                                                                    "descricao": component3_desc,
                                                                    "quantidade": max(1, default_qty3),
                                                                    "nivel": 3,
                                                                    "tem_estoque": tem_estoque3,
                                                                    "saldo_disponivel": estoque_info3['saldo']
                                                                }
                                                        else:
                                                            if is_selected3:
                                                                del st.session_state.selected_components[selected_equipamento_sku][component3_sku]
                                                    with col_qty3:
                                                        if component3_sku in st.session_state.selected_components[selected_equipamento_sku]:
                                                            current_qty3 = st.session_state.selected_components[selected_equipamento_sku][component3_sku]["quantidade"]
                                                            current_qty3 = safe_value(current_qty3)
                                                            st.number_input("Quantidade", min_value=1, value=current_qty3, key=f"qty_n3_{component1_sku}_{component2_sku}_{component3_sku}_{idx3}",
                                                                        on_change=lambda s=selected_equipamento_sku, c=component3_sku, k=f"qty_n3_{component1_sku}_{component2_sku}_{component3_sku}_{idx3}":
                                                                        st.session_state.selected_components[s][c].update({"quantidade": st.session_state[k]}))
                                                    with col_est3:
                                                        if tem_estoque3:
                                                            st.write(f"📦 Estoque: {estoque_info3['saldo']:.0f}")
                                                        else:
                                                            if estoque_info3['previsao_entrega']:
                                                                st.write(f"⚠️ Sem estoque. Previsão: {estoque_info3['previsao_entrega']}")
                                                            else:
                                                                st.write("⚠️ Sem estoque")
                    # Resumo da solicitação para visualização Hierárquica
                    st.markdown("---")
                    st.subheader("Resumo da Solicitação")
                    if st.session_state.selected_components[selected_equipamento_sku]:
                        summary_data = []
                        produtos_sem_estoque = False
                        for comp_info in st.session_state.selected_components[selected_equipamento_sku].values():
                            estoque_info = estoque_dict.get(comp_info["sku"], {'saldo': 0})
                            tem_estoque = estoque_info['saldo'] >= comp_info["quantidade"]
                            status_estoque = "✅ Em estoque" if tem_estoque else "❌ Sem estoque"
                            if not tem_estoque:
                                produtos_sem_estoque = True
                            summary_data.append([
                                comp_info["sku"],
                                comp_info["descricao"],
                                comp_info["quantidade"],
                                status_estoque
                            ])
                        df_summary = pd.DataFrame(summary_data, columns=["SKU", "Descrição", "Quantidade", "Status Estoque"])
                        st.dataframe(df_summary, use_container_width=True)
                        # Aviso para produtos sem estoque
                        if produtos_sem_estoque:
                            st.warning("⚠️ Alguns componentes não possuem estoque suficiente. A solicitação será enviada com a observação 'Produto sem estoque' para o almoxarifado.")
                            
                        # Exibe o resumo dos dados da solicitação antes de enviar (para debug)
                        with st.expander("Verificar dados da solicitação", expanded=False):
                            st.write("Centro de custo:", selected_cc_codigo)
                            st.write("Setor:", selected_cc_setor)
                            st.write("Cliente:", selected_cliente_nome)
                            st.write("Solicitante:", auth.get_logged_in_username())
                            
                        if st.button("Enviar Solicitação", type="primary", key="enviar_solicitacao_hierarquica"):
                            try:
                                # Verificar se todos os dados essenciais estão preenchidos
                                if not selected_cc_codigo or not selected_cc_setor:
                                    st.error("Centro de custo não selecionado corretamente.")
                                    return
                                    
                                import email_sender
                                
                                solicitacao_id = db_manager.criar_solicitacao(
                                    solicitante=auth.get_logged_in_username(),
                                    solicitante_email=auth.get_logged_in_user_email(),
                                    cliente_cnpj=selected_cliente_cnpj,
                                    cliente_nome=selected_cliente_nome,
                                    pedido_venda=selected_pedido_venda,
                                    equipamento_sku=selected_equipamento_sku,
                                    equipamento_nome=selected_equipamento_nome,
                                    itens_solicitados=list(st.session_state.selected_components[selected_equipamento_sku].values()),
                                    centro_custo=selected_cc_codigo,
                                    setor=selected_cc_setor,
                                    email_sender_module=email_sender,
                                    app_base_url=get_current_app_base_url()
                                )
                                st.success(f"Solicitação #{solicitacao_id} criada com sucesso! Aguardando aprovação do gestor.")
                                
                                # Verificar se a solicitação foi criada corretamente com o centro de custo
                                solicitacao = db_manager.get_solicitacao_by_id(solicitacao_id)
                                if solicitacao:
                                    st.write(f"Centro de custo registrado: {solicitacao.get('centro_custo', 'Não registrado')}")
                                    st.write(f"Setor registrado: {solicitacao.get('setor', 'Não registrado')}")
                                
                                # Limpa após envio
                                st.session_state.selected_components[selected_equipamento_sku] = {} 
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao enviar solicitação: {e}")
                                import traceback
                                st.error(traceback.format_exc())
                    else:
                        st.info("Nenhum componente selecionado para a solicitação.")
    else:
        st.info("Por favor, selecione um Centro de Custo para continuar.")



def page_aprovacao_solicitacao():
    """Página para gestores aprovarem ou rejeitarem solicitações."""
    
    # Verificamos permissões com mais detalhes
    user_role = auth.get_user_role()
    username = auth.get_logged_in_username()
    
    # Lista de roles permitidos a aprovar solicitações
    gestores_permitidos = ["Gestor Garantia", "Gestor Assistencia", "Gestor Instalacoes"]
    
    if not auth.has_permission(gestores_permitidos):
        st.warning("Você não tem permissão para acessar esta página.")
        return
    
    st.title("Aprovação de Solicitações")
    
    # Obter solicitações pendentes para o gestor atual
    solicitacoes_pendentes = db_manager.get_solicitacoes_pendentes_aprovacao_by_gestor(username)
    
    # Debugging para verificar se estamos obtendo solicitações
    st.write(f"Usuário: {username}, Role: {user_role}")
    st.write(f"Encontradas {len(solicitacoes_pendentes)} solicitações pendentes")
    
    if solicitacoes_pendentes.empty:
        st.info("Não há solicitações pendentes de aprovação para você no momento.")
        return
    
    st.write(f"**{len(solicitacoes_pendentes)}** solicitações pendentes de aprovação:")
    for index, solicitacao in solicitacoes_pendentes.iterrows():
        st.markdown(f"---")
        st.subheader(f"Solicitação #{solicitacao['id']} - Cliente: {solicitacao['cliente_nome']}")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Solicitante:** {solicitacao['solicitante']}")
            st.write(f"**Data Criação:** {solicitacao['data_criacao']}")
            st.write(f"**Equipamento:** {solicitacao['equipamento_nome']}")
        with col2:
            st.write(f"**Pedido Venda:** {solicitacao['pedido_venda']}")
            st.write(f"**Status:** {solicitacao['status_atual']}")
        
        # Busca itens da solicitação
        itens = db_manager.get_itens_solicitacao(solicitacao['id'])
        
        if not itens.empty:
            # Busca informações de estoque para os componentes
            componentes_skus = itens['componente_sku'].tolist()
            df_estoque = db_manager.get_estoque_componentes(componentes_skus)
            
            # Criar um dicionário para mapear estoque por SKU
            estoque_por_sku = {}
            if not df_estoque.empty:
                for _, row in df_estoque.iterrows():
                    estoque_por_sku[row['Codigo']] = {
                        'saldo': row['Saldo_Disponivel'],
                        'previsao': row.get('Previsao_Entrega_Ultimo_Pedido')
                    }
            
            # Prepara dados para exibição com informações de estoque
            display_data = []
            algum_estoque_insuficiente = False
            
            for _, item in itens.iterrows():
                sku = item['componente_sku']
                qtd_solicitada = item['quantidade_solicitada']
                
                estoque_info = estoque_por_sku.get(sku, {'saldo': 0, 'previsao': None})
                saldo_disponivel = estoque_info['saldo']
                previsao_chegada = estoque_info['previsao']
                
                status_estoque = '✅' if saldo_disponivel >= qtd_solicitada else '❌'
                if saldo_disponivel < qtd_solicitada:
                    algum_estoque_insuficiente = True
                
                info_estoque = f"{status_estoque} {saldo_disponivel}/{qtd_solicitada}"
                if saldo_disponivel < qtd_solicitada and previsao_chegada:
                    info_estoque += f" (Previsão: {previsao_chegada})"
                
                display_data.append({
                    'SKU': sku,
                    'Descrição': item['componente_desc'],
                    'Quantidade': qtd_solicitada,
                    'Estoque': info_estoque
                })
            
            # Exibe tabela com informações de estoque
            st.dataframe(pd.DataFrame(display_data), use_container_width=True)
            
            # Alerta sobre estoque insuficiente
            if algum_estoque_insuficiente:
                st.warning("⚠️ Um ou mais itens possuem estoque insuficiente.")
        
        col_buttons = st.columns(2)
        with col_buttons[0]:
            if st.button(f"Aprovar Solicitação #{solicitacao['id']}", key=f"approve_{solicitacao['id']}", type="primary"):
                db_manager.update_status_solicitacao(
                    solicitacao['id'],
                    'Aprovada',
                    auth.get_logged_in_username(),
                    "Solicitação aprovada pelo gestor.",
                    aprovador=auth.get_logged_in_username(),
                    data_aprovacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    motivo_rejeicao=None # Garante que o motivo de rejeição seja limpo
                )
                # Enviar e-mail para o almoxarifado
                app_base_url = get_current_app_base_url()
                email_sent = email_sender.send_email_to_almoxarifado(
                    solicitacao['id'], solicitacao, itens.to_dict('records'), app_base_url
                )
                if email_sent:
                    st.success(f"Solicitação #{solicitacao['id']} aprovada e e-mail enviado ao almoxarifado!")
                else:
                    st.warning(f"Solicitação #{solicitacao['id']} aprovada, mas houve um erro ao enviar o e-mail ao almoxarifado.")
                st.rerun()
        with col_buttons[1]:
            with st.expander(f"Rejeitar Solicitação #{solicitacao['id']}"):
                motivo = st.text_area(f"Motivo da Rejeição para #{solicitacao['id']}", key=f"motivo_rejeicao_{solicitacao['id']}")
                if st.button(f"Confirmar Rejeição #{solicitacao['id']}", key=f"reject_{solicitacao['id']}", type="secondary"):
                    if motivo:
                        db_manager.update_status_solicitacao(
                            solicitacao['id'],
                            'Rejeitada',
                            auth.get_logged_in_username(),
                            f"Solicitação rejeitada. Motivo: {motivo}",
                            aprovador=auth.get_logged_in_username(),
                            data_aprovacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            motivo_rejeicao=motivo
                        )
                        st.error(f"Solicitação #{solicitacao['id']} rejeitada.")
                        st.rerun()
                    else:
                        st.warning("Por favor, insira o motivo da rejeição.")

def page_diagnostico():
    """Página de diagnóstico do sistema."""
    if not auth.has_permission(["ADM"]):
        st.warning("Você não tem permissão para acessar esta página de diagnóstico.")
        return
    
    st.title("Diagnóstico do Sistema")
    
    # Verificar configuração de centros de custo
    st.header("Centros de Custo")
    diagnostico = db_manager.diagnostico_centros_custo()
    
    if isinstance(diagnostico, dict):
        st.subheader("Tabela de Centros de Custo")
        st.dataframe(diagnostico["centros_custo"])
        
        st.subheader("Solicitações Pendentes por Centro de Custo")
        if diagnostico["solicitacoes_por_centro"].empty:
            st.info("Não há solicitações pendentes no momento.")
        else:
            st.dataframe(diagnostico["solicitacoes_por_centro"])
    else:
        st.error(diagnostico)  # Mostra mensagem de erro
    
    # Verificar configuração de usuários gestores
    st.header("Verificação de Usuários Gestores")
    gestores_info = db_manager.verificar_usuarios_gestores()
    
    if "erro" in gestores_info:
        st.error(gestores_info["erro"])
    else:
        st.subheader("Gestores Cadastrados no Banco de Dados")
        st.json(gestores_info["gestores_db"])
        
        st.subheader("Gestores Configurados no Módulo Auth")
        st.json(gestores_info["gestores_auth"])
        
        if gestores_info["missing_in_auth"]:
            st.warning(f"Gestores no banco mas não no auth: {gestores_info['missing_in_auth']}")
        
        if gestores_info["missing_in_db"]:
            st.warning(f"Gestores no auth mas não no banco: {gestores_info['missing_in_db']}")
        
        if not gestores_info["missing_in_auth"] and not gestores_info["missing_in_db"]:
            st.success("Todos os gestores estão corretamente configurados!")
    
    # Verificar solicitações pendentes
    st.header("Todas as Solicitações Pendentes")
    all_pending = db_manager.get_solicitacoes_pendentes_aprovacao()
    if all_pending.empty:
        st.info("Não há solicitações pendentes de aprovação no sistema.")
    else:
        st.write(f"Total de solicitações pendentes: {len(all_pending)}")
        st.dataframe(all_pending[['id', 'solicitante', 'cliente_nome', 'centro_custo', 'setor', 'data_criacao', 'data_ultimo_status']])

def page_liberacao_almoxarifado():
    if not auth.has_permission(["Almoxarifado"]):
        st.warning("Você não tem permissão para acessar esta página.")
        return
    st.title("Liberação de Componentes - Almoxarifado")
    # Verifica se há um ID de solicitação na URL (vindo do e-mail)
    query_params = parse_qs(st.query_params.to_dict().get('query_string', [''])[0])
    solicitacao_id_from_url = query_params.get('solicitacao_id', [None])[0]
    solicitacoes_aprovadas = db_manager.get_solicitacoes_aprovadas_pendentes_liberacao()
    if solicitacoes_aprovadas.empty:
        st.info("Não há solicitações aprovadas aguardando liberação no momento.")
        return
    # Prioriza a solicitação da URL, se existir e for válida
    if solicitacao_id_from_url and int(solicitacao_id_from_url) in solicitacoes_aprovadas['id'].values:
        selected_solicitacao_id = int(solicitacao_id_from_url)
        st.subheader(f"Solicitação da URL: #{selected_solicitacao_id}")
    else:
        solicitacao_options = [""] + list(solicitacoes_aprovadas.apply(lambda row: f"#{row['id']} - Cliente: {row['cliente_nome']} - Solicitante: {row['solicitante']}", axis=1).values)
        selected_solicitacao_str = st.selectbox("Selecione uma Solicitação para Liberar", solicitacao_options)
        selected_solicitacao_id = int(selected_solicitacao_str.split(" - ")[0][1:]) if selected_solicitacao_str else None
    
    if selected_solicitacao_id:
        solicitacao = db_manager.get_solicitacao_by_id(selected_solicitacao_id)
        itens = db_manager.get_itens_solicitacao(selected_solicitacao_id)
        st.markdown(f"---")
        st.subheader(f"Detalhes da Solicitação #{solicitacao['id']}")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Solicitante:** {solicitacao['solicitante']}")
            st.write(f"**Data Criação:** {solicitacao['data_criacao']}")
            st.write(f"**Equipamento:** {solicitacao['equipamento_nome']}")
        with col2:
            st.write(f"**Cliente:** {solicitacao['cliente_nome']}")
            st.write(f"**Pedido Venda:** {solicitacao['pedido_venda']}")
            st.write(f"**Status:** {solicitacao['status_atual']}")
        
        # Buscar informações de estoque para os componentes
        componentes_skus = itens['componente_sku'].tolist()
        df_estoque = db_manager.get_estoque_componentes(componentes_skus)
        
        # Criar um dicionário para mapear estoque por SKU
        estoque_por_sku = {}
        if not df_estoque.empty:
            for _, row in df_estoque.iterrows():
                estoque_por_sku[row['Codigo']] = {
                    'saldo': row['Saldo_Disponivel'],
                    'quantidade_atual': row['Quantidade_Atual'],
                    'empenhada': row.get('Quantidade_Empenhada', 0),
                    'reservada': row.get('Quantidade_Reservada', 0),
                    'previsao': row.get('Previsao_Entrega_Ultimo_Pedido'),
                    'armazem': row.get('Armazem', '')
                }
        
        st.markdown("---")
        st.subheader("Componentes para Liberar")
        
        # Verificar se algum item tem estoque insuficiente
        algum_estoque_insuficiente = False
        editable_itens = []
        
        for index, item in itens.iterrows():
            sku = item['componente_sku']
            qtd_solicitada = int(item['quantidade_solicitada'])  # Garantindo que seja int
            
            estoque_info = estoque_por_sku.get(sku, {'saldo': 0, 'quantidade_atual': 0, 'empenhada': 0, 'reservada': 0, 'previsao': None, 'armazem': ''})
            saldo_disponivel = int(estoque_info['saldo'])  # Garantindo que seja int
            
            # Verifica se há estoque suficiente
            tem_estoque_suficiente = saldo_disponivel >= qtd_solicitada
            if not tem_estoque_suficiente:
                algum_estoque_insuficiente = True
            
            # Exibe informações do componente com dados de estoque
            st.markdown(f"""
            <div style="padding: 10px; border: 1px solid {'green' if tem_estoque_suficiente else 'red'}; border-radius: 5px; margin-bottom: 10px;">
                <h4>{sku} - {item['componente_desc']}</h4>
            </div>
            """, unsafe_allow_html=True)
            
            col_estoque, col_lib = st.columns([0.7, 0.3])
            
            with col_estoque:
                st.write(f"**Solicitado:** {qtd_solicitada}")
                st.write(f"**Saldo Disponível:** {saldo_disponivel}")
                st.write(f"**Quantidade Atual:** {int(estoque_info['quantidade_atual'])}")
                
                # Informações adicionais de estoque
                if estoque_info['armazem']:
                    st.write(f"**Armazém:** {estoque_info['armazem']}")
                if estoque_info['empenhada'] > 0:
                    st.write(f"**Empenhada:** {int(estoque_info['empenhada'])}")
                if estoque_info['reservada'] > 0:
                    st.write(f"**Reservada:** {int(estoque_info['reservada'])}")
                
                # Mensagem de estoque insuficiente com previsão de chegada
                if not tem_estoque_suficiente:
                    st.warning(f"**⚠️ Estoque insuficiente!** Faltam {qtd_solicitada - saldo_disponivel} unidades.")
                    if estoque_info['previsao']:
                        st.info(f"**📅 Previsão de chegada:** {estoque_info['previsao']}")
            
            with col_lib:
                # Define o valor máximo como o mínimo entre o solicitado e o disponível em estoque
                valor_maximo = min(qtd_solicitada, saldo_disponivel) if saldo_disponivel > 0 else qtd_solicitada
                valor_inicial = valor_maximo if tem_estoque_suficiente else saldo_disponivel
                
                # CORREÇÃO: Garantir que todos os valores sejam do mesmo tipo (int)
                qty_liberada = st.number_input(
                    f"Liberar Qtd", 
                    min_value=0, 
                    max_value=int(qtd_solicitada),  # Converter para int
                    value=int(valor_inicial),       # Converter para int
                    step=1,                         # Usar passo inteiro
                    key=f"lib_qty_{item['id']}"
                )
                
                editable_itens.append({
                    'id': item['id'],
                    'componente_sku': sku,
                    'componente_desc': item['componente_desc'],
                    'quantidade_solicitada': qtd_solicitada,
                    'quantidade_liberada': int(qty_liberada)  # Garantir que seja int
                })
        
        # Alerta geral sobre estoque insuficiente
        if algum_estoque_insuficiente:
            st.markdown("---")
            st.warning("⚠️ **ATENÇÃO:** Um ou mais itens possuem estoque insuficiente. A liberação será parcial.")
        
        st.markdown("---")
        col_actions = st.columns(2)
        with col_actions[0]:
            # Determinar automaticamente se é liberação total ou parcial
            total_solicitado = sum(item['quantidade_solicitada'] for item in editable_itens)
            total_liberado = sum(item['quantidade_liberada'] for item in editable_itens)
            status_liberacao = "Disponível para Retirada" if total_liberado == total_solicitado else "Liberação Parcial"
            
            # Botão com texto que reflete o tipo de liberação
            button_text = f"{status_liberacao} - Solicitação #{selected_solicitacao_id}"
            if st.button(button_text, type="primary"):
                db_manager.update_itens_solicitacao_liberacao(selected_solicitacao_id, editable_itens, auth.get_logged_in_username())
                db_manager.update_status_solicitacao(
                    selected_solicitacao_id,
                    status_liberacao,
                    auth.get_logged_in_username(),
                    f"Componentes separados e {status_liberacao.lower()}.",
                    almoxarife_liberacao=auth.get_logged_in_username(),
                    data_liberacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    motivo_nao_disponivel=None
                )
                st.success(f"Solicitação #{selected_solicitacao_id}: Componentes marcados como '{status_liberacao}'.")
                st.rerun()
                
        with col_actions[1]:
            with st.expander(f"Não é possível separar - Solicitação #{selected_solicitacao_id}"):
                motivo = st.text_area(f"Motivo para não separar #{selected_solicitacao_id}", key=f"motivo_nao_sep_{selected_solicitacao_id}")
                if st.button(f"Registrar Motivo - Solicitação #{selected_solicitacao_id}", type="secondary"):
                    if motivo:
                        db_manager.update_status_solicitacao(
                            selected_solicitacao_id,
                            'Não Disponível',
                            auth.get_logged_in_username(),
                            f"Almoxarifado não pôde separar. Motivo: {motivo}",
                            almoxarife_liberacao=auth.get_logged_in_username(),
                            data_liberacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            motivo_nao_disponivel=motivo
                        )
                        st.warning(f"Solicitação #{selected_solicitacao_id}: Registrado motivo de não disponibilidade.")
                        st.rerun()
                    else:
                        st.warning("Por favor, insira o motivo para não separar.")

def page_confirmar_retirada_devolucao():
    # Esta página pode ser acessada por link direto ou pelo menu
    # Não requer permissão específica no menu, mas as ações sim
    st.title("Confirmação de Retirada / Devolução")

    # Pega o ID da solicitação da URL, se existir
    query_params = parse_qs(st.query_params.to_dict().get('query_string', [''])[0])
    solicitacao_id_from_url = query_params.get('solicitacao_id', [None])[0]

    # Se o usuário for um Técnico, filtra apenas suas próprias solicitações
    if st.session_state.user_role == "Tecnico":
        solicitacoes_para_retirada = db_manager.get_solicitacoes_pendentes_retirada().query(f"solicitante == '{st.session_state.username}'")
        if solicitacoes_para_retirada.empty:
            st.info("Você não tem solicitações pendentes de retirada.")
    else:
        # Outros perfis (Administrativo, Almoxarifado) podem ver todas
        solicitacoes_para_retirada = db_manager.get_solicitacoes_pendentes_retirada()
    solicitacoes_para_devolucao = db_manager.get_all_solicitacoes()[
        (db_manager.get_all_solicitacoes()['status_atual'] == 'Retirada Confirmada') |
        (db_manager.get_all_solicitacoes()['status_atual'] == 'Devolução Pendente Almoxarifado')
    ]

    all_eligible_solicitations = pd.concat([solicitacoes_para_retirada, solicitacoes_para_devolucao]).drop_duplicates(subset=['id'])

    selected_solicitacao_id = None
    if solicitacao_id_from_url and int(solicitacao_id_from_url) in all_eligible_solicitations['id'].values:
        selected_solicitacao_id = int(solicitacao_id_from_url)
        st.subheader(f"Solicitação da URL: #{selected_solicitacao_id}")
    else:
        solicitacao_options = [""] + list(all_eligible_solicitations.apply(lambda row: f"#{row['id']} - Cliente: {row['cliente_nome']} - Status: {row['status_atual']}", axis=1).values)
        selected_solicitacao_str = st.selectbox("Selecione uma Solicitação", solicitacao_options)
        selected_solicitacao_id = int(selected_solicitacao_str.split(" - ")[0][1:]) if selected_solicitacao_str else None

    if selected_solicitacao_id:
        solicitacao = db_manager.get_solicitacao_by_id(selected_solicitacao_id)
        itens = db_manager.get_itens_solicitacao(selected_solicitacao_id)

        st.markdown(f"---")
        st.subheader(f"Detalhes da Solicitação #{solicitacao['id']}")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Solicitante:** {solicitacao['solicitante']}")
            st.write(f"**Data Criação:** {solicitacao['data_criacao']}")
            st.write(f"**Equipamento:** {solicitacao['equipamento_nome']}")
        with col2:
            st.write(f"**Cliente:** {solicitacao['cliente_nome']}")
            st.write(f"**Pedido Venda:** {solicitacao['pedido_venda']}")
            st.write(f"**Status:** {solicitacao['status_atual']}")

        st.markdown("---")
        st.subheader("Componentes")
        st.dataframe(itens[[
            'componente_sku', 'componente_desc', 'quantidade_solicitada',
            'quantidade_liberada', 'quantidade_retirada', 'quantidade_devolvida'
        ]].rename(columns={
            'componente_sku': 'SKU',
            'componente_desc': 'Descrição',
            'quantidade_solicitada': 'Solicitada',
            'quantidade_liberada': 'Liberada',
            'quantidade_retirada': 'Retirada',
            'quantidade_devolvida': 'Devolvida'
        }), use_container_width=True)

        current_status = solicitacao['status_atual']
        logged_in_user = auth.get_logged_in_username()

        if current_status == 'Disponível para Retirada':
            if auth.has_permission(["Tecnico", "Administrativo"]):
                # Verificar se o usuário é técnico e se é o solicitante original
                if st.session_state.user_role == "Tecnico" and solicitacao['solicitante'] != st.session_state.username:
                    st.warning(f"Você não tem permissão para confirmar a retirada desta solicitação. Apenas o solicitante original ({solicitacao['solicitante']}) pode fazer isso.")
                else:
                    if st.button(f"Confirmar Retirada - Solicitação #{selected_solicitacao_id}", type="primary"):
                        db_manager.update_itens_solicitacao_retirada(selected_solicitacao_id, logged_in_user)
                        db_manager.update_status_solicitacao(
                            selected_solicitacao_id,
                            'Retirada Confirmada',
                            logged_in_user,
                            "Solicitante confirmou a retirada dos componentes.",
                            retirado_por=logged_in_user,
                            data_retirada=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )
                        st.success(f"Retirada da Solicitação #{selected_solicitacao_id} confirmada!")
                        st.rerun()
            else:
                st.warning("Você não tem permissão para confirmar a retirada.")

        elif current_status == 'Retirada Confirmada':
            if auth.has_permission(["Tecnico", "Administrativo"]):
                # Verificar se o usuário é técnico e se é o solicitante original
                if st.session_state.user_role == "Tecnico" and solicitacao['solicitante'] != st.session_state.username:
                    st.warning(f"Você não tem permissão para finalizar ou devolver componentes desta solicitação. Apenas o solicitante original ({solicitacao['solicitante']}) pode fazer isso.")
                else:
                    st.markdown("---")
                    st.subheader("Ações Pós-Retirada")

                # Opção para finalizar (se tudo foi usado)
                if st.button(f"Finalizar Solicitação #{selected_solicitacao_id}", type="primary"):
                    db_manager.update_status_solicitacao(
                        selected_solicitacao_id,
                        'Finalizada',
                        logged_in_user,
                        "Solicitação finalizada pelo solicitante (todos os componentes utilizados).",
                        data_finalizacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
                    st.success(f"Solicitação #{selected_solicitacao_id} finalizada com sucesso!")
                    st.rerun()

                # Opção para devolver componentes
                with st.expander(f"Devolver Componentes - Solicitação #{selected_solicitacao_id}"):
                    st.write("Insira a quantidade de componentes a serem devolvidos:")
                    editable_devolucao_itens = []
                    for index, item in itens.iterrows():
                        max_devolvivel = item['quantidade_retirada'] - item['quantidade_devolvida']
                        if max_devolvivel > 0:
                            col_sku, col_desc, col_retirada, col_devolver = st.columns([0.2, 0.4, 0.2, 0.2])
                            with col_sku:
                                st.write(item['componente_sku'])
                            with col_desc:
                                st.write(item['componente_desc'])
                            with col_retirada:
                                st.write(f"Retirado: {item['quantidade_retirada']}")
                            with col_devolver:
                                qty_devolver = st.number_input(f"Devolver Qtd", min_value=0, max_value=max_devolvivel,
                                                               value=0, key=f"dev_qty_{item['id']}", label_visibility="collapsed")
                                editable_devolucao_itens.append({
                                    'id': item['id'],
                                    'componente_sku': item['componente_sku'],
                                    'quantidade_devolvida': item['quantidade_devolvida'] + qty_devolver # Soma com o que já foi devolvido
                                })
                    if st.button(f"Registrar Devolução - Solicitação #{selected_solicitacao_id}", type="secondary"):
                        itens_para_devolver = [item for item in editable_devolucao_itens if item['quantidade_devolvida'] > itens.loc[itens['id'] == item['id'], 'quantidade_devolvida'].iloc[0]]
                        if itens_para_devolver:
                            db_manager.update_itens_solicitacao_devolucao(selected_solicitacao_id, itens_para_devolver, logged_in_user)
                            db_manager.update_status_solicitacao(
                                selected_solicitacao_id,
                                'Devolução Pendente Almoxarifado',
                                logged_in_user,
                                "Solicitante registrou componentes para devolução.",
                                data_devolucao_solicitada=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            )
                            st.success(f"Devolução da Solicitação #{selected_solicitacao_id} registrada. Aguardando confirmação do almoxarifado.")
                            st.rerun()
                        else:
                            st.warning("Nenhuma quantidade para devolver foi especificada ou já foi devolvida.")
            else:
                st.warning("Você não tem permissão para registrar devoluções ou finalizar esta solicitação.")

        elif current_status == 'Devolução Pendente Almoxarifado':
            st.info("Aguardando confirmação de devolução pelo Almoxarifado.")
            if auth.has_permission(["Almoxarifado"]):
                st.markdown("---")
                st.subheader("Ação do Almoxarifado")
                if st.button(f"Confirmar Recebimento Devolução - Solicitação #{selected_solicitacao_id}", type="primary"):
                    db_manager.confirm_itens_solicitacao_devolucao_almoxarifado(selected_solicitacao_id, logged_in_user)
                    db_manager.update_status_solicitacao(
                        selected_solicitacao_id,
                        'Devolução Concluída',
                        logged_in_user,
                        "Almoxarifado confirmou o recebimento dos componentes devolvidos.",
                        almoxarife_devolucao_confirmacao=logged_in_user,
                        data_devolucao_confirmada=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        data_finalizacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Finaliza após devolução
                    )
                    st.success(f"Devolução da Solicitação #{selected_solicitacao_id} confirmada pelo Almoxarifado e processo finalizado!")
                    st.rerun()
            else:
                st.warning("Você não tem permissão para confirmar a devolução.")
        else:
            st.info(f"O status atual da solicitação é '{current_status}'. Nenhuma ação adicional disponível aqui.")


def page_devolucoes_almoxarifado():
    if not auth.has_permission(["Almoxarifado"]):
        st.warning("Você não tem permissão para acessar esta página.")
        return

    st.title("Confirmação de Devoluções - Almoxarifado")

    solicitacoes_pendentes_devolucao = db_manager.get_solicitacoes_pendentes_devolucao_almoxarifado()

    if solicitacoes_pendentes_devolucao.empty:
        st.info("Não há devoluções pendentes de confirmação no momento.")
        return

    st.write(f"**{len(solicitacoes_pendentes_devolucao)}** devoluções pendentes de confirmação:")

    for index, solicitacao in solicitacoes_pendentes_devolucao.iterrows():
        st.markdown(f"---")
        st.subheader(f"Devolução da Solicitação #{solicitacao['id']} - Solicitante: {solicitacao['solicitante']}")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Data Solicitação Devolução:** {solicitacao['data_devolucao_solicitada']}")
            st.write(f"**Cliente:** {solicitacao['cliente_nome']}")
            st.write(f"**Equipamento:** {solicitacao['equipamento_nome']}")
        with col2:
            st.write(f"**Pedido Venda:** {solicitacao['pedido_venda']}")
            st.write(f"**Status:** {solicitacao['status_atual']}")

        itens = db_manager.get_itens_solicitacao(solicitacao['id'])
        itens_devolvidos = itens[itens['quantidade_devolvida'] > 0]

        if not itens_devolvidos.empty:
            st.write("Componentes a serem devolvidos:")
            st.dataframe(itens_devolvidos[[
                'componente_sku', 'componente_desc', 'quantidade_retirada', 'quantidade_devolvida'
            ]].rename(columns={
                'componente_sku': 'SKU',
                'componente_desc': 'Descrição',
                'quantidade_retirada': 'Qtd Retirada',
                'quantidade_devolvida': 'Qtd a Devolver'
            }), use_container_width=True)
        else:
            st.info("Nenhum componente registrado para devolução nesta solicitação.")

        if st.button(f"Confirmar Devolução - Solicitação #{solicitacao['id']}", key=f"confirm_dev_{solicitacao['id']}", type="primary"):
            db_manager.confirm_itens_solicitacao_devolucao_almoxarifado(solicitacao['id'], auth.get_logged_in_username())
            db_manager.update_status_solicitacao(
                solicitacao['id'],
                'Devolução Concluída',
                auth.get_logged_in_username(),
                "Almoxarifado confirmou o recebimento dos componentes devolvidos.",
                almoxarife_devolucao_confirmacao=auth.get_logged_in_username(),
                data_devolucao_confirmada=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                data_finalizacao=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Finaliza após devolução
            )
            st.success(f"Devolução da Solicitação #{solicitacao['id']} confirmada e processo finalizado!")
            st.rerun()

def page_historico_solicitacoes():
    if not auth.has_permission(["Tecnico", "Administrativo", "Gestor Garantia", "Almoxarifado"]):
        st.warning("Você não tem permissão para acessar esta página.")
        return
    
    st.title("Histórico de Solicitações")
    all_solicitacoes = db_manager.get_all_solicitacoes()
    
    if all_solicitacoes.empty:
        st.info("Não há solicitações registradas no histórico.")
        return
    
    # Abas para separar as visualizações
    tab_solicitacoes, tab_componentes, tab_eventos = st.tabs([
        "Solicitações", "Componentes Solicitados", "Eventos de Histórico"
    ])
    
    with tab_solicitacoes:
        st.subheader("Solicitações Registradas")
        
        # Filtros para as solicitações
        st.sidebar.subheader("Filtros de Solicitações")
        status_filter = st.sidebar.multiselect("Filtrar por Status", all_solicitacoes['status_atual'].unique(), default=all_solicitacoes['status_atual'].unique())
        solicitante_filter = st.sidebar.multiselect("Filtrar por Solicitante", all_solicitacoes['solicitante'].unique())
        cliente_filter = st.sidebar.multiselect("Filtrar por Cliente", all_solicitacoes['cliente_nome'].unique())
        
        filtered_solicitacoes = all_solicitacoes[all_solicitacoes['status_atual'].isin(status_filter)]
        if solicitante_filter:
            filtered_solicitacoes = filtered_solicitacoes[filtered_solicitacoes['solicitante'].isin(solicitante_filter)]
        if cliente_filter:
            filtered_solicitacoes = filtered_solicitacoes[filtered_solicitacoes['cliente_nome'].isin(cliente_filter)]
        
        st.write(f"Total de solicitações no histórico: **{len(filtered_solicitacoes)}**")
        
        # Botão de download para solicitações filtradas
        if not filtered_solicitacoes.empty:
            df_to_download_solicitacoes = filtered_solicitacoes[[
                'id', 'data_criacao', 'solicitante', 'cliente_nome', 'pedido_venda',
                'equipamento_nome', 'status_atual', 'data_ultimo_status'
            ]].rename(columns={
                'id': 'ID',
                'data_criacao': 'Criação',
                'solicitante': 'Solicitante',
                'cliente_nome': 'Cliente',
                'pedido_venda': 'Pedido',
                'equipamento_nome': 'Equipamento',
                'status_atual': 'Status',
                'data_ultimo_status': 'Última Atualização'
            })
            
            output = io.BytesIO()
            df_to_download_solicitacoes.to_excel(output, index=False, sheet_name='Solicitacoes Filtradas')
            output.seek(0)
            
            st.download_button(
                label="Baixar Solicitações Filtradas (XLSX)",
                data=output.getvalue(),
                file_name="solicitacoes_filtradas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Baixa a tabela de solicitações visível com os filtros aplicados em formato XLSX."
            )
        
        # Exibir tabela principal de solicitações
        st.dataframe(filtered_solicitacoes[[
            'id', 'data_criacao', 'solicitante', 'cliente_nome', 'pedido_venda',
            'equipamento_nome', 'status_atual', 'data_ultimo_status'
        ]].rename(columns={
            'id': 'ID',
            'data_criacao': 'Criação',
            'solicitante': 'Solicitante',
            'cliente_nome': 'Cliente',
            'pedido_venda': 'Pedido',
            'equipamento_nome': 'Equipamento',
            'status_atual': 'Status',
            'data_ultimo_status': 'Última Atualização'
        }), use_container_width=True)
        
        st.markdown("---")
        st.subheader("Detalhes de Solicitação Específica")
        solicitacao_ids = [""] + list(filtered_solicitacoes['id'].astype(str).unique())
        selected_id_str = st.selectbox("Selecione um ID de Solicitação para ver detalhes", solicitacao_ids)
        
        if selected_id_str:
            display_solicitacao_details(int(selected_id_str))
    
    # NOVA ABA - Componentes Solicitados
    with tab_componentes:
        st.subheader("Componentes Solicitados")
        
        # Busca todos os itens de solicitação
        all_itens = db_manager.get_all_itens_solicitacao()
        
        if all_itens.empty:
            st.info("Nenhum componente solicitado encontrado.")
        else:
            # Filtros específicos para componentes
            st.sidebar.subheader("Filtros de Componentes")
            sku_filter = st.sidebar.text_input("Filtrar por SKU (contém)", "")
            desc_filter = st.sidebar.text_input("Filtrar por Descrição (contém)", "")
            
            filtered_itens = all_itens
            
            if sku_filter:
                filtered_itens = filtered_itens[filtered_itens['componente_sku'].str.contains(sku_filter, case=False, na=False)]
            if desc_filter:
                filtered_itens = filtered_itens[filtered_itens['componente_desc'].str.contains(desc_filter, case=False, na=False)]
            
            # Aplicar os mesmos filtros de solicitação para manter consistência
            if status_filter:
                filtered_itens = filtered_itens[filtered_itens['status_atual'].isin(status_filter)]
            if solicitante_filter:
                filtered_itens = filtered_itens[filtered_itens['solicitante'].isin(solicitante_filter)]
            if cliente_filter:
                filtered_itens = filtered_itens[filtered_itens['cliente_nome'].isin(cliente_filter)]
            
            st.write(f"Total de itens encontrados: **{len(filtered_itens)}**")
            
            # Botão de download para componentes filtrados
            if not filtered_itens.empty:
                # Prepara os dados para download - TODAS AS COLUNAS RELEVANTES
                df_to_download_itens = filtered_itens[[
                    'solicitacao_id', 'data_criacao', 'componente_sku', 'componente_desc',
                    'quantidade_solicitada', 'quantidade_liberada', 'quantidade_retirada', 'quantidade_devolvida',
                    'solicitante', 'cliente_nome', 'pedido_venda', 'status_atual',
                    'data_aprovacao', 'data_liberacao', 'data_retirada', 'data_devolucao_confirmada', 'data_finalizacao'
                ]].rename(columns={
                    'solicitacao_id': 'ID Solicitação',
                    'data_criacao': 'Data Criação',
                    'componente_sku': 'SKU',
                    'componente_desc': 'Descrição',
                    'quantidade_solicitada': 'Qtd Solicitada',
                    'quantidade_liberada': 'Qtd Liberada',
                    'quantidade_retirada': 'Qtd Retirada',
                    'quantidade_devolvida': 'Qtd Devolvida',
                    'solicitante': 'Solicitante',
                    'cliente_nome': 'Cliente',
                    'pedido_venda': 'Pedido',
                    'status_atual': 'Status',
                    'data_aprovacao': 'Data Aprovação',
                    'data_liberacao': 'Data Liberação',
                    'data_retirada': 'Data Retirada',
                    'data_devolucao_confirmada': 'Data Devolução',
                    'data_finalizacao': 'Data Finalização'
                })
                
                output_itens = io.BytesIO()
                df_to_download_itens.to_excel(output_itens, index=False, sheet_name='Componentes Solicitados')
                output_itens.seek(0)
                
                st.download_button(
                    label="Baixar Lista de Componentes (XLSX)",
                    data=output_itens.getvalue(),
                    file_name="componentes_solicitados.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Baixa a tabela de componentes com os filtros aplicados em formato XLSX."
                )
            
            # Exibir tabela de componentes - COLUNAS SELECIONADAS PARA A VISUALIZAÇÃO
            # (Mostramos menos colunas na visualização para não sobrecarregar a interface)
            st.dataframe(filtered_itens[[
                'solicitacao_id', 'data_criacao', 'componente_sku', 'componente_desc',
                'quantidade_solicitada', 'quantidade_liberada', 'quantidade_retirada', 'quantidade_devolvida',
                'solicitante', 'cliente_nome', 'status_atual'
            ]].rename(columns={
                'solicitacao_id': 'ID Sol.',
                'data_criacao': 'Data Criação',
                'componente_sku': 'SKU',
                'componente_desc': 'Descrição',
                'quantidade_solicitada': 'Solicitada',
                'quantidade_liberada': 'Liberada',
                'quantidade_retirada': 'Retirada',
                'quantidade_devolvida': 'Devolvida',
                'solicitante': 'Solicitante',
                'cliente_nome': 'Cliente',
                'status_atual': 'Status'
            }), use_container_width=True)
        
        # Opção para visualizar todas as datas
    if st.checkbox("Mostrar todas as datas"):
        st.subheader("Detalhes com todas as datas")
        st.dataframe(filtered_itens[[
            'solicitacao_id', 'componente_sku', 'componente_desc',
            'quantidade_solicitada', 'quantidade_liberada', 'quantidade_retirada', 'quantidade_devolvida',
            'data_criacao', 'data_aprovacao', 'data_liberacao', 'data_retirada', 'data_devolucao_confirmada', 'data_finalizacao'
        ]].rename(columns={
            'solicitacao_id': 'ID Sol.',
            'componente_sku': 'SKU',
            'componente_desc': 'Descrição',
            'quantidade_solicitada': 'Qtd Solicitada',
            'quantidade_liberada': 'Qtd Liberada',
            'quantidade_retirada': 'Qtd Retirada',
            'quantidade_devolvida': 'Qtd Devolvida',
            'data_criacao': 'Data Criação',
            'data_aprovacao': 'Data Aprovação',
            'data_liberacao': 'Data Liberação',
            'data_retirada': 'Data Retirada',  # <- Nome diferente de "Retirada" para evitar duplicação
            'data_devolucao_confirmada': 'Data Devolução',
            'data_finalizacao': 'Data Finalização'
        }), use_container_width=True)
    
    # Histórico de eventos em uma terceira aba
    with tab_eventos:
        st.subheader("Histórico de Eventos")
        
        df_historico_eventos = db_manager.get_all_historico()
        if not df_historico_eventos.empty:
            # Prepara o arquivo para download
            output_historico = io.BytesIO()
            df_historico_eventos.to_excel(output_historico, index=False, sheet_name='Historico de Eventos')
            output_historico.seek(0)
            
            st.download_button(
                label="Baixar Histórico Completo de Eventos (XLSX)",
                data=output_historico.getvalue(),
                file_name="historico_eventos_completo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Baixa todos os registros de eventos de todas as solicitações em formato XLSX."
            )
            
            # Exibir tabela de histórico
            st.dataframe(df_historico_eventos, use_container_width=True)
        else:
            st.info("Nenhum registro de histórico de eventos encontrado.")

# --- Main App Logic ---
def main():
    # Testa as conexões com os bancos de dados externos ao iniciar o app
    # Isso pode ser movido para um script de inicialização se preferir
    # get_protheus_connection()
    # get_dts_connection()

    if not auth.is_logged_in():
        auth.login_page()
    else:
        st.sidebar.title(f"Bem-vindo(a), {st.session_state.username}!")
        st.sidebar.write(f"**Cargo:** {st.session_state.user_role}")

        # Menu de navegação
        st.sidebar.markdown("---")
        st.sidebar.subheader("Navegação")
        pages = {
            "Dashboard": page_dashboard,  # Adicione esta linha
            "Solicitação de Componentes": page_solicitacao,
            "Aprovação de Solicitações": page_aprovacao_solicitacao,
            "Liberação Almoxarifado": page_liberacao_almoxarifado,
            "Confirmação de Retirada/Devolução": page_confirmar_retirada_devolucao, # Página unificada para solicitante
            "Confirmação Devoluções Almoxarifado": page_devolucoes_almoxarifado, # Página para almoxarife confirmar devoluções
            "Histórico de Solicitações": page_historico_solicitacoes,
            "Diagnóstico": page_diagnostico
        }

        # Lógica para lidar com parâmetros de URL para páginas específicas
        query_params = st.query_params.to_dict()
        current_page_name = query_params.get('page', [''])[0]
        
        # Mapeia o nome da página da URL para o nome de exibição no menu
        page_name_map = {
            "dashboard": "Dashboard",  # Adicione esta linha
            "solicitacao": "Solicitação de Componentes",
            "aprovacao_solicitacao": "Aprovação de Solicitações",
            "liberacao_almoxarifado": "Liberação Almoxarifado",
            "confirmar_retirada_devolucao": "Confirmação de Retirada/Devolução",
            "devolucoes_almoxarifado": "Confirmação Devoluções Almoxarifado",
            "historico_solicitacoes": "Histórico de Solicitações",
            "diagnostico": "Diagnóstico",
        }
        
        # Define a página inicial padrão ou a página da URL
        if current_page_name and current_page_name in page_name_map:
            default_page_selection = page_name_map[current_page_name]
        else:
            default_page_selection = "Histórico de Solicitações" # Página padrão se não houver URL ou for inválida

        selected_page = st.sidebar.radio("Ir para:", list(pages.keys()), index=list(pages.keys()).index(default_page_selection))

        # Renderiza a página selecionada
        if selected_page:
            pages[selected_page]()

        st.sidebar.markdown("---")
        if st.sidebar.button("Sair"):
            auth.logout()

if __name__ == "__main__":
    # Garante que o DB local e as tabelas estejam criadas/atualizadas antes de iniciar o app
    from gerar_base_pedidos import inicializar_e_migrar_db
    inicializar_e_migrar_db()
    
    main()

