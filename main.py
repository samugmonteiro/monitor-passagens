import json
import os
import sqlite3
import requests

def buscar_estatisticas(trajeto_id):
    conn = sqlite3.connect('flight.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trajeto_id TEXT,
            preco REAL,
            data_consulta DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Preço da última verificação
    cursor.execute('''
        SELECT preco FROM historico 
        WHERE trajeto_id = ? 
        ORDER BY id DESC LIMIT 1
    ''', (trajeto_id,))
    ultimo_registro = cursor.fetchone()
    ultimo_preco = ultimo_registro[0] if ultimo_registro else None

    # Média de todo o histórico registrado
    cursor.execute('''
        SELECT AVG(preco) FROM historico 
        WHERE trajeto_id = ?
    ''', (trajeto_id,))
    media_registro = cursor.fetchone()
    media_preco = media_registro[0] if media_registro and media_registro[0] else None

    conn.close()
    return ultimo_preco, media_preco

def salvar_no_banco(trajeto_id, preco):
    conn = sqlite3.connect('flight.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO historico (trajeto_id, preco) VALUES (?, ?)', (trajeto_id, preco))
    conn.commit()
    conn.close()

def enviar_telegram(mensagem):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={'chat_id': chat_id, 'text': mensagem, 'parse_mode': 'Markdown'})

def montar_notificacao(t, preco_atual, ultimo_preco, media_preco):
    msg = f"📊 *MONITORAMENTO DE PASSAGENS*\n"
    msg += f"✈️ *Rota:* {t['origem']} ⇄ {t['destino']}\n"
    msg += f"📅 *Ida:* {t['data_ida']} | *Volta:* {t['data_volta']}\n\n"
    msg += f"💵 *Preço Atual (Ida + Volta):* R$ {preco_atual:,.2f}\n"

    # Comparativo com a última verificação
    if ultimo_preco is None:
        msg += "🔄 *Comparação anterior:* Nulo (Primeira verificação)\n"
    else:
        diff_ult = preco_atual - ultimo_preco
        if diff_ult > 0:
            msg += f"🔺 *Comparação anterior:* Aumentou R$ {diff_ult:,.2f}\n"
        elif diff_ult < 0:
            msg += f"🔻 *Comparação anterior:* Diminuiu R$ {abs(diff_ult):,.2f}\n"
        else:
            msg += "➖ *Comparação anterior:* Preço manteve-se estável\n"

    # Comparativo com a média histórica
    if media_preco:
        pct_media = ((preco_atual - media_preco) / media_preco) * 100
        if pct_media > 0:
            msg += f"📈 *Média Geral:* {pct_media:.1f}% ACIMA da média (R$ {media_preco:,.2f})\n"
        elif pct_media < 0:
            msg += f"📉 *Média Geral:* {abs(pct_media):.1f}% ABAIXO da média (R$ {media_preco:,.2f})\n"
        else:
            msg += f"🎯 *Média Geral:* Exatamente na média (R$ {media_preco:,.2f})\n"

    return msg

def main():
    if not os.path.exists('trajetos.json'):
        print("Arquivo trajetos.json não encontrado.")
        return

    with open('trajetos.json', 'r', encoding='utf-8') as f:
        trajetos = json.load(f)

    from scraper import consultar_passagem_ida_e_volta  # Import da raspagem

    for t in trajetos:
        if not t.get('ativo', True):
            continue

        ultimo_preco, media_preco = buscar_estatisticas(t['id'])
        resultado = consultar_passagem_ida_e_volta(t['origem'], t['destino'], t['data_ida'], t['data_volta'])

        if resultado and resultado.get('preco_total'):
            preco_atual = resultado['preco_total']
            
            # Monta e envia relatório
            msg = montar_notificacao(t, preco_atual, ultimo_preco, media_preco)
            enviar_telegram(msg)
            
            # Salva o valor atual para a próxima consulta usar
            salvar_no_banco(t['id'], preco_atual)

if __name__ == "__main__":
    main()
