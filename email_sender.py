import smtplib
import streamlit as st
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Configurações de e-mail
EMAIL_SENDER = "garantitopema@gmail.com"
EMAIL_APP_PASSWORD = "lyticsntlgwnodkp" # Senha de aplicativo gerada para o Gmail
EMAIL_ALMOXARIFADO = "rmbarboza.ltda@gmail.com"

# Função base para enviar e-mails (reutilizável)
def send_email(recipient_email, subject, html_content):
    """
    Função base para enviar e-mails com conteúdo HTML.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient_email
    
    part1 = MIMEText(html_content, "html")
    msg.attach(part1)
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipient_email, msg.as_string())
        print(f"E-mail enviado com sucesso para {recipient_email}.")
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail para {recipient_email}: {e}")
        return False

def send_email_to_almoxarifado(solicitacao_id, solicitacao_data, itens_solicitados, app_link_base):
    """
    Envia um e-mail formatado em HTML para o responsável do almoxarifado
    notificando sobre uma nova solicitação aprovada.
    """
    # Link direto para a página de liberação no app
    # O link deve apontar para a página correta no seu Streamlit app,
    # passando o ID da solicitação como parâmetro.
    # Ex: http://localhost:8501/?page=liberacao_almoxarifado&solicitacao_id=123
    liberacao_link = f"{app_link_base}?page=liberacao_almoxarifado&solicitacao_id={solicitacao_id}"
    
    # Construção do corpo do e-mail em HTML
    html_content = f"""
    <html>
    <head></head>
    <body>
        <p>Prezado(a) responsável do Almoxarifado,</p>
        <p>Uma nova solicitação de componentes foi <strong>APROVADA</strong> e está aguardando sua liberação.</p>
        <h3>Detalhes da Solicitação #{solicitacao_id}:</h3>
        <ul>
            <li><strong>Data da Solicitação:</strong> {solicitacao_data['data_criacao']}</li>
            <li><strong>Solicitante:</strong> {solicitacao_data['solicitante']} ({solicitacao_data['solicitante_email']})</li>
            <li><strong>Cliente:</strong> {solicitacao_data['cliente_nome']} ({solicitacao_data['cliente_cnpj']})</li>
            <li><strong>Pedido de Venda:</strong> {solicitacao_data['pedido_venda']}</li>
            <li><strong>Equipamento:</strong> {solicitacao_data['equipamento_nome']} (SKU: {solicitacao_data['equipamento_sku']})</li>
            <li><strong>Centro de Custo:</strong> {solicitacao_data.get('centro_custo', 'Não especificado')} ({solicitacao_data.get('setor', 'Não especificado')})</li>
        </ul>
        <h4>Componentes Solicitados:</h4>
        <table border="1" style="width:100%; border-collapse: collapse;">
            <thead>
                <tr style="background-color:#f2f2f2;">
                    <th style="padding: 8px; text-align: left;">SKU Componente</th>
                    <th style="padding: 8px; text-align: left;">Descrição</th>
                    <th style="padding: 8px; text-align: left;">Quantidade</th>
                </tr>
            </thead>
            <tbody>
    """
    for item in itens_solicitados:
        html_content += f"""
                <tr>
                    <td style="padding: 8px; text-align: left;">{item['componente_sku']}</td>
                    <td style="padding: 8px; text-align: left;">{item['componente_desc']}</td>
                    <td style="padding: 8px; text-align: left;">{item['quantidade_solicitada']}</td>
                </tr>
        """
    html_content += f"""
            </tbody>
        </table>
        <p>Por favor, separe as peças e clique no link abaixo para registrar a disponibilidade no sistema:</p>
        <p><a href="{liberacao_link}" style="display: inline-block; padding: 10px 20px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px;">Acessar Solicitação no App para Liberação</a></p>
        <p>Atenciosamente,</p>
        <p>Equipe de Garantia</p>
    </body>
    </html>
    """
    
    return send_email(EMAIL_ALMOXARIFADO, f"Nova Solicitação de Componentes Aprovada - Pedido #{solicitacao_id}", html_content)

def send_email_to_gestor(solicitacao_id, solicitacao_info, itens_info, app_base_url):
    """
    Envia e-mail para o gestor responsável informando sobre nova solicitação pendente de aprovação.
    """
    import db_manager  # Importação local para evitar importação circular
    
    centro_custo = solicitacao_info.get('centro_custo', '')
    setor = solicitacao_info.get('setor', 'Não especificado')
    
    # Buscar informações do gestor responsável pelo centro de custo
    gestor_info = db_manager.get_gestor_by_centro_custo(centro_custo)
    
    if not gestor_info:
        st.warning(f"Não foi encontrado gestor para o centro de custo {centro_custo}")
        return False
    
    gestor_email = gestor_info.get('email')
    gestor_nome = gestor_info.get('gestor', 'Gestor')
    
    if not gestor_email:
        st.warning(f"E-mail do gestor não cadastrado para centro de custo {centro_custo}")
        return False
    
    # Link direto para a página de aprovação no app
    aprovacao_link = f"{app_base_url}?page=aprovacao_solicitacao&solicitacao_id={solicitacao_id}"
    
    # Preparação da tabela de itens solicitados
    itens_html = ""
    for item in itens_info:
        status_estoque = "✅ Em estoque" if item.get('tem_estoque', True) else "❌ Sem estoque"
        itens_html += f"""
        <tr>
            <td style="padding: 8px; text-align: left;">{item['sku']}</td>
            <td style="padding: 8px; text-align: left;">{item['descricao']}</td>
            <td style="padding: 8px; text-align: left;">{item.get('quantidade', 0)}</td>
            <td style="padding: 8px; text-align: left;">{status_estoque}</td>
        </tr>
        """
    
    # Conteúdo HTML do e-mail
    html_content = f"""
    <html>
    <head></head>
    <body>
        <p>Prezado(a) {gestor_nome},</p>
        <p>Uma nova solicitação de componentes foi registrada e está <strong>aguardando sua aprovação</strong>.</p>
        
        <h3>Detalhes da Solicitação #{solicitacao_id}:</h3>
        <ul>
            <li><strong>Data da Solicitação:</strong> {solicitacao_info.get('data_criacao', 'N/A')}</li>
            <li><strong>Solicitante:</strong> {solicitacao_info.get('solicitante', 'N/A')}</li>
            <li><strong>Cliente:</strong> {solicitacao_info.get('cliente_nome', 'N/A')}</li>
            <li><strong>Centro de Custo:</strong> {centro_custo} ({setor})</li>
            <li><strong>Pedido de Venda:</strong> {solicitacao_info.get('pedido_venda', 'N/A')}</li>
            <li><strong>Equipamento:</strong> {solicitacao_info.get('equipamento_nome', 'N/A')}</li>
        </ul>
        
        <h4>Componentes Solicitados:</h4>
        <table border="1" style="width:100%; border-collapse: collapse;">
            <thead>
                <tr style="background-color:#f2f2f2;">
                    <th style="padding: 8px; text-align: left;">SKU</th>
                    <th style="padding: 8px; text-align: left;">Descrição</th>
                    <th style="padding: 8px; text-align: left;">Quantidade</th>
                    <th style="padding: 8px; text-align: left;">Status Estoque</th>
                </tr>
            </thead>
            <tbody>
                {itens_html}
            </tbody>
        </table>
        
        <p>Para aprovar ou rejeitar esta solicitação, acesse o sistema clicando no botão abaixo:</p>
        <p><a href="{aprovacao_link}" style="display: inline-block; padding: 10px 20px; background-color: #007BFF; color: white; text-decoration: none; border-radius: 5px;">Avaliar Solicitação</a></p>
        
        <p>Atenciosamente,</p>
        <p>Sistema de Gestão de Solicitações de Componentes</p>
    </body>
    </html>
    """
    
    return send_email(gestor_email, f"Nova Solicitação #{solicitacao_id} Pendente de Aprovação", html_content)

# Teste de envio de e-mail (opcional)
if __name__ == '__main__':
    print("Testando envio de e-mail...")
    sample_solicitacao_data = {
        'id': 999,
        'data_criacao': '2025-09-09 10:00:00',
        'solicitante': 'Teste Solicitante',
        'solicitante_email': 'teste.solicitante@empresa.com',
        'cliente_cnpj': '00.000.000/0001-00',
        'cliente_nome': 'Cliente Teste LTDA',
        'pedido_venda': 'PDV-12345',
        'equipamento_sku': 'EQP-XYZ',
        'equipamento_nome': 'Equipamento de Teste',
        'centro_custo': '040023',
        'setor': 'Garantia'
    }
    sample_itens = [
        {'componente_sku': 'COMP-001', 'componente_desc': 'Motor Elétrico', 'quantidade_solicitada': 2},
        {'componente_sku': 'COMP-002', 'componente_desc': 'Sensor de Temperatura', 'quantidade_solicitada': 5}
    ]
    
    # Você precisará definir o app_link_base correto para o seu ambiente
    # Por exemplo, se estiver rodando localmente: "http://localhost:8501"
    # Se estiver em um servidor: "http://seu_servidor:8501"
    app_link_base = "http://localhost:8501"
    
    # Teste de e-mail para o almoxarifado
    success_almox = send_email_to_almoxarifado(
        solicitacao_id=sample_solicitacao_data['id'],
        solicitacao_data=sample_solicitacao_data,
        itens_solicitados=sample_itens,
        app_link_base=app_link_base
    )
    
    if success_almox:
        print("E-mail de teste para o almoxarifado enviado com sucesso!")
    else:
        print("Falha no envio do e-mail de teste para o almoxarifado.")
    
    # Nota: O teste da função send_email_to_gestor requer o db_manager implementado
    # e um centro de custo válido no banco de dados
    # Para testar, descomente as linhas abaixo após implementar as outras partes
    
    # success_gestor = send_email_to_gestor(
    #     solicitacao_id=sample_solicitacao_data['id'],
    #     solicitacao_info=sample_solicitacao_data,
    #     itens_info=[
    #         {'sku': 'COMP-001', 'descricao': 'Motor Elétrico', 'quantidade': 2, 'tem_estoque': True},
    #         {'sku': 'COMP-002', 'descricao': 'Sensor de Temperatura', 'quantidade': 5, 'tem_estoque': False}
    #     ],
    #     app_base_url=app_link_base
    # )
    # 
    # if success_gestor:
    #     print("E-mail de teste para o gestor enviado com sucesso!")
    # else:
    #     print("Falha no envio do e-mail de teste para o gestor.")

