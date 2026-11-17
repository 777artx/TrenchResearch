from datetime import UTC, date, datetime, timedelta

import httpx

from trench import universe
from trench.http import HttpClient
from trench.ingest import markets
from trench.lake import Lake
from trench.pit import PITStore
from trench.rawstore import RawStore
from trench.sources import dexscreener as dxs
from trench.sources import geckoterminal as gt

SOL_TOK = "TokA111111111111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"
EVM_TOK = "0xABCdef0000000000000000000000000000000001"


def _gt_pool(addr, base, quote, reserve, mcap, net="solana"):
    return {
        "id": f"{net}_{addr}",
        "attributes": {"address": addr, "name": "A / SOL", "reserve_in_usd": str(reserve),
                       "market_cap_usd": None if mcap is None else str(mcap), "fdv_usd": "9e6",
                       "volume_usd": {"h24": "1000"}, "base_token_price_usd": "0.01",
                       "transactions": {"h24": {"buys": 5, "sells": 4, "buyers": 3, "sellers": 2}},
                       "pool_created_at": "2026-11-01T00:00:00Z"},
        "relationships": {"base_token": {"data": {"id": f"{net}_{base}"}},
                          "quote_token": {"data": {"id": f"{net}_{quote}"}},
                          "dex": {"data": {"id": "pumpswap"}}},
    }


def test_gt_pool_rows_parse_ids_and_lowercase_evm():
    body = {"data": [_gt_pool("0xPOOL", EVM_TOK, "0xQ", 1, None, net="base")]}
    r = gt.pool_rows(body, "base", "top")[0]
    assert r["chain"] == "base" and r["base_token"] == EVM_TOK.lower()
    assert r["pool_address"] == "0xpool" and r["market_cap_usd"] is None
    assert gt.pool_rows(body, "unknown_net", "top") == []


def test_ohlcv_drops_incomplete_current_day():
    ts = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())  # noqa: E731
    today = date(2026, 11, 17)
    body = {"data": {"attributes": {"ohlcv_list": [
        [ts(today), 1, 1, 1, 1, 1], [ts(today - timedelta(1)), 1, 2, 0.5, 1.5, 10]]}}}
    rows = gt.ohlcv_rows(body, "solana", "P", SOL_TOK, before=today)
    assert [r["day"] for r in rows] == [today - timedelta(1)]


def test_dxs_pair_rows_skip_uncovered_chains():
    body = [{"chainId": "solana", "dexId": "raydium", "pairAddress": "P1",
             "baseToken": {"address": SOL_TOK}, "quoteToken": {"address": WSOL},
             "priceUsd": "0.5", "liquidity": {"usd": 80000}, "marketCap": 2e6,
             "pairCreatedAt": 1_700_000_000_000},
            {"chainId": "tron", "pairAddress": "X", "baseToken": {}, "quoteToken": {}}]
    rows = dxs.pair_rows(body)
    assert len(rows) == 1 and rows[0]["liquidity_usd"] == 80000.0
    assert rows[0]["pair_created_at"].year == 2023


def _clients(tmp_path, liq):
    def gt_handler(req: httpx.Request):
        p = req.url.path
        if p.endswith("/ohlcv/day"):
            now = datetime.now(UTC)
            y = int((now - timedelta(days=1)).timestamp())
            return httpx.Response(200, json={"data": {"attributes": {"ohlcv_list": [
                [y, 1, 2, 0.5, 1.5, 100]]}}})
        if "/networks/solana/pools" in p and req.url.params.get("page") == "1":
            return httpx.Response(200, json={"data": [_gt_pool("P1", SOL_TOK, WSOL, 60000, 2e6)]})
        return httpx.Response(200, json={"data": []})

    def dxs_handler(req: httpx.Request):
        if "/tokens/v1/solana/" in req.url.path:
            return httpx.Response(200, json=[{
                "chainId": "solana", "dexId": "pumpswap", "pairAddress": "P1",
                "baseToken": {"address": SOL_TOK}, "quoteToken": {"address": WSOL},
                "priceUsd": "0.01", "liquidity": {"usd": liq}, "marketCap": 2e6}])
        return httpx.Response(200, json=[])

    raw = RawStore(tmp_path / "raw")
    mk = lambda src, base, h: HttpClient(  # noqa: E731
        source=src, base_url=base, raw_store=raw, max_per_minute=10_000,
        transport=httpx.MockTransport(h), sleep=lambda s: None)
    return raw, mk("geckoterminal", gt.BASE_URL, gt_handler), mk("dexscreener", dxs.BASE_URL,
                                                                  dxs_handler)


