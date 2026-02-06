from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")

# CANAL 1: Onde a liderança será marcada (Use a variável SLACK_WEBHOOK_1 no Render)
WEBHOOK_LIDERANCA = os.environ.get("SLACK_WEBHOOK_1")

# CANAL 2: Apenas aviso, sem marcar ninguém (Use a variável SLACK_WEBHOOK_2 no Render)
WEBHOOK_GERAL = os.environ.get("SLACK_WEBHOOK_2")

# IDs para marcar (Apenas no Canal 1)
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

# --- FUNÇÃO DO INTERCOM ---
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
        print(f"❌ Erro no Intercom: {e}")
        return False

# --- FUNÇÃO DE ENVIO SIMPLES ---
def enviar_para_slack(url, mensagem):
    if not url:
        return # Se o link não existir, não faz nada
    try:
        requests.post(url, json={"text": mensagem})
    except Exception as e:
        print(f"⚠️ Erro ao enviar Slack: {e}")

# --- ROTA DO WEBHOOK ---
@app.route('/webhook-aircall', methods=['POST'])
def aircall_hook():
    data = request.json
    
    if not data or 'event' not in data: return jsonify({"status": "ignored"}), 200
    event_type = data['event']
    user = data.get('data', {}).get('user')
    if not user: return jsonify({"status": "ignored"}), 200

    agent_email = user.get('email')
    agent_name = user.get('name', agent_email.split('.')[0].capitalize())
    
    admin_id = AGENTS_MAP.get(agent_email)

    if not admin_id: return jsonify({"status": "ignored"}), 200

    # --- LÓGICA DE ENVIO SEPARADA ---
    
    # 1. ATENDEU A LIGAÇÃO
    if event_type == 'call.answered':
        print(f"📞 {agent_name} atendeu.")
        
        if set_intercom_status(admin_id, True):
            
            # MENSAGEM 1 (COM MARCAÇÃO) -> Vai para o Canal de Liderança
            msg_com_tag = f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação e está *Ausente*."
            enviar_para_slack(WEBHOOK_LIDERANCA, msg_com_tag)

            # MENSAGEM 2 (LIMPA) -> Vai para o Canal Geral
            msg_sem_tag = f"🔴 *{agent_name}* entrou em ligação e está *Ausente*."
            enviar_para_slack(WEBHOOK_GERAL, msg_sem_tag)

    # 2. DESLIGOU A LIGAÇÃO
    elif event_type == 'call.ended':
        print(f"☎️ {agent_name} desligou.")
        
        if set_intercom_status(admin_id, False):
            # Aviso de volta (Online) geralmente não precisa marcar ninguém em nenhum canal
            msg_online = f"🟢 *{agent_name}* finalizou a ligação e está *Online* novamente."
            
            enviar_para_slack(WEBHOOK_LIDERANCA, msg_online)
            enviar_para_slack(WEBHOOK_GERAL, msg_online)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
