from datetime import UTC, datetime, timedelta

import httpx

from trench.http import HttpClient
from trench.ingest import trades
from trench.lake import Lake
from trench.pit import PITStore
from trench.rawstore import RawStore
from trench.sources import geckoterminal as gt

TOK = "TokA111111111111111111111111111111111111111"
SOL = "So11111111111111111111111111111111111111112"


def _trade(i, ts, side="buy"):
    frm, to = (SOL, TOK) if side == "buy" else (TOK, SOL)
    return {"id": f"solana_tx{i}_0", "attributes": {
        "tx_hash": f"tx{i}", "block_number": i, "block_timestamp": ts.isoformat(),
        "tx_from_address": "Wallet1", "from_token_address": frm, "to_token_address": to,
        "from_token_amount": "1.5", "to_token_amount": "1000", "volume_in_usd": "100",
        "price_to_in_usd": "0.1", "price_from_in_usd": "66", "kind": side,
        "is_anomalous": False}}


def test_trade_rows_normalize_to_token():
    t0 = datetime(2026, 11, 17, 12, tzinfo=UTC)
    rows = gt.trade_rows({"data": [_trade(1, t0), _trade(2, t0, "sell")]}, "solana", "P", TOK)
    assert [r["side"] for r in rows] == ["buy", "sell"]
    assert rows[0]["token_amount"] == 1000.0 and rows[0]["quote_token"] == SOL
    assert rows[1]["token_amount"] == 1.5 and rows[1]["wallet"] == "Wallet1"


def _run(tmp_path, feed):
    def handler(req):
        return httpx.Response(200, json={"data": feed})

    raw = RawStore(tmp_path / "raw")
    c = HttpClient(source="geckoterminal", base_url=gt.BASE_URL, raw_store=raw,
                   max_per_minute=10_000, transport=httpx.MockTransport(handler),
                   sleep=lambda s: None)
    lake = Lake(tmp_path / "lake")
    return lake, trades.run_cycle(lake, raw, PITStore(tmp_path / "pub"), c,
                                  pools=[("solana", "P", TOK)])


def test_dedupes_across_polls_and_flags_gaps(tmp_path):
    t0 = datetime.now(UTC) - timedelta(hours=1)
    feed1 = [_trade(i, t0 + timedelta(seconds=i)) for i in range(5)]
    lake, r1 = _run(tmp_path, feed1)
    assert r1.new_trades == 5 and r1.gaps == 0

    # Same feed again: nothing new.
    _, r2 = _run(tmp_path, feed1)
    assert r2.new_trades == 0

    # A full feed (300) whose oldest trade is newer than anything stored: a gap.
    later = t0 + timedelta(minutes=30)
    full = [_trade(1000 + i, later + timedelta(seconds=i)) for i in range(trades.FEED_MAX)]
    _, r3 = _run(tmp_path, full)
    assert r3.new_trades == trades.FEED_MAX and r3.gaps == 1
    gaps = lake.connect().execute("SELECT count(*) FROM gt_trade_polls WHERE gap").fetchone()
    assert gaps == (1,)
