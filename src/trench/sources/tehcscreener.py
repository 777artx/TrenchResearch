"""TEHscreener public API (https://tehcscreener.com/api).

Daily aggregates for launchpads, trading terminals ("bots"), chains, DEXes, RWAs
and the Trench Index. 120 requests/min per IP; data updates once a day.
Credit "tehcscreener.com" on anything published from it.

The normalizers below are pure functions from a response body to rows, so they
can be tested against cached fixtures without the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date

BASE_URL = "https://tehcscreener.com/api/v1"
SOURCE = "tehcscreener"
MAX_PER_MINUTE = 110  # documented limit is 120; keep headroom


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _aligned(days: list[str], series: dict, fields: Iterable[str], ids: dict) -> list[dict]:
    """Explode a {days: [...], field: [...]} series into one row per day."""
    fields = list(fields)
    cols = {f: series.get(f) for f in fields}
    rows = []
    for i, day in enumerate(days):
        row = {**ids, "day": _d(day)}
        for f in fields:
            col = cols[f]
            row[f] = None if col is None or i >= len(col) else col[i]
        rows.append(row)
    return rows


# ---- launchpads -------------------------------------------------------------------
def launchpad_series(body: dict) -> list[dict]:
    rows = []
    for s in body["series"]:
        rows += _aligned(
            body["days"],
            s,
            ["volume_usd", "tokens_launched", "revenue_usd"],
            {"chain": s["chain"], "pad": s["pad"]},
        )
    return rows


def launchpad_detail_daily(body: dict) -> list[dict]:
    return [
        {
            "chain": body["chain"],
            "pad": body["pad"],
            "day": _d(r["day"]),
            "tokens_launched": r.get("tokens_launched"),
            "volume_usd": r.get("volume_usd"),
            "trade_txns": r.get("trade_txns"),
        }
        for r in body.get("daily", [])
    ]


def launchpad_top_tokens(body: dict, through: str | None) -> list[dict]:
    return [
        {
            "chain": body["chain"],
            "pad": body["pad"],
            "window": body["window"],
            "tokens_mode": body.get("tokens_mode"),
            "through": _d(through),
            "rank": i + 1,
            "token": t["token"],
            "symbol": t.get("symbol"),
            "name": t.get("name"),
            "volume_usd": t.get("volume_usd"),
            "trade_txns": t.get("trade_txns"),
            "first_day": _d(t.get("first_day")),
            "onchain_mcap_usd": t.get("onchain_mcap_usd"),
            "onchain_change_1d": t.get("onchain_change_1d"),
        }
        for i, t in enumerate(body.get("top_tokens", []))
    ]


def launchpad_profile(body: dict) -> list[dict]:
    p = body.get("profile")
    if not p:
        return []
    return [
        {"chain": body["chain"], "pad": body["pad"], "profile_json": json.dumps(p, sort_keys=True)}
    ]


def launchpad_revenue(body: dict) -> list[dict]:
    return [
        {
            "chain": body["chain"],
            "pad": body["project"],
            "day": _d(r["day"]),
            "protocol_revenue_usd": r.get("protocol_revenue_usd"),
            "creator_revenue_usd": r.get("creator_revenue_usd"),
            "buyback_usd": r.get("buyback_usd"),
            "lineage": r.get("source"),
        }
        for r in body.get("daily", [])
    ]


# ---- bots (trading terminals) ----------------------------------------------------
def bots_series(body: dict) -> list[dict]:
    key = "bot" if body.get("group", "bot") == "bot" else "chain"
    rows = []
    for s in body["series"]:
        rows += _aligned(body["days"], s, ["volume_usd", "txns", "fees_usd"], {key: s["name"]})
    return rows


def bot_chain_daily(body: dict) -> list[dict]:
    rows = []
    for s in body.get("series", []):
        rows += _aligned(
            body["days"],
            s,
            ["volume_usd", "txns", "fees_usd", "wallets"],
            {"bot": body["bot"], "chain": s["name"]},
        )
    return rows


def bot_wallets_dedup(body: dict) -> list[dict]:
    return _aligned(body["days"], body, ["wallets_dedup"], {"bot": body["bot"]})


def bot_profile(body: dict) -> list[dict]:
    keep = [
        "display_name",
        "color",
        "logo_path",
        "website_url",
        "x_url",
        "description",
        "first_day",
        "tokens_since",
        "token_windows",
        "totals",
    ]
    return [
        {
            "bot": body["bot"],
            "profile_json": json.dumps({k: body.get(k) for k in keep}, sort_keys=True),
        }
    ]


def bot_top_tokens(body: dict) -> list[dict]:
    return [
        {
            "bot": body["bot"],
            "window": body["window"],
            "through": _d(body.get("through")),
            "rank": i + 1,
            "chain": t.get("chain"),
            "token": t["token"],
            "volume_usd": t.get("volume_usd"),
            "txns": t.get("txns"),
            "peak_wallets": t.get("peak_wallets"),
            "first_day": _d(t.get("first_day")),
            "last_day": _d(t.get("last_day")),
        }
        for i, t in enumerate(body.get("top_tokens", []))
    ]


def bot_perps_daily(body: dict) -> list[dict]:
    return _aligned(
        body.get("days", []),
        body,
        ["volume_usd", "fees_usd", "txns", "wallets"],
        {"bot": body["bot"]},
    )


# ---- chains, rwa, dexes -----------------------------------------------------------
def chain_daily(body: dict) -> list[dict]:
    return _aligned(
        body["days"],
        body,
        ["txns", "active_wallets", "dex_volume_usd", "dex_trades"],
        {"chain": body["chain"]},
    )


def rwa_daily(body: dict) -> list[dict]:
    return [
        {
            "chain": r["chain"],
            "day": _d(r["day"]),
            "volume_usd": r.get("volume_usd"),
            "value_usd": r.get("value_usd"),
            "swaps": r.get("swaps"),
            "assets_traded": r.get("assets_traded"),
            "assets_valued": r.get("assets_valued"),
        }
        for r in body.get("rows", [])
    ]


def dex_daily(body: dict) -> list[dict]:
    return [
        {
            "chain": body["chain"],
            "dex": body["dex"],
            "day": _d(r["day"]),
            "volume_usd": r.get("volume_usd"),
            "trades": r.get("trades"),
            "pools": r.get("pools"),
            "traders": r.get("traders"),
            "protocol_revenue_usd": r.get("protocol_revenue_usd"),
        }
        for r in body.get("daily", [])
    ]


# ---- trench, status ---------------------------------------------------------------
def trench_history(body: dict) -> list[dict]:
    return [{"day": _d(r["day"]), "score": r["score"]} for r in body.get("history", [])]


def trench_today(body: dict) -> list[dict]:
    t = body.get("today")
    if not t:
        return []
    return [
        {
            "day": _d(t["day"]),
            "score": t["score"],
            "band": t.get("band"),
            "component": k,
            "value": c.get("value"),
            "percentile": c.get("percentile"),
        }
        for k, c in t.get("components", {}).items()
    ]


def trench_method(body: dict) -> list[dict]:
    m = body.get("method")
    if not m:
        return []
    return [
        {
            "method_json": json.dumps(m, sort_keys=True),
            "tracked_json": json.dumps(body.get("tracked"), sort_keys=True),
        }
    ]


def status(body: dict) -> list[dict]:
    return [{k: body.get(k) for k in ("synced_at", "source", "rows_grain", "rows_pad", "note")}]
