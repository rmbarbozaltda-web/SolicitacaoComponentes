import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from io import BytesIO
import db_manager
import auth

def calcular_tempo_medio_entre_etapas(df, inicio_col, fim_col, filtro_status=None):
    """
    Calcula o tempo médio entre duas etapas do processo, em horas.
    Retorna o tempo médio e o número de registros usados no cálculo.
    """
    if filtro_status:
        df = df[df['status_atual'].isin(filtro_status)]
    
    # Filtrar apenas registros que têm ambas as datas
    df_filtrado = df.dropna(subset=[inicio_col, fim_col])
    
    if df_filtrado.empty:
        return 0, 0
    
    # Converter strings para datetime se necessário
    if isinstance(df_filtrado[inicio_col].iloc[0], str):
        df_filtrado[inicio_col] = pd.to_datetime(df_filtrado[inicio_col])
    if isinstance(df_filtrado[fim_col].iloc[0], str):
        df_filtrado[fim_col] = pd.to_datetime(df_filtrado[fim_col])
    
    # Calcular a diferença em horas
    df_filtrado['tempo_diff'] = (df_filtrado[fim_col] - df_filtrado[inicio_col]).dt.total_seconds() / 3600
    
    # Filtrar valores negativos ou exageradamente altos (possíveis erros de data)
    df_valido = df_filtrado[(df_filtrado['tempo_diff'] >= 0) & (df_filtrado['tempo_diff'] < 720)]  # menos de 30 dias
    
    if df_valido.empty:
        return 0, 0
        
    tempo_medio = df_valido['tempo_diff'].mean()
    count = len(df_valido)
    
    return tempo_medio, count

