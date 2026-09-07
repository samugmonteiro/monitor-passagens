import json
import os
import sqlite3
import requests
from google_flights_scraper import consultar_passagem_ida_e_volta, consultar_passagem_somente_ida

DB_NAME = 'flight.db'

def inicializar_banco():
    """Garante que a tabela de histórico exista no banco de dados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trajeto_id TEXT,
            preco REAL,
            data_consulta DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def buscar_estatisticas(trajeto_id):
    """Retorna o último preço registrado e a média histórica do trajeto."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Preço da verificação imediatamente anterior
    cursor.execute('''
        SELECT preco FROM historico 
        WHERE trajeto_id = ? 
        ORDER BY id DESC LIMIT 1
    ''', (trajeto_id,))
    ultimo_registro = cursor.fetchone()
    ultimo_preco = ultimo_registro[0] if ultimo_registro else None

    # Média de todos os registros históricos do trajeto
    cursor.execute('''
        SELECT AVG(preco) FROM historico 
        WHERE trajeto_id = ?
    ''', (trajeto_id,))
    media_registro = cursor.fetchone()
    media_preco = media_registro[0] if media_registro and media_registro[0] else None

    conn.close()
    return ultimo_preco, media_preco

def salvar_no_banco(trajeto_id, preco):
    """Salva a nova leitura de preço no banco de dados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO historico (trajeto_id, preco) VALUES (?, ?)', (trajeto_id, preco))
    conn.commit()
    conn.close()

def enviar_telegram(mensagem):
    """Envia a notificação formatada para o Telegram via Bot API."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': mensagem,
            'parse_mode': 'Markdown'
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Erro ao enviar mensagem no Telegram: {e}")

def montar_notificacao(t, preco_atual, ultimo_preco, media_preco):
    """Constrói o relatório em Markdown com preço atual, delta anterior e % em relação à média."""
    tipo = t.get('tipo', 'IDA_E_VOLTA')
    tipo_txt = "Ida e Volta" if tipo == 'IDA_E_VOLTA' else "Somente Ida"
    
    msg = f"📊 *MONITORAMENTO DE PASSAGENS*\n"
    msg += f"📌 *Tipo:* {tipo_txt}\n"
    msg += f"✈️ *Rota:* {t['origem']} ⇄ {t['destino']}\n"
    
    if tipo == 'IDA_E_VOLTA':
        msg += f"📅 *Ida:* {t['data_ida']} | *Volta:* {t['data_volta']}\n\n"
    else:
        msg += f"📅 *Ida:* {t['data_ida']}\n\n"

    msg += f"💵 *Preço Atual:* R$ {preco_atual:,.2f}\n"

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
    inicializar_banco()

    if not os.path.exists('trajetos.json'):
        print("Arquivo trajetos.json não encontrado.")
        return

    with open('trajetos.json', 'r', encoding='utf-8') as f:
        trajetos = json.load(f)

    for t in trajetos:
        if not t.get('ativo', True):
            continue

        trajeto_id = t['id']
        tipo = t.get('tipo', 'IDA_E_VOLTA')
        
        # Recupera histórico antes de salvar o valor atual
        ultimo_preco, media_preco = buscar_estatisticas(trajeto_id)

        print(f"🔍 Consultando {tipo}: {t['origem']} -> {t['destino']}...")
        
        if tipo == 'SOMENTE_IDA':
            resultado = consultar_passagem_somente_ida(t['origem'], t['destino'], t['data_ida'])
        else:
            resultado = consultar_passagem_ida_e_volta(t['origem'], t['destino'], t['data_ida'], t['data_volta'])

        if resultado and resultado.get('preco_total'):
            preco_atual = resultado['preco_total']
            
            # Monta e envia a notificação com os deltas calculados
            msg = montar_notificacao(t, preco_atual, ultimo_preco, media_preco)
            enviar_telegram(msg)
            
            # Atualiza o banco de dados com a nova medição
            salvar_no_banco(trajeto_id, preco_atual)
            print(f"✅ Sucesso: R$ {preco_atual:.2f} gravado no banco.")

if __name__ == "__main__":
    main()
