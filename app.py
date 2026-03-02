from flask import Flask, request, jsonify
import requests
import os
import time
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

# CONFIGURACOES GERAIS
INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")
WEBHOOK_LIDERANCA = os.environ.get("SLACK_WEBHOOK_1")
WEBHOOK_GERAL = os.environ.get("SLACK_WEBHOOK_2")

# CREDENCIAIS SEGURAS DO GOOGLE
GOOGLE_JSON_KEY = os.environ.get("GOOGLE_JSON_KEY")
PLANILHA_ID = os.environ.get("PLANILHA_ID")

LIDERANCA_TAGS = "<@U06KNLC1Y9F> <@U08CZ58DDAA>"

# MEMORIAS DO SISTEMA
CACHE_AGENTES = {}
LAST_UPDATE = 0
CACHE_TIMEOUT = 600
STATUS_EM_TEMPO_REAL = {}

def hora_atual():
    return datetime.now().strftime("%H:%M:%S")

def get_agents_map():
    global CACHE_AGENTES, LAST_UPDATE, STATUS_EM_TEMPO_REAL
    agora = time.time()
    
    if CACHE_AGENTES and (agora - LAST_UPDATE < CACHE_TIMEOUT):
        return CACHE_AGENTES

    if not GOOGLE_JSON_KEY or not PLANILHA_ID:
        print(f"[{hora_atual()}] Aviso: Credenciais do Google não configuradas.")
        return CACHE_AGENTES

    print(f"[{hora_atual()}] A ler dados da Planilha Google...")
    
    try:
        credenciais_dict = json.loads(GOOGLE_JSON_KEY)
        escopos = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credenciais = Credentials.from_service_account_info(credenciais_dict, scopes=escopos)
        cliente = gspread.authorize(credenciais)
        
        planilha = cliente.open_by_key(PLANILHA_ID).sheet1
        registos = planilha.get_all_records()
        
        novo_mapa = {}
        for linha in registos:
            email = str(linha.get('Email', '')).strip()
            intercom_id = str(linha.get('Intercom_ID', '')).strip()
            inicio = str(linha.get('Inicio', '')).strip()
            fim = str(linha.get('Fim', '')).strip()
            
            if email and intercom_id:
                novo_mapa[email] = {
                    "id": intercom_id,
                    "inicio": inicio if inicio else None,
                    "fim": fim if fim else None
                }
                
                # Inicia todos como Aguardando status
                if email not in STATUS_EM_TEMPO_REAL:
                    nome_inicial = email.split('.')[0].capitalize()
                    STATUS_EM_TEMPO_REAL[email] = {
                        "nome": nome_inicial,
                        "status": "Aguardando status ⚪",
                        "inicio": None
                    }
        
        CACHE_AGENTES = novo_mapa
        LAST_UPDATE = agora
        
        print(f"[{hora_atual()}] Planilha carregada: {len(CACHE_AGENTES)} agentes.")
        return CACHE_AGENTES

    except Exception as e:
        print(f"[{hora_atual()}] Erro ao ler planilha: {e}")
        return CACHE_AGENTES

def automacao_ativa_agora(email, agents_map):
    agente = agents_map.get(email)
    if not agente: 
        return False
        
    inicio = agente.get("inicio")
    fim = agente.get("fim")
    
    if not inicio or not fim:
        return True
        
    fuso_br = timezone(timedelta(hours=-3))
    hora_agora = datetime.now(fuso_br).strftime("%H:%M")
    
    return inicio <= hora_agora <= fim

def set_intercom_status(admin_id, is_away):
    url = f"https://api.intercom.io/admins/{admin_id}/away"
    headers = {
        "Authorization": f"Bearer {INTERCOM_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {"away_mode_enabled": is_away, "away_mode_reassign": False}
    
    try:
        response = requests.put(url, json=payload, headers=headers)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"[{hora_atual()}] Erro Intercom: {e}")
        return False

def enviar_para_slack(url, mensagem):
    if not url: return
    try:
        requests.post(url, json={"text": mensagem})
    except Exception as e:
        print(f"[{hora_atual()}] Erro Slack: {e}")