def test_markets_run_registers_snapshots_and_backfills(tmp_path):
    lake = Lake(tmp_path / "lake")
    raw, g, d = _clients(tmp_path, liq=70_000)
    cfg = markets.MarketsConfig(gt_top_pages=1, gt_new_pages=1, chains=("solana",))
    rep = markets.run(lake, raw, cfg, gt_client=g, dxs_client=d)
    assert rep.errors == [] and rep.new_tokens == 1  # WSOL is a quote asset, not registered
    assert rep.rows["dxs_pair_snapshot"] == 1 and rep.rows["gt_pool_ohlcv_day"] == 1

    # Second run: token already registered, OHLCV complete through yesterday -> no refetch.
    raw, g, d = _clients(tmp_path, liq=70_000)
    rep2 = markets.run(lake, raw, cfg, gt_client=g, dxs_client=d)
    assert rep2.new_tokens == 0 and rep2.rows["gt_pool_ohlcv_day"] == 0


def test_universe_is_point_in_time_and_keeps_dead_coins(tmp_path):
    lake, pit = Lake(tmp_path / "lake"), PITStore(tmp_path / "pub")
    t0 = datetime(2026, 11, 10, 12, tzinfo=UTC)
    snap = lambda liq, mcap: [{  # noqa: E731
        "chain": "solana", "base_token": SOL_TOK, "pair_address": "P1",
        "liquidity_usd": liq, "market_cap_usd": mcap, "fdv_usd": None}]
    lake.write("dxs_pair_snapshot", snap(10_000.0, 5e5), run_id="a", fetched_at=t0)
    lake.write("dxs_pair_snapshot", snap(90_000.0, 3e6), run_id="b",
               fetched_at=t0 + timedelta(days=2))
    lake.write("dxs_pair_snapshot", snap(0.0, 1e3), run_id="c",  # coin dies
               fetched_at=t0 + timedelta(days=5))

    # Built with data up to day 1 only: the token has not qualified yet.
    assert universe.build(lake, pit, cutoff=t0 + timedelta(days=1)) == 0
    # A later build sees the qualifying snapshot from 11-12.
    assert universe.build(lake, pit, cutoff=t0 + timedelta(days=6)) == 1
    ent = f"solana:{SOL_TOK}"
    assert ent not in universe.members(pit, date(2026, 11, 11))
    assert ent in universe.members(pit, date(2026, 11, 12))
    assert ent in universe.members(pit, date(2026, 11, 30))  # dead coin stays
    # Re-running does not republish.
    assert universe.build(lake, pit, cutoff=t0 + timedelta(days=6)) == 0


def test_quote_assets_never_enter_universe(tmp_path):
    lake, pit = Lake(tmp_path / "lake"), PITStore(tmp_path / "pub")
    lake.write("dxs_pair_snapshot", [{"chain": "solana", "base_token": WSOL, "pair_address": "X",
                                      "liquidity_usd": 1e8, "market_cap_usd": 1e10,
                                      "fdv_usd": None}],
               run_id="a", fetched_at=datetime(2026, 11, 10, tzinfo=UTC))
    assert universe.build(lake, pit, cutoff=datetime(2026, 11, 11, tzinfo=UTC)) == 0
