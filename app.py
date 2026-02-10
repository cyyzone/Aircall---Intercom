from flask import Flask, request, jsonify
import requests
import os
import json # Importado para ler o pacote de dados completo
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")
WEBHOOK_LIDERANCA = os.environ.get("SLACK_WEBHOOK_1")
WEBHOOK_GERAL = os.environ.get("SLACK_WEBHOOK_2")

LIDERANCA_TAGS = "<@U06KNLC1Y9F> <@U08CZ58DDAA>"

AGENTS_MAP = {
    "rhayslla.junca@produttivo.com.br": "5281911",
    "douglas.david@produttivo.com.br": "5586698",
    "aline.souza@produttivo.com.br": "5717251",
    "heloisa.atm.slv@produttivo.com.br": "7455039",
    "danielle.ghesini@produttivo.com.br": "7628368",
    "jenyffer.souza@produttivo.com.br": "8115775",
    "marcelo.misugi@produttivo.com.br": "8126602"
}

def hora_atual():
    return datetime.now().strftime("%H:%M:%S")

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
        print(f"[{hora_atual()}] ❌ Erro Intercom: {e}")
        return False

def enviar_para_slack(url, mensagem):
    if not url: return
    try:
        requests.post(url, json={"text": mensagem})
    except Exception as e:
        print(f"[{hora_atual()}] ⚠️ Erro Slack: {e}")

@app.route('/webhook-aircall', methods=['POST'])
def aircall_hook():
    data = request.json
    
    if not data or 'event' not in data:
        return jsonify({"status": "ignored"}), 200

    event_type = data['event']
    
    # --- LOG DIAGNÓSTICO (IMPORTANTE) ---
    # Isso vai imprimir no Render exatamente o que acontece numa transferência
    if 'transfer' in event_type:
        print(f"\n[{hora_atual()}] 🕵️ DETETIVE DE TRANSFERÊNCIA:")
        print(json.dumps(data, indent=2))
        print("-" * 30)

    user = data.get('data', {}).get('user')
    
    # Se não tiver user, tentamos achar nos campos de transferência (correção tentativa)
    if not user and 'transferred_to' in str(data):
         print(f"[{hora_atual()}] ⚠️ Evento de transferência detectado sem usuário padrão.")

    if not user: 
        return jsonify({"status": "ignored", "reason": "No agent data"}), 200

    agent_email = user.get('email')
    agent_name = user.get('name', agent_email.split('.')[0].capitalize())
    admin_id = AGENTS_MAP.get(agent_email)

    if not admin_id:
        # Só imprime se for um evento relevante, pra não sujar o log
        if event_type in ['call.answered', 'call.ended', 'call.transferred']:
            print(f"[{hora_atual()}] 🚫 Agente não mapeado: {agent_email}")
        return jsonify({"status": "ignored"}), 200

    # --- LÓGICA ATUALIZADA ---

    # 1. ATENDEU (Normal)
    if event_type == 'call.answered':
        print(f"[{hora_atual()}] 📞 {agent_name} ATENDEU.")
        if set_intercom_status(admin_id, True):
            msg_tag = f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação (Ausente)."
            msg_geral = f"🔴 *{agent_name}* entrou em ligação (Ausente)."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg_tag)
            enviar_para_slack(WEBHOOK_GERAL, msg_geral)

    # 2. DESLIGOU (Normal)
    elif event_type == 'call.ended':
        print(f"[{hora_atual()}] ☎️ {agent_name} DESLIGOU.")
        if set_intercom_status(admin_id, False):
            msg = f"🟢 *{agent_name}* finalizou e está Online."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg)
            enviar_para_slack(WEBHOOK_GERAL, msg)

    # 3. TRANSFERIU (Tentativa de Correção para Heloísa)
    elif event_type == 'call.transferred':
        print(f"[{hora_atual()}] 🔀 {agent_name} TRANSFERIU a chamada.")
        
        # Lógica: Quem transfere (Heloisa) sai da ligação, então fica ONLINE
        if set_intercom_status(admin_id, False):
            print(f"[{hora_atual()}] ✅ {agent_name} voltou para ONLINE após transferir.")
            msg = f"🟢 *{agent_name}* transferiu a chamada e está Online."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg)
            enviar_para_slack(WEBHOOK_GERAL, msg)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
