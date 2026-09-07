import json
import os
from scraper import consultar_passagem_ida_e_volta
from database import salvar_historico, avaliar_e_notificar

def carregar_trajetos():
    if not os.path.exists('trajetos.json'):
        print("Arquivo trajetos.json não encontrado.")
        return []
    with open('trajetos.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    trajetos = carregar_trajetos()
    print(f"Iniciando monitoramento de {len(trajetos)} trajeto(s) [IDA E VOLTA]...\n")

    for t in trajetos:
        if not t.get('ativo', True):
            continue

        print(f"✈️ Consultando Pacote Ida + Volta: {t['origem']} ⇄ {t['destino']}")
        print(f"   📅 Ida: {t['data_ida']} | Volta: {t['data_volta']}")
        
        # Consulta o valor TOTAL da ida + volta juntas
        resultado = consultar_passagem_ida_e_volta(
            origem=t['origem'],
            destino=t['destino'],
            data_ida=t['data_ida'],
            data_volta=t['data_volta']
        )
        
        if resultado and resultado.get('preco_total'):
            preco_total = resultado['preco_total']
            print(f"💵 Menor preço total encontrado (Ida + Volta): R$ {preco_total:.2f}")
            
            # Salva o histórico combinado e valida o preço alvo total
            salvar_historico(t['id'], preco_total)
            avaliar_e_notificar(
                trajeto_id=t['id'], 
                preco_atual=preco_total, 
                preco_alvo=t['preco_alvo_total']
            )

if __name__ == "__main__":
    main()
