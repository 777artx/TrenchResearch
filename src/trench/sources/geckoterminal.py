"""GeckoTerminal public API (https://www.geckoterminal.com/dex-api).

Pool lists (top, new, trending) with liquidity, market cap and unique buyer and
seller counts, plus daily OHLCV for about the last 180 days. The free tier allows
about 30 requests/min.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from trench import chains

BASE_URL = "https://api.geckoterminal.com/api/v2"
SOURCE = "geckoterminal"
MAX_PER_MINUTE = 15  # paced evenly; bursts at 30/min drew ~100 429s, 20/min still ~10
BACKOFF_BASE = 10.0  # 429s carry no Retry-After: wait 10, 20, 40, 80 s
HEADERS = {"Accept": "application/json;version=20230302"}
OHLCV_MAX_DAYS = 1000  # per-request limit; free history is shorter (~180 days)


def _f(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _addr_from_id(rel: dict | None, network: str) -> str | None:
    """Relationship ids look like '<network>_<address>'."""
    rid = ((rel or {}).get("data") or {}).get("id")
    if not rid:
        return None
    prefix = network + "_"
    return rid[len(prefix):] if rid.startswith(prefix) else rid


def _ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def pool_rows(body: dict, network: str, listing: str) -> list[dict]:
    chain = chains.from_gt(network)
    if chain is None:
        return []
    rows = []
    for p in body.get("data") or []:
        a = p.get("attributes") or {}
        rel = p.get("relationships") or {}
        tx = (a.get("transactions") or {}).get("h24") or {}
        vol = a.get("volume_usd") or {}
        base = _addr_from_id(rel.get("base_token"), network)
        quote = _addr_from_id(rel.get("quote_token"), network)
        rows.append(
            {
                "chain": chain,
                "listing": listing,
                "pool_address": chains.norm_address(chain, a["address"]),
                "name": a.get("name"),
                "dex": ((rel.get("dex") or {}).get("data") or {}).get("id"),
                "base_token": chains.norm_address(chain, base) if base else None,
                "quote_token": chains.norm_address(chain, quote) if quote else None,
                "base_token_price_usd": _f(a.get("base_token_price_usd")),
                "reserve_usd": _f(a.get("reserve_in_usd")),
                "market_cap_usd": _f(a.get("market_cap_usd")),
                "fdv_usd": _f(a.get("fdv_usd")),
                "volume_h24": _f(vol.get("h24")),
                "buys_h24": tx.get("buys"),
                "sells_h24": tx.get("sells"),
                "buyers_h24": tx.get("buyers"),
                "sellers_h24": tx.get("sellers"),
                "pool_created_at": _ts(a.get("pool_created_at")),
            }
        )
    return rows


def ohlcv_rows(body: dict, chain: str, pool: str, token: str, before: date) -> list[dict]:
    """Daily candles priced in USD for ``token``. Days on or after ``before`` are
    dropped, because the current day's candle is incomplete."""
    lst = (((body.get("data") or {}).get("attributes") or {}).get("ohlcv_list")) or []
    rows = []
    for ts, o, h, lo, c, v in lst:
        day = datetime.fromtimestamp(ts, UTC).date()
        if day >= before:
            continue
        rows.append(
            {"chain": chain, "pool_address": pool, "token": token, "day": day,
             "open": _f(o), "high": _f(h), "low": _f(lo), "close": _f(c), "volume_usd": _f(v)}
        )
    return rows
