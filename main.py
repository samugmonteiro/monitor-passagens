import json
import os
from scraper import consultar_passagem  # Mantém a função de busca existente
from database import salvar_historico, avaliar_e_notificar # Mantém rotinas existentes

def carregar_trajetos():
    caminho_json = 'trajetos.json'
    if not os.path.exists(caminho_json):
        print("Arquivo trajetos.json não encontrado.")
        return []
    with open(caminho_json, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    trajetos = carregar_trajetos()
    print(f"Iniciando monitoramento de {len(trajetos)} trajeto(s)...")

    for t in trajetos:
        if not t.get('ativo', True):
            continue

        print(f"\n🔍 Consultando: {t['origem']} -> {t['destino']} ({t['data_ida']} a {t['data_volta']})")
        
        # Executa consulta para cada trajeto configurado
        resultado = consultar_passagem(t['origem'], t['destino'], t['data_ida'], t['data_volta'])
        
        if resultado and resultado.get('preco'):
            preco = resultado['preco']
            print(f"💵 Menor preço: R$ {preco}")
            
            # Salva e valida individualmente por trajeto
            salvar_historico(t['id'], preco)
            avaliar_e_notificar(t['id'], preco, t['preco_alvo'])

if __name__ == "__main__":
    main()
