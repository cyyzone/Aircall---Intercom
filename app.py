from flask import Flask, request, jsonify
import requests
import os
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
    "bruno.braga@produttivo.com.br": "7450383",
    "heloisa.atm.slv@produttivo.com.br": "7455039",
    "danielle.ghesini@produttivo.com.br": "7628368",
    "jenyffer.souza@produttivo.com.br": "8115775",
    "marcelo.misugi@produttivo.com.br": "8126602"
}

# Função auxiliar para pegar hora certa no log
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
        print(f"[{hora_atual()}] ❌ Erro ao conectar com Intercom: {e}")
        return False

def enviar_para_slack(url, mensagem, canal_nome):
    if not url: return
    try:
        requests.post(url, json={"text": mensagem})
        # LOG DE SUCESSO DO SLACK
        print(f"[{hora_atual()}] 💬 Slack enviado para {canal_nome}.")
    except Exception as e:
        print(f"[{hora_atual()}] ⚠️ Erro ao enviar Slack ({canal_nome}): {e}")

@app.route('/webhook-aircall', methods=['POST'])
def aircall_hook():
    data = request.json
    
    if not data or 'event' not in data:
        # Log simples para ignorar spam vazio
        return jsonify({"status": "ignored"}), 200

    event_type = data['event']
    
    # Filtra logs para não poluir com eventos inúteis (tocando, criado, etc)
    if event_type not in ['call.answered', 'call.ended']:
        return jsonify({"status": "ignored"}), 200

    user = data.get('data', {}).get('user')
    if not user: return jsonify({"status": "ignored"}), 200

    agent_email = user.get('email')
    agent_name = user.get('name', agent_email.split('.')[0].capitalize())
    admin_id = AGENTS_MAP.get(agent_email)

    if not admin_id:
        print(f"[{hora_atual()}] 🚫 Ignorado: Agente não mapeado ({agent_email})")
        return jsonify({"status": "ignored"}), 200

    # --- LÓGICA DETALHADA ---
    
    if event_type == 'call.answered':
        print(f"[{hora_atual()}] 📞 {agent_name} ATENDEU. Iniciando processos...")
        
        # 1. Tenta mudar Intercom
        if set_intercom_status(admin_id, True):
            # LOG DE SUCESSO INTERCOM
            print(f"[{hora_atual()}] ✅ Status Intercom alterado para: AUSENTE")
            
            # 2. Envia Slack Liderança
            msg_com_tag = f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação e está *Ausente*."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg_com_tag, "Canal Liderança")

            # 3. Envia Slack Geral
            msg_sem_tag = f"🔴 *{agent_name}* entrou em ligação e está *Ausente*."
            enviar_para_slack(WEBHOOK_GERAL, msg_sem_tag, "Canal Geral")
        else:
            print(f"[{hora_atual()}] ❌ Falha ao mudar status no Intercom.")

    elif event_type == 'call.ended':
        print(f"[{hora_atual()}] ☎️ {agent_name} DESLIGOU. Iniciando processos...")
        
        # 1. Tenta mudar Intercom
        if set_intercom_status(admin_id, False):
            # LOG DE SUCESSO INTERCOM
            print(f"[{hora_atual()}] ✅ Status Intercom alterado para: ONLINE")
            
            # 2. Envia Slack (Avisos de volta)
            msg_online = f"🟢 *{agent_name}* finalizou a ligação e está *Online* novamente."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg_online, "Canal Liderança")
            enviar_para_slack(WEBHOOK_GERAL, msg_online, "Canal Geral")
        else:
            print(f"[{hora_atual()}] ❌ Falha ao mudar status no Intercom.")

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
