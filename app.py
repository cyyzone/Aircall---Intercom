from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK")

# --- LIDERANÇA A SER MARCADA ---
# Seus IDs configurados
LIDERANCA_TAGS = "<@U06KNLC1Y9F> <@U08CZ58DDAA>"

AGENTS_MAP = {
    "rhayslla.junca@produttivo.com.br": "5281911",
    "douglas.david@produttivo.com.br": "5586698",
    "aline.souza@produttivo.com.br": "5717251",
    "willian.aust@produttivo.com.br": "7152911",
    "bruno.braga@produttivo.com.br": "7450383",
    "heloisa.atm.slv@produttivo.com.br": "7455039",
    "danielle.ghesini@produttivo.com.br": "7628368",
    "jenyffer.souza@produttivo.com.br": "8115775",
    "marcelo.misugi@produttivo.com.br": "8126602",
    "barbara.carvalho@produttivo.com.br": "8138769" 
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

# --- FUNÇÃO DO SLACK ---
def send_slack_msg(message):
    if not SLACK_WEBHOOK:
        return 
        
    try:
        requests.post(SLACK_WEBHOOK, json={"text": message})
        print("✅ Notificação enviada para o Slack")
    except Exception as e:
        print(f"⚠️ Erro ao enviar para Slack: {e}")

# --- ROTA DO WEBHOOK ---
@app.route('/webhook-aircall', methods=['POST'])
def aircall_hook():
    data = request.json
    
    # Validações básicas
    if not data or 'event' not in data:
        return jsonify({"status": "ignored"}), 200

    event_type = data['event']
    user = data.get('data', {}).get('user')
    
    if not user:
        return jsonify({"status": "ignored", "reason": "No agent data"}), 200

    agent_email = user.get('email')
    
    # --- A CORREÇÃO ESTÁ AQUI EMBAIXO ---
    # Essa linha define o nome antes de ser usada. 
    # Se o nome não vier no json, ele pega a primeira parte do email.
    agent_name = user.get('name', agent_email.split('.')[0].capitalize())
    
    admin_id = AGENTS_MAP.get(agent_email)

    if not admin_id:
        print(f"⚠️ Agente não mapeado: {agent_email}")
        return jsonify({"status": "ignored"}), 200

    # --- LÓGICA PRINCIPAL ---
    
    # 1. ATENDEU A LIGAÇÃO
    if event_type == 'call.answered':
        # Agora a variável agent_name existe e não vai dar erro
        print(f"📞 {agent_name} atendeu.")
        
        if set_intercom_status(admin_id, True):
            msg = f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação e está *Ausente*."
            send_slack_msg(msg)

    # 2. DESLIGOU A LIGAÇÃO
    elif event_type == 'call.ended':
        print(f"☎️ {agent_name} desligou.")
        
        if set_intercom_status(admin_id, False):
            msg = f"🟢 *{agent_name}* finalizou a ligação e está *Online* novamente."
            send_slack_msg(msg)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
