#!/usr/bin/env python3
"""
flight_price_tracker.py

Armazena preços de voos coletados (por exemplo, pelo google_flights_scraper.py)
em um banco SQLite e fornece uma regra para verificar se o preço atual de um
trecho está X% abaixo da média histórica daquele trecho.

Uso típico:

    from flight_price_tracker import (
        init_db,
        store_price,
        get_historical_average,
        check_price_drop,
    )

    init_db()

    store_price(origin="GRU", destination="JFK", depart_date="2026-11-10",
                return_date="2026-11-20", price=3245.0, currency="BRL")

    resultado = check_price_drop(
        origin="GRU", destination="JFK",
        current_price=2800.0, threshold_pct=15,
    )
    print(resultado)
"""

import sqlite3
import json
from contextlib import closing
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

DB_PATH = "flight_prices.db"


# --------------------------------------------------------------------------
# Setup do banco
# --------------------------------------------------------------------------

def init_db(db_path: str = DB_PATH) -> None:
    """Cria a tabela de preços caso ainda não exista."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS flight_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                depart_date TEXT NOT NULL,
                return_date TEXT,
                price REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'BRL',
                collected_at TEXT NOT NULL
            )
            """
        )
        # Índice para acelerar consultas por trecho (origem + destino)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_route ON flight_prices (origin, destination)"
        )
        conn.commit()


# --------------------------------------------------------------------------
# Inserção de dados
# --------------------------------------------------------------------------

def store_price(
    origin: str,
    destination: str,
    depart_date: str,
    price: float,
    return_date: Optional[str] = None,
    currency: str = "BRL",
    db_path: str = DB_PATH,
) -> int:
    """
    Insere um preço coletado no banco. Retorna o id do registro criado.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO flight_prices
                (origin, destination, depart_date, return_date, price, currency, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (origin.upper(), destination.upper(), depart_date, return_date, price, currency, collected_at),
        )
        conn.commit()
        return cursor.lastrowid


# --------------------------------------------------------------------------
# Consultas / estatísticas
# --------------------------------------------------------------------------

def get_historical_average(
    origin: str,
    destination: str,
    db_path: str = DB_PATH,
    exclude_last: bool = False,
) -> Optional[float]:
    """
    Retorna o preço médio histórico já coletado para o trecho origin->destination.
    Se exclude_last=True, ignora o registro mais recente (útil para comparar o
    preço atual contra a média SEM incluí-lo).
    Retorna None se não houver dados suficientes.
    """
    with closing(sqlite3.connect(db_path)) as conn:
        if exclude_last:
            query = """
                SELECT AVG(price) FROM flight_prices
                WHERE origin = ? AND destination = ?
                AND id NOT IN (
                    SELECT id FROM flight_prices
                    WHERE origin = ? AND destination = ?
                    ORDER BY collected_at DESC LIMIT 1
                )
            """
            params = (origin.upper(), destination.upper(), origin.upper(), destination.upper())
        else:
            query = "SELECT AVG(price) FROM flight_prices WHERE origin = ? AND destination = ?"
            params = (origin.upper(), destination.upper())

        row = conn.execute(query, params).fetchone()
        return row[0] if row and row[0] is not None else None


def get_price_count(origin: str, destination: str, db_path: str = DB_PATH) -> int:
    """Retorna quantos preços já foram coletados para esse trecho."""
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM flight_prices WHERE origin = ? AND destination = ?",
            (origin.upper(), destination.upper()),
        ).fetchone()
        return row[0] if row else 0


# --------------------------------------------------------------------------
# Regra de negócio: preço X% abaixo da média histórica
# --------------------------------------------------------------------------

@dataclass
class PriceDropResult:
    origin: str
    destination: str
    current_price: float
    historical_average: Optional[float]
    threshold_pct: float
    pct_below_average: Optional[float]
    is_good_deal: bool
    samples_used: int
    message: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def check_price_drop(
    origin: str,
    destination: str,
    current_price: float,
    threshold_pct: float = 15.0,
    db_path: str = DB_PATH,
    min_samples: int = 3,
) -> PriceDropResult:
    """
    Verifica se `current_price` está pelo menos `threshold_pct`% abaixo da
    média histórica de preços já registrados para o trecho origin->destination.

    - threshold_pct=15 significa: "o preço atual precisa estar 15% ou mais
      abaixo da média histórica para ser considerado uma boa oferta".
    - min_samples define o número mínimo de registros históricos necessários
      para o cálculo ser considerado confiável (default: 3).
    """
    avg_price = get_historical_average(origin, destination, db_path=db_path)
    samples = get_price_count(origin, destination, db_path=db_path)

    if avg_price is None or samples < min_samples:
        return PriceDropResult(
            origin=origin.upper(),
            destination=destination.upper(),
            current_price=current_price,
            historical_average=avg_price,
            threshold_pct=threshold_pct,
            pct_below_average=None,
            is_good_deal=False,
            samples_used=samples,
            message=(
                f"Dados históricos insuficientes ({samples} amostra(s); "
                f"mínimo necessário: {min_samples}). Não é possível avaliar a oferta com confiança."
            ),
        )

    pct_below_average = ((avg_price - current_price) / avg_price) * 100
    is_good_deal = pct_below_average >= threshold_pct

    if is_good_deal:
        message = (
            f"Preço atual está {pct_below_average:.1f}% abaixo da média histórica "
            f"({samples} amostras) — considerado uma boa oferta (limite: {threshold_pct}%)."
        )
    else:
        message = (
            f"Preço atual está {pct_below_average:.1f}% "
            f"{'abaixo' if pct_below_average >= 0 else 'acima'} da média histórica "
            f"({samples} amostras) — abaixo do limite de {threshold_pct}% para ser considerado boa oferta."
        )

    return PriceDropResult(
        origin=origin.upper(),
        destination=destination.upper(),
        current_price=current_price,
        historical_average=round(avg_price, 2),
        threshold_pct=threshold_pct,
        pct_below_average=round(pct_below_average, 2),
        is_good_deal=is_good_deal,
        samples_used=samples,
        message=message,
    )


# --------------------------------------------------------------------------
# Exemplo de uso combinando com o scraper (google_flights_scraper.py)
# --------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()

    # Simulação: alguns preços históricos coletados em dias anteriores
    store_price("GRU", "JFK", "2026-11-10", 3400.0)
    store_price("GRU", "JFK", "2026-11-10", 3550.0)
    store_price("GRU", "JFK", "2026-11-10", 3300.0)
    store_price("GRU", "JFK", "2026-11-10", 3600.0)

    # Preço coletado "hoje"
    preco_atual = 2800.0

    resultado = check_price_drop(
        origin="GRU",
        destination="JFK",
        current_price=preco_atual,
        threshold_pct=15,
    )

    print(resultado.to_json())
