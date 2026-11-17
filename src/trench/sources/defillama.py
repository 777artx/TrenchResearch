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
