#!/usr/bin/env python3
"""
google_flights_scraper.py

Consulta o Google Flights (via scraping com Playwright) para uma rota e
data(s) informadas, e extrai o menor preço encontrado entre os resultados
exibidos na página.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def build_google_flights_url(origin: str, destination: str, depart_date: str, return_date: str | None) -> str:
    """Monta a URL de busca do Google Flights usando a busca em linguagem natural."""
    depart_fmt = datetime.strptime(depart_date, "%Y-%m-%d").strftime("%d de %B de %Y")

    if return_date:
        return_fmt = datetime.strptime(return_date, "%Y-%m-%d").strftime("%d de %B de %Y")
        query = f"voos de {origin} para {destination} ida em {depart_fmt} volta em {return_fmt}"
    else:
        query = f"voos somente ida de {origin} para {destination} em {depart_fmt}"

    return f"https://www.google.com/travel/flights?q={quote(query)}&hl=pt-BR&curr=BRL"


def extract_prices_from_page(page) -> list[float]:
    """Extrai todos os valores monetários visíveis na página de resultados."""
    content = page.content()

    # Procura por padrões como "R$ 2.345", "R$2345", "US$ 450", "$450"
    pattern = r"(?:R\$|US\$|\$)\s?([\d\.,]+)"
    raw_matches = re.findall(pattern, content)

    prices = []
    for raw in raw_matches:
        cleaned = raw.replace(".", "").replace(",", ".")
        try:
            value = float(cleaned)
            # Filtra valores fora da faixa plausível de passagens
            if 50 <= value <= 100000:
                prices.append(value)
        except ValueError:
            continue

    return prices


def search_flights(origin: str, destination: str, depart_date: str, return_date: str | None, headless: bool = True) -> dict:
    url = build_google_flights_url(origin, destination, depart_date, return_date)
    result = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
        "lowest_price": None,
        "currency": "BRL",
        "source_url": url,
        "success": False,
        "error": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")

            # Espera algum indício de resultados carregados
            try:
                page.wait_for_selector("text=/R\\$|US\\$|\\$/", timeout=20000)
            except PlaywrightTimeoutError:
                pass

            # Pequena espera extra para a renderização assíncrona
            page.wait_for_timeout(3000)

            prices = extract_prices_from_page(page)

            if prices:
                result["lowest_price"] = min(prices)
                result["success"] = True
            else:
                result["error"] = "Nenhum preço encontrado na página."

        except PlaywrightTimeoutError:
            result["error"] = "Timeout ao carregar a página do Google Flights."
        except Exception as exc:
            result["error"] = f"Erro inesperado: {exc}"
        finally:
            browser.close()

    return result


# =====================================================================
# FUNÇÕES DE INTEGRAÇÃO COM O MAIN.PY
# =====================================================================

def consultar_passagem_ida_e_volta(origem: str, destino: str, data_ida: str, data_volta: str) -> dict | None:
    """Função chamada pelo main.py para buscas de Ida e Volta."""
    res = search_flights(
        origin=origem,
        destination=destino,
        depart_date=data_ida,
        return_date=data_volta,
        headless=True
    )
    if res and res.get("success") and res.get("lowest_price"):
        return {"preco_total": res["lowest_price"]}
    return None


def consultar_passagem_somente_ida(origem: str, destino: str, data_ida: str) -> dict | None:
    """Função chamada pelo main.py para buscas de Somente Ida."""
    res = search_flights(
        origin=origem,
        destination=destino,
        depart_date=data_ida,
        return_date=None,
        headless=True
    )
    if res and res.get("success") and res.get("lowest_price"):
        return {"preco_total": res["lowest_price"]}
    return None


# =====================================================================
# EXECUÇÃO VIA LINHA DE COMANDO (CLI)
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="Consulta o menor preço de voos no Google Flights.")
    parser.add_argument("--origin", required=True, help="Código IATA da origem, ex: GRU")
    parser.add_argument("--destination", required=True, help="Código IATA do destino, ex: JFK")
    parser.add_argument("--depart-date", required=True, help="Data de ida no formato YYYY-MM-DD")
    parser.add_argument("--return-date", default=None, help="Data de volta no formato YYYY-MM-DD (opcional)")
    parser.add_argument("--show-browser", action="store_true", help="Executa com o navegador visível (debug)")

    args = parser.parse_args()

    result = search_flights(
        origin=args.origin.upper(),
        destination=args.destination.upper(),
        depart_date=args.depart_date,
        return_date=args.return_date,
        headless=not args.show_browser,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