@app.route('/webhook-aircall', methods=['POST'])
def aircall_hook():
    data = request.json
    
    if not data or 'event' not in data:
        return jsonify({"status": "ignored"}), 200

    AGENTS_MAP = get_agents_map()
    event_type = data['event']
    call_data = data.get('data', {})

    # 1. TRATA TRANSFERENCIAS
    if event_type == 'call.transferred':
        quem_transferiu = call_data.get('transferred_by')
        if quem_transferiu:
            email_by = quem_transferiu.get('email')
            name_by = quem_transferiu.get('name', 'Agente')
            dados_by = AGENTS_MAP.get(email_by)
            id_by = dados_by.get("id") if dados_by else None
            
            if id_by and automacao_ativa_agora(email_by, AGENTS_MAP):
                if set_intercom_status(id_by, False):
                    STATUS_EM_TEMPO_REAL[email_by] = {"nome": name_by, "status": "Disponível 🟢", "inicio": None}
                    enviar_para_slack(WEBHOOK_LIDERANCA, f"🟢 *{name_by}* transferiu a chamada e ficou *Online*.")
                    enviar_para_slack(WEBHOOK_GERAL, f"🟢 *{name_by}* transferiu a chamada e ficou *Online*.")
        
        quem_recebeu = call_data.get('transferred_to')
        if quem_recebeu:
            email_to = quem_recebeu.get('email')
            name_to = quem_recebeu.get('name', 'Agente')
            dados_to = AGENTS_MAP.get(email_to)
            id_to = dados_to.get("id") if dados_to else None
            
            if id_to and automacao_ativa_agora(email_to, AGENTS_MAP):
                if set_intercom_status(id_to, True):
                    STATUS_EM_TEMPO_REAL[email_to] = {"nome": name_to, "status": "Em Ligação 🔴", "inicio": datetime.now()}
                    enviar_para_slack(WEBHOOK_LIDERANCA, f"🔴 {LIDERANCA_TAGS}: *{name_to}* recebeu transferência e ficou *Ausente*.")
                    enviar_para_slack(WEBHOOK_GERAL, f"🔴 *{name_to}* recebeu transferência e ficou *Ausente*.")

        return jsonify({"status": "success"}), 200

    # 2. TRATA MUDANCAS DE STATUS (PAUSA E DISPONIVEL)
    if event_type in ['user.opened', 'user.closed']:
        user_email = call_data.get('email')
        user_name = call_data.get('name', 'Agente')
        
        if user_email in AGENTS_MAP:
            if event_type == 'user.opened':
                STATUS_EM_TEMPO_REAL[user_email] = {"nome": user_name, "status": "Disponível 🟢", "inicio": None}
                print(f"[{hora_atual()}] {user_name} ficou DISPONÍVEL.")
            
            elif event_type == 'user.closed':
                STATUS_EM_TEMPO_REAL[user_email] = {"nome": user_name, "status": "Ausente (Pausa) 🟡", "inicio": None}
                print(f"[{hora_atual()}] {user_name} ficou AUSENTE.")
                
        return jsonify({"status": "success"}), 200

    # 3. TRATA CHAMADAS NORMAIS
    user = call_data.get('user')
    if not user: 
        return jsonify({"status": "ignored", "reason": "No agent data"}), 200

    agent_email = user.get('email')
    agent_name = user.get('name', agent_email.split('.')[0].capitalize())
    
    dados_agente = AGENTS_MAP.get(agent_email)
    admin_id = dados_agente.get("id") if dados_agente else None

    if not admin_id or not automacao_ativa_agora(agent_email, AGENTS_MAP):
        return jsonify({"status": "ignored"}), 200

    if event_type == 'call.answered':
        STATUS_EM_TEMPO_REAL[agent_email] = {"nome": agent_name, "status": "Em Ligação 🔴", "inicio": datetime.now()}

        if set_intercom_status(admin_id, True):
            enviar_para_slack(WEBHOOK_LIDERANCA, f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação (Ausente).")
            enviar_para_slack(WEBHOOK_GERAL, f"🔴 *{agent_name}* entrou em ligação (Ausente).")

    elif event_type == 'call.ended':
        STATUS_EM_TEMPO_REAL[agent_email] = {"nome": agent_name, "status": "Disponível 🟢", "inicio": None}

        if set_intercom_status(admin_id, False):
            enviar_para_slack(WEBHOOK_LIDERANCA, f"🟢 *{agent_name}* finalizou e está Online.")
            enviar_para_slack(WEBHOOK_GERAL, f"🟢 *{agent_name}* finalizou e está Online.")

    return jsonify({"status": "success"}), 200

@app.route('/status', methods=['GET'])
def painel_visual():
    get_agents_map()
    
    html = """
    <html>
        <head>
            <title>Monitor de Operação</title>
            <meta http-equiv="refresh" content="5"> 
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f9; }
                table { width: 50%; border-collapse: collapse; background: white; margin-top: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
                th { background-color: #2c3e50; color: white; }
            </style>
        </head>
        <body>
            <h2>Painel de Atendimento</h2>
            <p>Atualizado automaticamente a cada 5 segundos.</p>
            <table>
                <tr>
                    <th>Nome do Agente</th>
                    <th>Status Atual</th>
                    <th>Tempo na Ligação</th>
                </tr>
    """

    for email, dados in STATUS_EM_TEMPO_REAL.items():
        nome = dados.get("nome", "Agente")
        status = dados.get("status", "Desconhecido")
        inicio = dados.get("inicio")

        tempo_texto = "-"
        
        if status == "Em Ligação 🔴" and inicio:
            tempo_ligacao = datetime.now() - inicio
            minutos, segundos = divmod(tempo_ligacao.seconds, 60)
            tempo_texto = f"{minutos}m {segundos}s"

        html += f"""
                <tr>
                    <td><b>{nome}</b></td>
                    <td>{status}</td>
                    <td>{tempo_texto}</td>
                </tr>
        """

    html += """
            </table>
        </body>
    </html>
    """
    
    return html

if __name__ == '__main__':
    app.run(debug=True, port=5000)
