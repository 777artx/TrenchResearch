"""DexScreener public API (https://docs.dexscreener.com/api/reference).

Current pair state only: price, liquidity, market cap, rolling volume and
transaction counts. No history, so we store a snapshot per run and history
accumulates from our first fetch. Pair endpoints allow 300 requests/min.
"""

from __future__ import annotations

from datetime import UTC, datetime

from trench import chains

BASE_URL = "https://api.dexscreener.com"
SOURCE = "dexscreener"
MAX_PER_MINUTE = 240  # documented 300 for token/pair endpoints
BATCH = 30  # addresses per /tokens/v1 call


def _f(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def pair_rows(body: list[dict]) -> list[dict]:
    rows = []
    for p in body or []:
        chain = chains.from_dxs(p.get("chainId", ""))
        if chain is None:
            continue
        base, quote = p.get("baseToken") or {}, p.get("quoteToken") or {}
        txns, vol = p.get("txns") or {}, p.get("volume") or {}
        liq, chg = p.get("liquidity") or {}, p.get("priceChange") or {}
        created = p.get("pairCreatedAt")
        rows.append(
            {
                "chain": chain,
                "dex": p.get("dexId"),
                "pair_address": chains.norm_address(chain, p["pairAddress"]),
                "labels": ",".join(p.get("labels") or []) or None,
                "base_token": chains.norm_address(chain, base.get("address", "")),
                "base_symbol": base.get("symbol"),
                "base_name": base.get("name"),
                "quote_token": chains.norm_address(chain, quote.get("address", "")),
                "quote_symbol": quote.get("symbol"),
                "price_usd": _f(p.get("priceUsd")),
                "price_native": _f(p.get("priceNative")),
                "liquidity_usd": _f(liq.get("usd")),
                "liquidity_base": _f(liq.get("base")),
                "liquidity_quote": _f(liq.get("quote")),
                "fdv_usd": _f(p.get("fdv")),
                "market_cap_usd": _f(p.get("marketCap")),
                "volume_h24": _f(vol.get("h24")),
                "volume_h6": _f(vol.get("h6")),
                "volume_h1": _f(vol.get("h1")),
                "buys_h24": (txns.get("h24") or {}).get("buys"),
                "sells_h24": (txns.get("h24") or {}).get("sells"),
                "price_change_h24": _f(chg.get("h24")),
                "pair_created_at": (
                    datetime.fromtimestamp(created / 1000, UTC) if created else None
                ),
            }
        )
    return rows
