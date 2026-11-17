"""DefiLlama DEX volume by chain (https://api.llama.fi). Free, no key.

Daily total DEX volume per chain, all pairs (memecoins, majors and stablecoins
together, no bot filtering). Used as the raw input for chain-level indicators
until our own organic, memecoin-only volume has enough history.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

BASE_URL = "https://api.llama.fi"
SOURCE = "defillama"
MAX_PER_MINUTE = 30
CHAIN_NAMES = {"solana": "Solana", "base": "Base", "ethereum": "Ethereum",
               "robinhood": "Robinhood", "bnb": "BSC"}


def dex_daily_rows(body: dict, chain: str, before: date) -> list[dict]:
    """One row per complete UTC day; the current, incomplete day is dropped."""
    rows = []
    for ts, vol in body.get("totalDataChart") or []:
        day = datetime.fromtimestamp(int(ts), UTC).date()
        if day >= before:
            continue
        rows.append({"chain": chain, "day": day, "volume_usd": float(vol) if vol else None})
    return rows


COINS_URL = "https://coins.llama.fi"
PRICE_ASSETS = {"ETH": "coingecko:ethereum", "SOL": "coingecko:solana"}
MAX_POINTS = 500  # per request, across all coins


def price_rows(body: dict, asset: str, coin_id: str, before: date) -> list[dict]:
    pts = ((body.get("coins") or {}).get(coin_id) or {}).get("prices") or []
    rows = {}
    for p in pts:
        day = datetime.fromtimestamp(int(p["timestamp"]), UTC).date()
        if day < before:
            rows[day] = {"asset": asset, "day": day, "price_usd": float(p["price"])}
    return list(rows.values())