def page_dashboard():
    # Verifica permissão - permitem acesso ao dashboard
    roles_permitidos = ["Tecnico", "Administrativo", "Gestor Garantia", "Almoxarifado"]
    if not auth.has_permission(roles_permitidos):
        st.warning("Você não tem permissão para acessar esta página.")
        return

    st.title("Dashboard de Solicitações de Componentes")
    
    # Obtém dados de solicitações e itens
    solicitacoes = db_manager.get_all_solicitacoes()
    if solicitacoes.empty:
        st.info("Não há dados de solicitações para exibir no dashboard.")
        return
    
    # Converte colunas de data para datetime
    date_columns = ['data_criacao', 'data_ultimo_status', 'data_aprovacao', 
                  'data_liberacao', 'data_retirada', 'data_devolucao_solicitada', 
                  'data_devolucao_confirmada', 'data_finalizacao']
    
    for col in date_columns:
        if col in solicitacoes.columns:
            solicitacoes[col] = pd.to_datetime(solicitacoes[col], errors='coerce')
    
    # Obtém itens de solicitações
    itens_solicitados = db_manager.get_all_itens_solicitacao()
    
    # Filtros laterais
    st.sidebar.subheader("Filtros")
    
    # Filtro de período
    st.sidebar.subheader("Período")
    periodo_options = ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias", "Último ano", "Todo o período"]
    periodo_selecionado = st.sidebar.selectbox("Selecione o período", periodo_options)
    
    hoje = datetime.now()
    if periodo_selecionado == "Últimos 7 dias":
        data_inicio = hoje - timedelta(days=7)
    elif periodo_selecionado == "Últimos 30 dias":
        data_inicio = hoje - timedelta(days=30)
    elif periodo_selecionado == "Últimos 90 dias":
        data_inicio = hoje - timedelta(days=90)
    elif periodo_selecionado == "Último ano":
        data_inicio = hoje - timedelta(days=365)
    else:
        data_inicio = solicitacoes['data_criacao'].min()
    
    # Aplica filtro de período
    solicitacoes_periodo = solicitacoes[solicitacoes['data_criacao'] >= data_inicio]
    
    # Filtra itens do mesmo período
    ids_periodo = solicitacoes_periodo['id'].tolist()
    itens_periodo = itens_solicitados[itens_solicitados['solicitacao_id'].isin(ids_periodo)]
    
    # Outros filtros
    all_solicitantes = sorted(solicitacoes['solicitante'].unique().tolist())
    solicitante_selecionado = st.sidebar.multiselect("Filtrar por Solicitante", all_solicitantes)
    
    all_clientes = sorted(solicitacoes['cliente_nome'].unique().tolist())
    cliente_selecionado = st.sidebar.multiselect("Filtrar por Cliente", all_clientes)
    
    all_status = sorted(solicitacoes['status_atual'].unique().tolist())
    status_selecionado = st.sidebar.multiselect("Filtrar por Status", all_status)
    
    # Aplicar filtros adicionais
    if solicitante_selecionado:
        solicitacoes_periodo = solicitacoes_periodo[solicitacoes_periodo['solicitante'].isin(solicitante_selecionado)]
        ids_filtrados = solicitacoes_periodo['id'].tolist()
        itens_periodo = itens_periodo[itens_periodo['solicitacao_id'].isin(ids_filtrados)]
    
    if cliente_selecionado:
        solicitacoes_periodo = solicitacoes_periodo[solicitacoes_periodo['cliente_nome'].isin(cliente_selecionado)]
        ids_filtrados = solicitacoes_periodo['id'].tolist()
        itens_periodo = itens_periodo[itens_periodo['solicitacao_id'].isin(ids_filtrados)]
    
    if status_selecionado:
        solicitacoes_periodo = solicitacoes_periodo[solicitacoes_periodo['status_atual'].isin(status_selecionado)]
        ids_filtrados = solicitacoes_periodo['id'].tolist()
        itens_periodo = itens_periodo[itens_periodo['solicitacao_id'].isin(ids_filtrados)]
    
    # Verifica se ainda temos dados após os filtros
    if solicitacoes_periodo.empty:
        st.warning("Não há dados para exibir com os filtros selecionados.")
        return
    
    # ======= MÉTRICAS PRINCIPAIS =======
    st.header("Métricas Principais")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_solicitacoes = len(solicitacoes_periodo)
        st.metric("Total de Solicitações", total_solicitacoes)
    
    with col2:
        solicitacoes_finalizadas = len(solicitacoes_periodo[solicitacoes_periodo['status_atual'].isin(['Finalizada', 'Devolução Concluída'])])
        taxa_finalizacao = (solicitacoes_finalizadas / total_solicitacoes) * 100 if total_solicitacoes > 0 else 0
        st.metric("Solicitações Finalizadas", f"{solicitacoes_finalizadas} ({taxa_finalizacao:.1f}%)")
    
    with col3:
        solicitacoes_pendentes = len(solicitacoes_periodo[solicitacoes_periodo['status_atual'] == 'Pendente Aprovação'])
        st.metric("Aguardando Aprovação", solicitacoes_pendentes)
    
    with col4:
        solicitacoes_liberacao = len(solicitacoes_periodo[solicitacoes_periodo['status_atual'] == 'Aprovada'])
        st.metric("Aguardando Liberação", solicitacoes_liberacao)
    
    # ======= TEMPOS DE PROCESSO =======
    st.header("Tempos de Processo")
    
    # Calcular tempos médios entre etapas
    tempo_medio_aprovacao, count_aprovacao = calcular_tempo_medio_entre_etapas(
        solicitacoes_periodo, 'data_criacao', 'data_aprovacao', 
        filtro_status=['Aprovada', 'Liberação Parcial', 'Disponível para Retirada', 'Retirada Parcial', 'Retirada Confirmada', 'Finalizada', 'Devolução Pendente Almoxarifado', 'Devolução Concluída']
    )
    
    tempo_medio_liberacao, count_liberacao = calcular_tempo_medio_entre_etapas(
        solicitacoes_periodo, 'data_aprovacao', 'data_liberacao',
        filtro_status=['Liberação Parcial', 'Disponível para Retirada', 'Retirada Parcial', 'Retirada Confirmada', 'Finalizada', 'Devolução Pendente Almoxarifado', 'Devolução Concluída']
    )
    
    tempo_medio_retirada, count_retirada = calcular_tempo_medio_entre_etapas(
        solicitacoes_periodo, 'data_liberacao', 'data_retirada',
        filtro_status=['Retirada Parcial', 'Retirada Confirmada', 'Finalizada', 'Devolução Pendente Almoxarifado', 'Devolução Concluída']
    )
    
    tempo_medio_finalizacao, count_finalizacao = calcular_tempo_medio_entre_etapas(
        solicitacoes_periodo, 'data_criacao', 'data_finalizacao',
        filtro_status=['Finalizada', 'Devolução Concluída']
    )

    # Gráfico de tempo médio de cada etapa
    tempos = [
        {'Etapa': 'Aprovação', 'Tempo Médio (horas)': tempo_medio_aprovacao, 'Registros': count_aprovacao},
        {'Etapa': 'Liberação', 'Tempo Médio (horas)': tempo_medio_liberacao, 'Registros': count_liberacao},
        {'Etapa': 'Retirada', 'Tempo Médio (horas)': tempo_medio_retirada, 'Registros': count_retirada},
        {'Etapa': 'Ciclo Completo', 'Tempo Médio (horas)': tempo_medio_finalizacao, 'Registros': count_finalizacao}
    ]
    
    df_tempos = pd.DataFrame(tempos)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Criar gráfico interativo com plotly
        fig = px.bar(
            df_tempos, 
            x='Etapa', 
            y='Tempo Médio (horas)',
            color='Etapa',
            text='Tempo Médio (horas)',
            title='Tempo Médio por Etapa do Processo (em horas)',
            hover_data=['Registros']
        )
        fig.update_traces(texttemplate='%{y:.1f}', textposition='outside')
        fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Detalhes")
        for tempo in tempos:
            if tempo['Registros'] > 0:
                st.write(f"**{tempo['Etapa']}**")
                tempo_em_horas = tempo['Tempo Médio (horas)']
                # Converter para dias:horas se for grande
                if tempo_em_horas >= 24:
                    dias = int(tempo_em_horas // 24)
                    horas = round(tempo_em_horas % 24, 1)
                    st.write(f"{dias} dias e {horas} horas")
                else:
                    st.write(f"{tempo_em_horas:.1f} horas")
                st.write(f"Baseado em {tempo['Registros']} registros")
                st.write("---")
    
    # ======= STATUS DAS SOLICITAÇÕES =======
    st.header("Status das Solicitações")
    
    # Contagem de solicitações por status
    status_counts = solicitacoes_periodo['status_atual'].value_counts().reset_index()
    status_counts.columns = ['Status', 'Quantidade']
    
    # Gráfico de pizza para status
    fig_status = px.pie(
        status_counts, 
        names='Status', 
        values='Quantidade',
        title='Distribuição por Status',
        hole=0.3
    )
    fig_status.update_traces(textposition='inside', textinfo='percent+label')
    
    # Contagem de solicitações por mês/semana
    solicitacoes_periodo['Mês'] = solicitacoes_periodo['data_criacao'].dt.strftime('%Y-%m')
    solicitacoes_por_mes = solicitacoes_periodo.groupby('Mês').size().reset_index(name='Quantidade')
    solicitacoes_por_mes = solicitacoes_por_mes.sort_values('Mês')
    
    # Gráfico de linha para solicitações ao longo do tempo
    fig_tendencia = px.line(
        solicitacoes_por_mes, 
        x='Mês', 
        y='Quantidade',
        title='Tendência de Solicitações',
        markers=True
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.plotly_chart(fig_status, use_container_width=True)
    
    with col2:
        st.plotly_chart(fig_tendencia, use_container_width=True)
    
    # ======= ANÁLISE DE COMPONENTES =======
    st.header("Análise de Componentes")
    
    if not itens_periodo.empty:
        # Consolidar itens por SKU
        componentes_consolidados = itens_periodo.groupby('componente_sku').agg(
            descricao=('componente_desc', 'first'),
            total_solicitado=('quantidade_solicitada', 'sum'),
            total_liberado=('quantidade_liberada', 'sum'),
            total_retirado=('quantidade_retirada', 'sum'),
            total_devolvido=('quantidade_devolvida', 'sum'),
            contagem=('solicitacao_id', 'count')
        ).reset_index()
        
        # Calcular consumo real (retirado - devolvido)
        componentes_consolidados['consumo_real'] = componentes_consolidados['total_retirado'] - componentes_consolidados['total_devolvido']
        
        # Ordenar por total solicitado para análise ABC
        componentes_consolidados = componentes_consolidados.sort_values('total_solicitado', ascending=False)
        
        # Calcular percentual acumulado para curva ABC
        componentes_consolidados['percentual'] = componentes_consolidados['total_solicitado'] / componentes_consolidados['total_solicitado'].sum()
        componentes_consolidados['percentual_acumulado'] = componentes_consolidados['percentual'].cumsum()
        
        # Determinar classificação ABC
        componentes_consolidados['classe'] = 'C'
        componentes_consolidados.loc[componentes_consolidados['percentual_acumulado'] <= 0.80, 'classe'] = 'A'
        componentes_consolidados.loc[(componentes_consolidados['percentual_acumulado'] > 0.80) & 
                                   (componentes_consolidados['percentual_acumulado'] <= 0.95), 'classe'] = 'B'
        
        # Gráfico de barras para os top componentes
        top_componentes = componentes_consolidados.head(10)
                
        fig_top = px.bar(
            top_componentes,
            x='componente_sku',
            y='total_solicitado',
            color='classe',
            text='total_solicitado',
            title='Top 10 Componentes Mais Solicitados',
            labels={'componente_sku': 'SKU', 'total_solicitado': 'Quantidade Solicitada', 'classe': 'Classe'},
            hover_data=['descricao', 'contagem']
        )
        fig_top.update_traces(texttemplate='%{text:.0f}', textposition='outside')
        
        # Gráfico de Pareto (curva ABC)
        fig_pareto = go.Figure()
        
        # Adicionar barras para quantidades
        fig_pareto.add_trace(go.Bar(
            x=componentes_consolidados['componente_sku'],
            y=componentes_consolidados['total_solicitado'],
            name='Quantidade',
            text=componentes_consolidados['descricao'],
            marker_color=componentes_consolidados['classe'].map({
                'A': 'rgba(255, 0, 0, 0.7)',
                'B': 'rgba(255, 165, 0, 0.7)',
                'C': 'rgba(0, 128, 0, 0.7)'
            })
        ))
        
        # Adicionar linha para percentual acumulado
        fig_pareto.add_trace(go.Scatter(
            x=componentes_consolidados['componente_sku'],
            y=componentes_consolidados['percentual_acumulado'],
            name='% Acumulado',
            yaxis='y2',
            line=dict(color='blue', width=2)
        ))
        
        # Layout com dois eixos y
        fig_pareto.update_layout(
            title='Análise de Pareto (Curva ABC) dos Componentes',
            xaxis=dict(title='SKU do Componente', tickangle=45, tickmode='array', tickvals=[]),
            yaxis=dict(title='Quantidade Solicitada'),
            yaxis2=dict(
                title='Percentual Acumulado',
                overlaying='y',
                side='right',
                range=[0, 1],
                tickformat='.0%'
            ),
            legend=dict(x=0.01, y=0.99),
            hovermode='closest'
        )
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.plotly_chart(fig_pareto, use_container_width=True)
        
        with col2:
            st.plotly_chart(fig_top, use_container_width=True)
        
        # Tabela de componentes por classe ABC
        st.subheader("Classificação ABC de Componentes")
        
        tab1, tab2, tab3 = st.tabs(["Classe A", "Classe B", "Classe C"])
        
        with tab1:
            classe_a = componentes_consolidados[componentes_consolidados['classe'] == 'A']
            if not classe_a.empty:
                st.dataframe(
                    classe_a[['componente_sku', 'descricao', 'total_solicitado', 'total_retirado', 'consumo_real', 'contagem']],
                    hide_index=True,
                    use_container_width=True
                )
                st.write(f"**{len(classe_a)} componentes (Classe A)** representam 80% do volume de solicitações")
            else:
                st.info("Não há componentes na classe A.")
                
        with tab2:
            classe_b = componentes_consolidados[componentes_consolidados['classe'] == 'B']
            if not classe_b.empty:
                st.dataframe(
                    classe_b[['componente_sku', 'descricao', 'total_solicitado', 'total_retirado', 'consumo_real', 'contagem']],
                    hide_index=True,
                    use_container_width=True
                )
                st.write(f"**{len(classe_b)} componentes (Classe B)** representam 15% do volume de solicitações")
            else:
                st.info("Não há componentes na classe B.")
                
        with tab3:
            classe_c = componentes_consolidados[componentes_consolidados['classe'] == 'C']
            if not classe_c.empty:
                st.dataframe(
                    classe_c[['componente_sku', 'descricao', 'total_solicitado', 'total_retirado', 'consumo_real', 'contagem']],
                    hide_index=True,
                    use_container_width=True
                )
                st.write(f"**{len(classe_c)} componentes (Classe C)** representam apenas 5% do volume de solicitações")
            else:
                st.info("Não há componentes na classe C.")
    
        # Análise de componentes sem estoque
        if 'observacoes' in itens_periodo.columns:
            # Identificar componentes sem estoque
            itens_sem_estoque = itens_periodo[~itens_periodo['observacoes'].isnull() & 
                                            itens_periodo['observacoes'].str.contains('sem estoque', case=False, na=False)]
            
            if not itens_sem_estoque.empty:
                st.subheader("Componentes com Problemas de Estoque")
                
                # Agrupar por SKU para ver os mais problemáticos
                sem_estoque_agrupado = itens_sem_estoque.groupby(['componente_sku', 'componente_desc']).size().reset_index(name='ocorrencias')
                sem_estoque_agrupado = sem_estoque_agrupado.sort_values('ocorrencias', ascending=False)
                
                col1, col2 = st.columns([3, 2])
                
                with col1:
                    fig_sem_estoque = px.bar(
                        sem_estoque_agrupado.head(15),
                        x='componente_sku',
                        y='ocorrencias',
                        color='ocorrencias',
                        color_continuous_scale='Reds',
                        title='Top 15 Componentes com Problemas de Estoque',
                        labels={'componente_sku': 'SKU', 'ocorrencias': 'Ocorrências'},
                        hover_data=['componente_desc']
                    )
                    st.plotly_chart(fig_sem_estoque, use_container_width=True)
                    
                with col2:
                    st.write("**Detalhamento de itens sem estoque**")
                    st.dataframe(
                        sem_estoque_agrupado[['componente_sku', 'componente_desc', 'ocorrencias']],
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    total_sem_estoque = len(itens_sem_estoque)
                    total_itens = len(itens_periodo)
                    percentual = (total_sem_estoque / total_itens) * 100 if total_itens > 0 else 0
                    
                    st.info(f"**{total_sem_estoque}** de **{total_itens}** itens solicitados ({percentual:.1f}%) apresentaram problemas de estoque.")

    # ======= ANÁLISE DE FREQUÊNCIA DE COMPONENTES =======
        st.header("Análise de Frequência de Componentes")

        if not itens_periodo.empty:
            # Análise de frequência: quantas solicitações diferentes contêm cada componente
            frequencia_componentes = itens_periodo.groupby(['componente_sku', 'componente_desc']).agg(
                solicitacoes_distintas=('solicitacao_id', 'nunique'),
                quantidade_total=('quantidade_solicitada', 'sum'),
                data_primeira_solicitacao=('data_criacao', 'min'),
                data_ultima_solicitacao=('data_criacao', 'max')
            ).reset_index()
            
            # Calcular o número de dias entre a primeira e última solicitação
            frequencia_componentes['data_primeira_solicitacao'] = pd.to_datetime(frequencia_componentes['data_primeira_solicitacao'])
            frequencia_componentes['data_ultima_solicitacao'] = pd.to_datetime(frequencia_componentes['data_ultima_solicitacao'])
            frequencia_componentes['dias_entre_solicitacoes'] = (frequencia_componentes['data_ultima_solicitacao'] - 
                                                            frequencia_componentes['data_primeira_solicitacao']).dt.days
            
            # Para evitar divisão por zero, substituímos 0 por 1
            frequencia_componentes['dias_entre_solicitacoes'] = frequencia_componentes['dias_entre_solicitacoes'].replace(0, 1)
            
            # Calcular média de solicitações por mês (para comparações mais justas)
            frequencia_componentes['solicitacoes_por_mes'] = (frequencia_componentes['solicitacoes_distintas'] / 
                                                            (frequencia_componentes['dias_entre_solicitacoes'] / 30)).round(2)
            
            # Ordena por número de solicitações distintas
            top_frequencia = frequencia_componentes.sort_values('solicitacoes_distintas', ascending=False).head(15)
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Gráfico de frequência absoluta (número de solicitações distintas)
                fig_freq_abs = px.bar(
                    top_frequencia,
                    x='componente_sku',
                    y='solicitacoes_distintas',
                    title='Top 15 Componentes por Frequência de Solicitação',
                    labels={
                        'componente_sku': 'SKU do Componente',
                        'solicitacoes_distintas': 'Número de Solicitações',
                    },
                    text='solicitacoes_distintas',
                    color='solicitacoes_distintas',
                    color_continuous_scale='Blues',
                    hover_data=['componente_desc', 'quantidade_total']
                )
                fig_freq_abs.update_traces(texttemplate='%{text}', textposition='outside')
                fig_freq_abs.update_layout(yaxis_title='Número de Solicitações Distintas')
                st.plotly_chart(fig_freq_abs, use_container_width=True)
            
            with col2:
                # Gráfico de frequência por mês
                top_freq_mensal = frequencia_componentes.sort_values('solicitacoes_por_mes', ascending=False).head(15)
                fig_freq_mensal = px.bar(
                    top_freq_mensal,
                    x='componente_sku',
                    y='solicitacoes_por_mes',
                    title='Top 15 Componentes por Frequência Mensal',
                    labels={
                        'componente_sku': 'SKU do Componente',
                        'solicitacoes_por_mes': 'Solicitações por Mês',
                    },
                    text='solicitacoes_por_mes',
                    color='solicitacoes_por_mes',
                    color_continuous_scale='Greens',
                    hover_data=['componente_desc', 'quantidade_total', 'solicitacoes_distintas']
                )
                fig_freq_mensal.update_traces(texttemplate='%{text}', textposition='outside')
                fig_freq_mensal.update_layout(yaxis_title='Média de Solicitações por Mês')
                st.plotly_chart(fig_freq_mensal, use_container_width=True)
            
            # Matriz de dispersão: Frequência vs Volume
            st.subheader("Relação entre Frequência e Volume de Solicitação")
            
            # Definir limiares para classificação
            freq_threshold = frequencia_componentes['solicitacoes_distintas'].quantile(0.7)
            vol_threshold = frequencia_componentes['quantidade_total'].quantile(0.7)
            
            # Classificar componentes
            frequencia_componentes['classificacao'] = 'Baixo Volume & Baixa Frequência'
            frequencia_componentes.loc[(frequencia_componentes['solicitacoes_distintas'] >= freq_threshold) & 
                                    (frequencia_componentes['quantidade_total'] >= vol_threshold), 'classificacao'] = 'Alto Volume & Alta Frequência'
            frequencia_componentes.loc[(frequencia_componentes['solicitacoes_distintas'] >= freq_threshold) & 
                                    (frequencia_componentes['quantidade_total'] < vol_threshold), 'classificacao'] = 'Baixo Volume & Alta Frequência'
            frequencia_componentes.loc[(frequencia_componentes['solicitacoes_distintas'] < freq_threshold) & 
                                    (frequencia_componentes['quantidade_total'] >= vol_threshold), 'classificacao'] = 'Alto Volume & Baixa Frequência'
            
            # Gráfico de dispersão
            fig_scatter = px.scatter(
                frequencia_componentes,
                x='solicitacoes_distintas',
                y='quantidade_total',
                color='classificacao',
                title='Matriz de Análise: Frequência vs Volume',
                labels={
                    'solicitacoes_distintas': 'Frequência (Número de Solicitações)',
                    'quantidade_total': 'Volume (Quantidade Total Solicitada)',
                    'classificacao': 'Classificação'
                },
                hover_data=['componente_sku', 'componente_desc', 'solicitacoes_por_mes'],
                size='solicitacoes_por_mes',
                size_max=20,
            )
            
            # Adicionar linhas de referência para os limiares
            fig_scatter.add_shape(
                type="line",
                x0=freq_threshold,
                y0=0,
                x1=freq_threshold,
                y1=frequencia_componentes['quantidade_total'].max(),
                line=dict(color="gray", width=1, dash="dash"),
            )
            fig_scatter.add_shape(
                type="line",
                x0=0,
                y0=vol_threshold,
                x1=frequencia_componentes['solicitacoes_distintas'].max(),
                y1=vol_threshold,
                line=dict(color="gray", width=1, dash="dash"),
            )
            
            st.plotly_chart(fig_scatter, use_container_width=True)
            
            # Tabela com os componentes mais frequentemente solicitados
            with st.expander("Detalhamento de Componentes por Frequência", expanded=False):
                # Criar colunas calculadas para exibição
                frequencia_componentes_display = frequencia_componentes.copy()
                frequencia_componentes_display['média_por_solicitação'] = (
                    frequencia_componentes_display['quantidade_total'] / frequencia_componentes_display['solicitacoes_distintas']
                ).round(2)
                
                st.dataframe(
                    frequencia_componentes_display[[
                        'componente_sku', 'componente_desc', 'solicitacoes_distintas',
                        'solicitacoes_por_mes', 'quantidade_total', 'média_por_solicitação',
                        'classificacao'
                    ]].sort_values('solicitacoes_distintas', ascending=False).rename(columns={
                        'componente_sku': 'SKU',
                        'componente_desc': 'Descrição',
                        'solicitacoes_distintas': 'Nº de Solicitações',
                        'solicitacoes_por_mes': 'Solicitações/Mês',
                        'quantidade_total': 'Quantidade Total',
                        'média_por_solicitação': 'Média por Solicitação',
                        'classificacao': 'Classificação'
                    }),
                    hide_index=True,
                    use_container_width=True
                )
            
            # Nova seção para recorrência de componentes (padrões temporais)
            st.subheader("Recorrência de Componentes ao Longo do Tempo")
            
            # Selecionar apenas os componentes mais frequentes para análise temporal
            top_recorrentes = frequencia_componentes.nlargest(5, 'solicitacoes_distintas')['componente_sku'].tolist()
            
            if top_recorrentes:
                # Preparar dados para visualização temporal
                df_temporal = itens_periodo[itens_periodo['componente_sku'].isin(top_recorrentes)].copy()
                df_temporal['mes_ano'] = pd.to_datetime(df_temporal['data_criacao']).dt.strftime('%Y-%m')
                
                # Agrupar por mês e componente
                recorrencia_mensal = df_temporal.groupby(['mes_ano', 'componente_sku']).agg(
                    contagem=('solicitacao_id', 'nunique'),
                    quantidade_total=('quantidade_solicitada', 'sum'),
                    descricao=('componente_desc', 'first')
                ).reset_index()
                
                # Gráfico de linha para mostrar recorrência ao longo do tempo
                fig_recorrencia = px.line(
                    recorrencia_mensal,
                    x='mes_ano',
                    y='contagem',
                    color='componente_sku',
                    markers=True,
                    title='Recorrência Mensal dos 5 Componentes Mais Frequentes',
                    labels={
                        'mes_ano': 'Mês/Ano',
                        'contagem': 'Número de Solicitações',
                        'componente_sku': 'SKU do Componente'
                    },
                    hover_data=['descricao', 'quantidade_total']
                )
                st.plotly_chart(fig_recorrencia, use_container_width=True)

    # ======= ANÁLISE DE ESTOQUE E NECESSIDADES DE REPOSIÇÃO =======
        st.header("Análise de Estoque e Necessidades de Reposição")

        # Verificar dados disponíveis para análise de estoque
        has_observacoes = 'observacoes' in itens_periodo.columns
        has_stock_info = False  # Flag para controlar se temos alguma informação de estoque

        # Identificar itens com problemas de estoque usando diferentes fontes de dados
        if not itens_periodo.empty:
            itens_sem_estoque = pd.DataFrame()  # Inicializar DataFrame vazio
            
            # Método 1: Usar a coluna 'observacoes' se disponível
            if has_observacoes:
                itens_sem_estoque = itens_periodo[
                    ~itens_periodo['observacoes'].isna() & 
                    itens_periodo['observacoes'].str.contains('sem estoque|não disponível|insuficiente|indisponível', 
                                                            case=False, regex=True, na=False)
                ].copy()
                if not itens_sem_estoque.empty:
                    has_stock_info = True
            
            # Método 2: Se método 1 não retornou resultados, verificar diferença entre solicitado e liberado
            if not has_stock_info and 'quantidade_solicitada' in itens_periodo.columns and 'quantidade_liberada' in itens_periodo.columns:
                # Considerar casos onde o que foi liberado é menor do que o solicitado
                itens_periodo['diferenca_estoque'] = itens_periodo['quantidade_solicitada'] - itens_periodo['quantidade_liberada']
                itens_sem_estoque = itens_periodo[itens_periodo['diferenca_estoque'] > 0].copy()
                
                if not itens_sem_estoque.empty:
                    has_stock_info = True
                    # Adicionar observação sintética se não existir
                    if not has_observacoes:
                        itens_sem_estoque['observacoes'] = "Quantidade liberada menor que a solicitada (possível falta de estoque)"
            
            # Método 3: Usar status da solicitação para inferir problemas de estoque
            if not has_stock_info and 'status_atual' in itens_periodo.columns:
                # Identificar solicitações com status que podem indicar problemas de estoque
                status_problematicos = ['Aprovada Parcialmente', 'Liberação Parcial', 'Não Disponível']
                itens_sem_estoque = itens_periodo[itens_periodo['status_atual'].isin(status_problematicos)].copy()
                
                if not itens_sem_estoque.empty:
                    has_stock_info = True
                    # Adicionar observação sintética
                    if not has_observacoes:
                        itens_sem_estoque['observacoes'] = "Status indica possível problema de estoque"
            
            # Se ainda não temos informações de estoque, verificar se algum componente tem quantidade_liberada = 0
            if not has_stock_info and 'quantidade_liberada' in itens_periodo.columns:
                itens_sem_estoque = itens_periodo[(itens_periodo['quantidade_liberada'] == 0) & 
                                                (itens_periodo['quantidade_solicitada'] > 0)].copy()
                
                if not itens_sem_estoque.empty:
                    has_stock_info = True
                    # Adicionar observação sintética
                    if not has_observacoes:
                        itens_sem_estoque['observacoes'] = "Nenhuma quantidade liberada para item solicitado"
            
            # Se conseguimos identificar itens com problemas de estoque, prosseguir com a análise
            if has_stock_info:
                # Calcular a proporção de solicitações com problemas de estoque
                total_solicitacoes = itens_periodo['solicitacao_id'].nunique()
                solicitacoes_com_falta = itens_sem_estoque['solicitacao_id'].nunique()
                
                # Métricas principais sobre estoque
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if total_solicitacoes > 0:
                        taxa_falta_estoque = (solicitacoes_com_falta / total_solicitacoes) * 100
                        st.metric(
                            "Solicitações com Falta de Estoque", 
                            f"{solicitacoes_com_falta} de {total_solicitacoes}",
                            f"{taxa_falta_estoque:.1f}%"
                        )
                    else:
                        st.metric("Solicitações com Falta de Estoque", "0 de 0", "0%")
                
                with col2:
                    total_itens_analisados = len(itens_periodo)
                    total_itens_sem_estoque = len(itens_sem_estoque)
                    if total_itens_analisados > 0:
                        taxa_itens_sem_estoque = (total_itens_sem_estoque / total_itens_analisados) * 100
                        st.metric(
                            "Itens com Estoque Insuficiente", 
                            f"{total_itens_sem_estoque} de {total_itens_analisados}",
                            f"{taxa_itens_sem_estoque:.1f}%"
                        )
                    else:
                        st.metric("Itens com Estoque Insuficiente", "0 de 0", "0%")
                
                with col3:
                    # Tentar estimar déficit de estoque
                    if 'diferenca_estoque' in itens_sem_estoque.columns:
                        deficit_total = itens_sem_estoque['diferenca_estoque'].sum()
                        st.metric("Déficit Total Estimado", f"{deficit_total:.0f} unidades")
                    elif has_observacoes:
                        # Tentar extrair informações de saldo disponível das observações
                        # Função para extrair valores numéricos de uma string
                        def extract_number(text):
                            import re
                            if pd.isna(text):
                                return None
                            matches = re.findall(r"disponível: (\d+)", str(text))
                            if matches:
                                return int(matches[0])
                            return None
                        
                        # Aplicar extração aos itens sem estoque
                        itens_sem_estoque['saldo_extraido'] = itens_sem_estoque['observacoes'].apply(extract_number)
                        
                        # Calcular déficit para itens onde temos informação do saldo
                        itens_com_saldo = itens_sem_estoque[~itens_sem_estoque['saldo_extraido'].isna()].copy()
                        if not itens_com_saldo.empty:
                            itens_com_saldo['deficit'] = itens_com_saldo['quantidade_solicitada'] - itens_com_saldo['saldo_extraido']
                            deficit_total = itens_com_saldo['deficit'].sum()
                            st.metric("Déficit Total de Estoque", f"{deficit_total:.0f} unidades")
                        else:
                            st.metric("Déficit Total de Estoque", "Não calculável")
                    else:
                        st.metric("Déficit Total de Estoque", "Não calculável")
                
                # 2. Análise de componentes sem estoque
                # Agrupar por SKU para identificar componentes mais problemáticos
                componentes_sem_estoque = itens_sem_estoque.groupby(['componente_sku', 'componente_desc']).agg(
                    ocorrencias=('solicitacao_id', 'count'),
                    solicitacoes_afetadas=('solicitacao_id', 'nunique'),
                    quantidade_solicitada=('quantidade_solicitada', 'sum'),
                    primeira_ocorrencia=('data_criacao', 'min'),
                    ultima_ocorrencia=('data_criacao', 'max')
                ).reset_index()
                
                # Calcular dias desde a primeira ocorrência
                hoje = datetime.now()
                componentes_sem_estoque['primeira_ocorrencia'] = pd.to_datetime(componentes_sem_estoque['primeira_ocorrencia'])
                componentes_sem_estoque['ultima_ocorrencia'] = pd.to_datetime(componentes_sem_estoque['ultima_ocorrencia'])
                componentes_sem_estoque['dias_desde_primeira_ocorrencia'] = (
                    hoje - componentes_sem_estoque['primeira_ocorrencia']
                ).dt.days
                componentes_sem_estoque['persistencia'] = (
                    componentes_sem_estoque['ultima_ocorrencia'] - componentes_sem_estoque['primeira_ocorrencia']
                ).dt.days
                
                # Ordenar por número de ocorrências
                componentes_sem_estoque = componentes_sem_estoque.sort_values('ocorrencias', ascending=False)
                
                # Visualização dos componentes mais problemáticos
                col1, col2 = st.columns([3, 2])
                
                with col1:
                    # Gráfico de ocorrências de falta de estoque
                    top_sem_estoque = componentes_sem_estoque.head(10)
                    
                    fig_sem_estoque = px.bar(
                        top_sem_estoque,
                        x='componente_sku',
                        y='ocorrencias',
                        color='dias_desde_primeira_ocorrencia',
                        title='Top 10 Componentes com Maior Incidência de Falta de Estoque',
                        labels={
                            'componente_sku': 'SKU do Componente',
                            'ocorrencias': 'Ocorrências',
                            'dias_desde_primeira_ocorrencia': 'Dias desde a Primeira Ocorrência'
                        },
                        text='ocorrencias',
                        color_continuous_scale='Reds',
                        hover_data=['componente_desc', 'solicitacoes_afetadas', 'quantidade_solicitada']
                    )
                    fig_sem_estoque.update_traces(texttemplate='%{text}', textposition='outside')
                    fig_sem_estoque.update_layout(xaxis_tickangle=45)
                    st.plotly_chart(fig_sem_estoque, use_container_width=True)
                
                with col2:
                    # Criar uma matriz de criticidade
                    # Eixo X: Frequência (ocorrências)
                    # Eixo Y: Persistência (dias desde primeira ocorrência)
                    fig_criticidade = px.scatter(
                        componentes_sem_estoque,
                        x='ocorrencias',
                        y='dias_desde_primeira_ocorrencia',
                        size='quantidade_solicitada',
                        color='persistencia',
                        title='Matriz de Criticidade de Componentes sem Estoque',
                        labels={
                            'ocorrencias': 'Frequência de Ocorrências',
                            'dias_desde_primeira_ocorrencia': 'Dias desde Primeira Ocorrência',
                            'persistencia': 'Persistência do Problema (dias)',
                            'quantidade_solicitada': 'Quantidade Total Solicitada'
                        },
                        hover_data=['componente_sku', 'componente_desc', 'solicitacoes_afetadas']
                    )
                    st.plotly_chart(fig_criticidade, use_container_width=True)
                
                # 3. Evolução temporal de problemas de estoque
                st.subheader("Evolução Temporal de Problemas de Estoque")
                
                # Agrupar por mês para ver tendência
                itens_sem_estoque['mes_ano'] = pd.to_datetime(itens_sem_estoque['data_criacao']).dt.strftime('%Y-%m')
                evolucao_problemas = itens_sem_estoque.groupby('mes_ano').agg(
                    componentes_afetados=('componente_sku', 'nunique'),
                    ocorrencias=('solicitacao_id', 'count'),
                    solicitacoes_afetadas=('solicitacao_id', 'nunique')
                ).reset_index()
                
                # Garantir ordem cronológica
                evolucao_problemas = evolucao_problemas.sort_values('mes_ano')
                
                # Gráfico de linha para evolução temporal
                fig_evolucao = px.line(
                    evolucao_problemas,
                    x='mes_ano',
                    y=['ocorrencias', 'componentes_afetados', 'solicitacoes_afetadas'],
                    title='Evolução dos Problemas de Estoque ao Longo do Tempo',
                    labels={
                        'mes_ano': 'Mês/Ano',
                        'value': 'Quantidade',
                        'variable': 'Métrica'
                    },
                    markers=True
                )
                st.plotly_chart(fig_evolucao, use_container_width=True)
                
                # 4. Tabela detalhada de componentes sem estoque
                st.subheader("Detalhamento de Componentes sem Estoque")

                # Verificar se existem componentes para análise
                if not componentes_sem_estoque.empty:
                    # Calcular indicadores de prioridade para reposição
                    try:
                        componentes_sem_estoque['prioridade_reposicao'] = (
                            componentes_sem_estoque['ocorrencias'] * 
                            componentes_sem_estoque['quantidade_solicitada'] * 
                            (1 + componentes_sem_estoque['dias_desde_primeira_ocorrencia'] / 30)
                        ).round(2)
                        
                        # Categorizar prioridade
                        if len(componentes_sem_estoque) > 3:  # Se tivermos dados suficientes para criar quartis
                            try:
                                componentes_sem_estoque['categoria_prioridade'] = pd.qcut(
                                    componentes_sem_estoque['prioridade_reposicao'],
                                    q=3,
                                    labels=['Baixa', 'Média', 'Alta'],
                                    duplicates='drop'
                                )
                            except ValueError:  # Se houver valores duplicados ou outros problemas
                                # Abordagem alternativa com cut
                                min_val = componentes_sem_estoque['prioridade_reposicao'].min()
                                max_val = componentes_sem_estoque['prioridade_reposicao'].max()
                                if min_val < max_val:  # Garantir que temos um intervalo válido
                                    bins = [min_val, min_val + (max_val-min_val)/3, min_val + 2*(max_val-min_val)/3, max_val]
                                    componentes_sem_estoque['categoria_prioridade'] = pd.cut(
                                        componentes_sem_estoque['prioridade_reposicao'],
                                        bins=bins,
                                        labels=['Baixa', 'Média', 'Alta'],
                                        include_lowest=True
                                    )
                                else:
                                    # Se todos os valores são iguais
                                    componentes_sem_estoque['categoria_prioridade'] = 'Média'
                        else:  # Para poucos dados, usamos uma abordagem mais simples
                            if len(componentes_sem_estoque) > 1:
                                limite_alto = componentes_sem_estoque['prioridade_reposicao'].quantile(0.66) 
                                limite_medio = componentes_sem_estoque['prioridade_reposicao'].quantile(0.33)
                                
                                componentes_sem_estoque['categoria_prioridade'] = 'Média'
                                componentes_sem_estoque.loc[componentes_sem_estoque['prioridade_reposicao'] >= limite_alto, 'categoria_prioridade'] = 'Alta'
                                componentes_sem_estoque.loc[componentes_sem_estoque['prioridade_reposicao'] <= limite_medio, 'categoria_prioridade'] = 'Baixa'
                            else:
                                # Se temos apenas um componente
                                componentes_sem_estoque['categoria_prioridade'] = 'Alta'
                    
                    except Exception as e:
                        st.warning(f"Não foi possível calcular a prioridade de reposição: {e}")
                        # Criar colunas padrão para evitar erros
                        componentes_sem_estoque['prioridade_reposicao'] = 0
                        componentes_sem_estoque['categoria_prioridade'] = 'Não calculada'
                    
                    # Colunas a serem mostradas
                    colunas_exibicao = [
                        'componente_sku', 'componente_desc', 'ocorrencias', 
                        'solicitacoes_afetadas', 'quantidade_solicitada',
                        'dias_desde_primeira_ocorrencia'
                    ]
                    
                    # Adicionar colunas de prioridade se existirem
                    if 'persistencia' in componentes_sem_estoque.columns:
                        colunas_exibicao.append('persistencia')
                    if 'prioridade_reposicao' in componentes_sem_estoque.columns:
                        colunas_exibicao.append('prioridade_reposicao')
                    if 'categoria_prioridade' in componentes_sem_estoque.columns:
                        colunas_exibicao.append('categoria_prioridade')
                    
                    # Mapeamento de nomes de colunas
                    nome_colunas = {
                        'componente_sku': 'SKU',
                        'componente_desc': 'Descrição',
                        'ocorrencias': 'Ocorrências',
                        'solicitacoes_afetadas': 'Solicitações Afetadas',
                        'quantidade_solicitada': 'Qtd. Solicitada',
                        'dias_desde_primeira_ocorrencia': 'Dias desde 1ª Ocorrência',
                        'persistencia': 'Persistência (dias)',
                        'prioridade_reposicao': 'Índice de Prioridade',
                        'categoria_prioridade': 'Prioridade'
                    }
                    
                    # Exibir tabela com informações e indicador de prioridade
                    if 'prioridade_reposicao' in componentes_sem_estoque.columns:
                        df_exibicao = componentes_sem_estoque[colunas_exibicao].sort_values('prioridade_reposicao', ascending=False)
                    else:
                        df_exibicao = componentes_sem_estoque[colunas_exibicao].sort_values('ocorrencias', ascending=False)
                    
                    # Renomear colunas para exibição
                    colunas_renomeadas = {col: nome_colunas.get(col, col) for col in colunas_exibicao}
                    df_exibicao = df_exibicao.rename(columns=colunas_renomeadas)
                    
                    st.dataframe(
                        df_exibicao,
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # 5. Recomendações de Reposição
                    st.subheader("Recomendações de Reposição")
                    
                    # Componentes de alta prioridade (se categoria_prioridade existe)
                    if 'categoria_prioridade' in componentes_sem_estoque.columns:
                        componentes_alta_prioridade = componentes_sem_estoque[
                            componentes_sem_estoque['categoria_prioridade'] == 'Alta'
                        ].copy()
                        
                        if not componentes_alta_prioridade.empty:
                            # Calcular quantidade recomendada para reposição
                            # Baseada na demanda histórica + margem de segurança
                            componentes_alta_prioridade['qtd_recomendada'] = (
                                componentes_alta_prioridade['quantidade_solicitada'] * 1.2
                            ).round(0).astype(int)
                            
                            st.write("#### Componentes com Prioridade Alta para Reposição")
                            st.dataframe(
                                componentes_alta_prioridade[[
                                    'componente_sku', 'componente_desc', 
                                    'quantidade_solicitada', 'qtd_recomendada',
                                    'solicitacoes_afetadas', 'dias_desde_primeira_ocorrencia'
                                ]].rename(columns={
                                    'componente_sku': 'SKU',
                                    'componente_desc': 'Descrição',
                                    'quantidade_solicitada': 'Qtd. Solicitada',
                                    'qtd_recomendada': 'Qtd. Recomendada',
                                    'solicitacoes_afetadas': 'Solicitações Afetadas',
                                    'dias_desde_primeira_ocorrencia': 'Dias sem Estoque'
                                }),
                                hide_index=True,
                                use_container_width=True
                            )
                            
                            # Opção para download da lista de reposição
                            output_reposicao = BytesIO()
                            with pd.ExcelWriter(output_reposicao, engine='xlsxwriter') as writer:
                                componentes_alta_prioridade.to_excel(writer, sheet_name='Reposicao_Prioritaria', index=False)
                                componentes_sem_estoque.to_excel(writer, sheet_name='Todos_Problemas_Estoque', index=False)
                            
                            st.download_button(
                                label="Download Lista de Reposição (Excel)",
                                data=output_reposicao.getvalue(),
                                file_name=f"lista_reposicao_priorizada_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.info("Não foram identificados componentes com prioridade alta para reposição.")
                    else:
                        # Caso não tenha sido possível categorizar a prioridade
                        # Mostrar os componentes mais solicitados como recomendação
                        top_componentes = componentes_sem_estoque.nlargest(5, 'ocorrencias').copy()
                        
                        if not top_componentes.empty:
                            # Calcular quantidade recomendada para reposição
                            top_componentes['qtd_recomendada'] = (
                                top_componentes['quantidade_solicitada'] * 1.2
                            ).round(0).astype(int)
                            
                            st.write("#### Componentes Recomendados para Reposição (baseado em ocorrências)")
                            st.dataframe(
                                top_componentes[[
                                    'componente_sku', 'componente_desc', 
                                    'quantidade_solicitada', 'qtd_recomendada',
                                    'ocorrencias'
                                ]].rename(columns={
                                    'componente_sku': 'SKU',
                                    'componente_desc': 'Descrição',
                                    'quantidade_solicitada': 'Qtd. Solicitada',
                                    'qtd_recomendada': 'Qtd. Recomendada',
                                    'ocorrencias': 'Ocorrências'
                                }),
                                hide_index=True,
                                use_container_width=True
                            )
                else:
                    st.info("Não foram identificados componentes com problemas de estoque para análise detalhada.")
    
    # ======= DESEMPENHO POR SOLICITANTE =======
    st.header("Desempenho por Solicitante")
    
    # Contagem de solicitações por solicitante
    solicitacoes_por_usuario = solicitacoes_periodo.groupby('solicitante').size().reset_index(name='quantidade')
    solicitacoes_por_usuario = solicitacoes_por_usuario.sort_values('quantidade', ascending=False)
    
    # Tempo médio de ciclo completo por solicitante
    tempo_ciclo_por_solicitante = []
    for solicitante in solicitacoes_por_usuario['solicitante']:
        df_sol = solicitacoes_periodo[solicitacoes_periodo['solicitante'] == solicitante]
        tempo_medio, count = calcular_tempo_medio_entre_etapas(df_sol, 'data_criacao', 'data_finalizacao',
                                                          filtro_status=['Finalizada', 'Devolução Concluída'])
        
        # Converter para dias para melhor visualização
        tempo_medio_dias = tempo_medio / 24 if tempo_medio > 0 else 0
        
        tempo_ciclo_por_solicitante.append({
            'solicitante': solicitante,
            'tempo_medio_dias': tempo_medio_dias,
            'solicitacoes_finalizadas': count
        })
    
    df_tempo_solicitante = pd.DataFrame(tempo_ciclo_por_solicitante)
    
    # Mesclar com contagem total de solicitações
    df_desempenho_solicitante = pd.merge(
        solicitacoes_por_usuario,
        df_tempo_solicitante,
        on='solicitante',
        how='left'
    )
    
    # Calcular taxa de finalização
    df_desempenho_solicitante['taxa_finalizacao'] = (
        df_desempenho_solicitante['solicitacoes_finalizadas'] / 
        df_desempenho_solicitante['quantidade']
    ) * 100
    
    # Ordenar por quantidade de solicitações
    df_desempenho_solicitante = df_desempenho_solicitante.sort_values('quantidade', ascending=False)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de quantidade de solicitações por usuário
        fig_qtd_usuario = px.bar(
            df_desempenho_solicitante,
            x='solicitante',
            y='quantidade',
            title='Quantidade de Solicitações por Solicitante',
            color='quantidade',
            labels={'solicitante': 'Solicitante', 'quantidade': 'Nº de Solicitações'},
            text_auto=True
        )
        fig_qtd_usuario.update_layout(xaxis_tickangle=45)
        st.plotly_chart(fig_qtd_usuario, use_container_width=True)
        
    with col2:
        # Gráfico de tempo médio de ciclo por usuário (apenas para quem tem solicitações finalizadas)
        df_tempo_finalizadas = df_desempenho_solicitante[df_desempenho_solicitante['solicitacoes_finalizadas'] > 0]
        
        if not df_tempo_finalizadas.empty:
            fig_tempo_usuario = px.bar(
                df_tempo_finalizadas,
                x='solicitante',
                y='tempo_medio_dias',
                title='Tempo Médio de Ciclo por Solicitante (dias)',
                color='solicitacoes_finalizadas',
                labels={
                    'solicitante': 'Solicitante', 
                    'tempo_medio_dias': 'Tempo Médio (dias)',
                    'solicitacoes_finalizadas': 'Solicitações Finalizadas'
                },
                text_auto=True
            )
            fig_tempo_usuario.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig_tempo_usuario, use_container_width=True)
        else:
            st.info("Não há solicitações finalizadas para mostrar o tempo médio de ciclo.")
    
    # Tabela de desempenho por solicitante
    st.subheader("Tabela de Desempenho por Solicitante")
    st.dataframe(
        df_desempenho_solicitante.rename(columns={
            'solicitante': 'Solicitante',
            'quantidade': 'Total de Solicitações',
            'solicitacoes_finalizadas': 'Finalizadas',
            'tempo_medio_dias': 'Tempo Médio (dias)',
            'taxa_finalizacao': 'Taxa de Finalização (%)'
        }),
        hide_index=True,
        use_container_width=True
    )
    
    # ======= DOWNLOAD DOS DADOS =======
    st.header("Exportar Dados")
    
    col1, col2 = st.columns(2)
    
    # Preparar dados para download
    output1 = BytesIO()
    output2 = BytesIO()
    
    # Excel para solicitações
    with pd.ExcelWriter(output1, engine='xlsxwriter') as writer:
        solicitacoes_periodo.to_excel(writer, sheet_name='Solicitacoes', index=False)
        
    # Excel para análise de componentes
    with pd.ExcelWriter(output2, engine='xlsxwriter') as writer:
        componentes_consolidados.to_excel(writer, sheet_name='Componentes', index=False)
        df_desempenho_solicitante.to_excel(writer, sheet_name='Desempenho_Solicitante', index=False)
    
    with col1:
        st.download_button(
            label="Download Relatório de Solicitações",
            data=output1.getvalue(),
            file_name="relatorio_solicitacoes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col2:
        st.download_button(
            label="Download Análise de Componentes",
            data=output2.getvalue(),
            file_name="analise_componentes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
