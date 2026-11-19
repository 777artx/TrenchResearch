import json
from pathlib import Path

from trench.sources import gmgn

FIX = Path(__file__).parent / "fixtures" / "gmgn"


def test_trade_rows_from_real_response():
    body = json.loads((FIX / "token_trades_v2.json").read_text())
    rows = gmgn.trade_rows(body, "TOK")
    assert len(rows) == 50
    r = rows[0]
    assert {x["side"] for x in rows} <= {"buy", "sell", "add", "remove", "burn"}
    assert r["wallet"] and r["block_time"].year >= 2026
    trades = [x for x in rows if x["side"] in ("buy", "sell")]
    assert trades and all(x["usd"] is not None for x in trades) and r["trade_id"]


def test_holder_and_rank_rows_from_real_responses():
    h = gmgn.holder_rows(json.loads((FIX / "token_holders_.json").read_text()), "TOK")
    assert len(h) == 100 and h[0]["rank"] == 1 and h[0]["wallet"]
    w = gmgn.wallet_rank_rows(json.loads((FIX / "rank_sol_wallets_7d.json").read_text()), "7d")
    assert len(w) == 100 and w[0]["wallet"]


def test_shape_change_raises():
    import pytest

    with pytest.raises(KeyError):
        gmgn.trade_rows({"data": {"items": []}}, "TOK")
