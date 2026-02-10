from flask import Flask, request, jsonify
import requests
import os
import json
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
    "marcelo.misugi@produttivo.com.br": "8126602",
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
    call_data = data.get('data', {})

    # ---------------------------------------------------------
    # CENÁRIO 1: TRANSFERÊNCIA (Lógica Especial)
    # ---------------------------------------------------------
    if event_type == 'call.transferred':
        print(f"[{hora_atual()}] 🔀 TRANSFERÊNCIA DETECTADA!")
        
        # PARTE A: Quem transferiu (ex: Heloisa) -> Fica ONLINE
        quem_transferiu = call_data.get('transferred_by')
        if quem_transferiu:
            email_by = quem_transferiu.get('email')
            name_by = quem_transferiu.get('name', 'Agente')
            id_by = AGENTS_MAP.get(email_by)
            
            if id_by:
                if set_intercom_status(id_by, False): # False = Online
                    print(f"[{hora_atual()}] ✅ {name_by} (Origem) voltou para ONLINE.")
                    msg = f"🟢 *{name_by}* transferiu a chamada e ficou *Online*."
                    enviar_para_slack(WEBHOOK_LIDERANCA, msg)
                    enviar_para_slack(WEBHOOK_GERAL, msg)
        
        # PARTE B: Quem recebeu (ex: Aline) -> Fica AUSENTE
        quem_recebeu = call_data.get('transferred_to')
        if quem_recebeu:
            email_to = quem_recebeu.get('email')
            name_to = quem_recebeu.get('name', 'Agente')
            id_to = AGENTS_MAP.get(email_to)
            
            if id_to:
                if set_intercom_status(id_to, True): # True = Ausente
                    print(f"[{hora_atual()}] ✅ {name_to} (Destino) mudou para AUSENTE.")
                    msg_lider = f"🔴 {LIDERANCA_TAGS}: *{name_to}* recebeu transferência e ficou *Ausente*."
                    msg_geral = f"🔴 *{name_to}* recebeu transferência e ficou *Ausente*."
                    enviar_para_slack(WEBHOOK_LIDERANCA, msg_lider)
                    enviar_para_slack(WEBHOOK_GERAL, msg_geral)

        return jsonify({"status": "success"}), 200

    # ---------------------------------------------------------
    # CENÁRIO 2: CHAMADA NORMAL (Atendeu / Desligou)
    # ---------------------------------------------------------
    
    user = call_data.get('user')
    if not user: 
        return jsonify({"status": "ignored", "reason": "No agent data"}), 200

    agent_email = user.get('email')
    agent_name = user.get('name', agent_email.split('.')[0].capitalize())
    admin_id = AGENTS_MAP.get(agent_email)

    if not admin_id:
        return jsonify({"status": "ignored"}), 200

    if event_type == 'call.answered':
        print(f"[{hora_atual()}] 📞 {agent_name} ATENDEU.")
        if set_intercom_status(admin_id, True):
            msg_tag = f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação (Ausente)."
            msg_geral = f"🔴 *{agent_name}* entrou em ligação (Ausente)."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg_tag)
            enviar_para_slack(WEBHOOK_GERAL, msg_geral)

    elif event_type == 'call.ended':
        print(f"[{hora_atual()}] ☎️ {agent_name} DESLIGOU.")
        if set_intercom_status(admin_id, False):
            msg = f"🟢 *{agent_name}* finalizou e está Online."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg)
            enviar_para_slack(WEBHOOK_GERAL, msg)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
