"""GMGN (gmgn.ai) via a headless browser (tools/gmgn/collect.js). Scraping approved
by Arthur on 2026-11-19. Endpoints are internal and may change: normalizers raise
on unexpected shapes instead of returning nothing.

GMGN's tags and PnL figures are GMGN's own definitions; they are stored as inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime

BASE_PARAMS_NOTE = "device and client parameters are copied from the page's own requests"


def _f(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def _ts(x):
    return datetime.fromtimestamp(int(x), UTC) if x else None


def trade_rows(body: dict, token: str) -> list[dict]:
    hist = body["data"]["history"]
    return [{
        "token": token, "trade_id": t.get("id"), "tx_hash": t.get("tx_hash"),
        "block_time": _ts(t.get("timestamp")), "wallet": t.get("maker"),
        # event: buy, sell, add / remove (liquidity), burn. Indicators use buy and sell.
        "side": t.get("event"), "token_amount": _f(t.get("base_amount")),
        "quote_amount": _f(t.get("quote_amount")), "quote_symbol": t.get("quote_symbol"),
        "usd": _f(t.get("amount_usd")), "price_usd": _f(t.get("price_usd")),
        "maker_tags": ",".join(t.get("maker_tags") or []) or None,
        "maker_token_tags": ",".join(t.get("maker_token_tags") or []) or None,
        "is_open_or_close": t.get("is_open_or_close"),
        "wallet_balance_after": _f(t.get("balance")),
        "wallet_bought_amount": _f(t.get("history_bought_amount")),
        "wallet_realized_profit": _f(t.get("realized_profit")),
        "wallet_unrealized_profit": _f(t.get("unrealized_profit")),
        "priority_fee": _f(t.get("priority_fee")), "tip_fee": _f(t.get("tip_fee")),
        "gas_usd": _f(t.get("gas_usd")),
    } for t in hist]


def holder_rows(body: dict, token: str) -> list[dict]:
    lst = body["data"]["list"]
    return [{
        "token": token, "rank": i + 1, "wallet": h.get("address"),
        "token_account": h.get("account_address"), "addr_type": h.get("addr_type"),
        # A pool name (e.g. pump_amm) for pool wallets, empty for ordinary wallets.
        "exchange": h.get("exchange") or None, "balance": _f(h.get("balance")),
        "share": _f(h.get("amount_percentage")), "usd_value": _f(h.get("usd_value")),
        "avg_cost": _f(h.get("cost")),
        "total_cost": _f(h.get("accu_cost") or h.get("total_cost")),
        "profit": _f(h.get("profit")), "netflow_usd": _f(h.get("netflow_usd")),
        "bought_cost": _f(h.get("history_bought_cost")),
        "sold_income": _f(h.get("history_sold_income")),
        "transfer_in": _f(h.get("history_transfer_in_amount")),
        "transfer_out": _f(h.get("history_transfer_out_amount")),
        "tags": ",".join(h.get("tags") or []) or None,
        # Per-token roles: creator, dev_team, sniper, bundler, top_holder, transfer_in ...
        "token_tags": ",".join(h.get("maker_token_tags") or []) or None,
        "wallet_tag": h.get("wallet_tag_v2"),
    } for i, h in enumerate(lst)]


def wallet_rank_rows(body: dict, window: str) -> list[dict]:
    rank = body["data"]["rank"]
    keep = ["pnl_1d", "pnl_7d", "pnl_30d", "realized_profit_1d", "realized_profit_7d",
            "realized_profit_30d", "winrate_7d", "winrate_30d", "buy_7d", "sell_7d",
            "txs_7d", "avg_holding_period_7d", "net_inflow_7d", "last_active",
            "pnl_gt_5x_num_7d", "pnl_lt_minus_dot5_num_7d"]
    return [{"window": window, "rank": i + 1, "wallet": w.get("address"),
             "name": w.get("name") or w.get("nickname"),
             "tags": ",".join(w.get("tags") or []) or None,
             **{k: _f(w.get(k)) for k in keep}} for i, w in enumerate(rank)]
