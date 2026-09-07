import os
import requests
from google_flights_scraper import search_flights
from flight_price_tracker import init_db, store_price, check_price_drop

# Configurações passadas via Secrets do GitHub / Variáveis de ambiente
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ORIGEM = os.getenv("ORIGEM", "GRU")
DESTINO = os.getenv("DESTINO", "JFK")
DATA_IDA = os.getenv("DATA_IDA", "2026-11-10")
DATA_VOLTA = os.getenv("DATA_VOLTA", "2026-11-20")
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", "15.0"))

def enviar_telegram(mensagem: str):
    """Envia alerta via Telegram Bot."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Credenciais do Telegram não configuradas (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("📱 Notificação enviada para o Telegram com sucesso!")
        else:
            print(f"❌ Falha ao enviar para o Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Erro ao conectar ao Telegram: {e}")

def run():
    # 1. Garante que o banco de dados SQLite existe
    init_db()

    print(f"🔎 Consultando voos de {ORIGEM} para {DESTINO} (Ida: {DATA_IDA}, Volta: {DATA_VOLTA})...")
    
    # 2. Busca o preço no Google Flights usando o scraper do Claude
    resultado = search_flights(
        origin=ORIGEM,
        destination=DESTINO,
        depart_date=DATA_IDA,
        return_date=DATA_VOLTA,
        headless=True
    )

    if not resultado["success"] or resultado["lowest_price"] is None:
        print(f"❌ Erro na busca: {resultado.get('error', 'Sem preço retornado')}")
        return

    preco_atual = resultado["lowest_price"]
    print(f"💵 Menor preço encontrado hoje: R$ {preco_atual:.2f}")

    # 3. Registra o preço no banco SQLite
    store_price(
        origin=ORIGEM,
        destination=DESTINO,
        depart_date=DATA_IDA,
        return_date=DATA_VOLTA,
        price=preco_atual
    )

    # 4. Avalia se o preço atual é uma boa oferta
    avaliacao = check_price_drop(
        origin=ORIGEM,
        destination=DESTINO,
        current_price=preco_atual,
        threshold_pct=THRESHOLD_PCT
    )

    print(f"📊 Avaliação: {avaliacao.message}")

    # 5. Se for uma boa oferta (ou em testes), envia o alerta no Telegram
    if avaliacao.is_good_deal:
        msg = (
            f"🚨 *ALERTA DE PASSAGEM BARATA!*\n\n"
            f"✈️ *Rota:* {ORIGEM} ➡️ {DESTINO}\n"
            f"📅 *Ida:* {DATA_IDA} | *Volta:* {DATA_VOLTA}\n"
            f"💰 *Preço Atual:* R$ {preco_atual:.2f}\n"
            f"📉 *Média Histórica:* R$ {avaliacao.historical_average:.2f}\n"
            f"🔥 *Desconto:* {avaliacao.pct_below_average}% abaixo da média!\n\n"
            f"🔗 [Abrir no Google Flights]({resultado['source_url']})"
        )
        enviar_telegram(msg)

if __name__ == "__main__":
    run()