from flask import Flask, request, jsonify
import requests
import os 

app = Flask(__name__)

INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK")
LIDERANCA_TAGS = "<@U06KNLC1Y9F> <@U08CZ58DDAA>"

if not INTERCOM_TOKEN:
    print("⚠️ AVISO: Token do Intercom não encontrado nas variáveis de ambiente!")

# nossa lista de de/para.. o aircall manda email e a gente traduz pra ID do intercom
AGENTS_MAP = {
    "rhayslla.junca@produttivo.com.br": "5281911",
    "douglas.david@produttivo.com.br": "5586698",
    "aline.souza@produttivo.com.br": "5717251",
    "bruno.braga@produttivo.com.br": "7450383",
    "heloisa.atm.slv@produttivo.com.br": "7455039",
    "danielle.ghesini@produttivo.com.br": "7628368",
    "jenyffer.souza@produttivo.com.br": "8115775",
    "marcelo.misugi@produttivo.com.br": "8126602",
}

# funcao q faz a magica de chamar a api do intercom
def set_intercom_status(admin_id, is_away):
    url = f"https://api.intercom.io/admins/{admin_id}/away"
    headers = {
        "Authorization": f"Bearer {INTERCOM_TOKEN}", # autenticacao
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    # essa trava (reassign: False) eh importante pra nao perder os chats q ja tao com o agente
    payload = {"away_mode_enabled": is_away, "away_mode_reassign": False}
    
    try:
        response = requests.put(url, json=payload, headers=headers)
        response.raise_for_status() 
        print(f"✅ Sucesso! Status alterado para: {'Ausente' if is_away else 'Online'}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro no Intercom: {e}")
        return False

# --- FUNÇÃO DO SLACK (Envia notificação)
def send_slack_msg(message):
    if not SLACK_WEBHOOK:
        return # Se não tiver link configurado, não faz nada
        
    try:
        requests.post(SLACK_WEBHOOK, json={"text": message})
        print("✅ Notificação enviada para o Slack")
    except Exception as e:
        print(f"⚠️ Erro ao enviar para Slack: {e}")

@app.route('/', methods=['GET'])
def home():
    return "A automação está online e rodando! 🚀"

# rota do webhook.. eh aqui q o aircall bate qdo o telefone toca
@app.route('/webhook-aircall', methods=['POST'])
def aircall_hook():
    data = request.json
    
    # validacao basica so pra garantir q tem dados
    if not data or 'event' not in data:
        return jsonify({"status": "ignored"}), 200

    event_type = data['event']
    user = data.get('data', {}).get('user')
    
    # se nao tiver usuario (ex: evento de sistema), ignora
    if not user:
        return jsonify({"status": "ignored", "reason": "No agent data"}), 200

    agent_email = user.get('email')
    admin_id = AGENTS_MAP.get(agent_email) # busca o ID na nossa lista la de cima

    # se o agente nao tiver na lista, avisa no log e nao faz nada
    if not admin_id:
        print(f"⚠️ Agente não mapeado: {agent_email}")
        return jsonify({"status": "ignored"}), 200

# 1. ATENDEU A LIGAÇÃO
    if event_type == 'call.answered':
        print(f"📞 {agent_name} atendeu.")
        
        # Muda status no Intercom
        if set_intercom_status(admin_id, True):
            # Manda mensagem no Slack marcando os dois líderes
            msg = f"🔴 {LIDERANCA_TAGS}: *{agent_name}* entrou em ligação e está *Ausente*."
            send_slack_msg(msg)

    # 2. DESLIGOU A LIGAÇÃO
    elif event_type == 'call.ended':
        print(f"☎️ {agent_name} desligou.")
        
        # Volta status no Intercom
        if set_intercom_status(admin_id, False):
            # Avisa no Slack (sem marcar liderança, para não gerar spam desnecessário)
            msg = f"🟢 *{agent_name}* finalizou a ligação e está *Online* novamente."
            send_slack_msg(msg)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
