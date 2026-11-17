import json
from datetime import date

import httpx

from trench.http import HttpClient
from trench.ingest import tehcscreener as ingest
from trench.lake import Lake
from trench.rawstore import RawStore
from trench.sources import tehcscreener as teh


def load(fixtures, name):
    return json.loads((fixtures / "tehcscreener" / name).read_text())


def test_trench_fixture_method_and_today(fixtures):
    body = load(fixtures, "trench.json")
    m = json.loads(teh.trench_method(body)[0]["method_json"])
    assert m["blend"] == {"short": 0.6, "long": 0.4}
    assert m["cooldown"] == 0.65
    today = teh.trench_today(body)
    weights = m["weights"]
    raw = sum(weights[r["component"]] * r["percentile"] for r in today)
    # On a non-drop day the published score is the weighted sum of blended percentiles.
    assert round(raw) == today[0]["score"] == 23
    hist = teh.trench_history(body)
    assert hist[0]["day"] == date(2024, 2, 20) and len(hist) == 1001


def test_series_are_aligned_to_days(fixtures):
    body = load(fixtures, "launchpads_series_7d.json")
    rows = teh.launchpad_series(body)
    assert len(rows) == len(body["days"]) * len(body["series"])
    pump = [r for r in rows if r["pad"] == "pumpfun"]
    assert pump[0]["day"] == date.fromisoformat(body["days"][0])
    assert pump[-1]["tokens_launched"] == body["series"][0]["tokens_launched"][-1]

    bots = teh.bots_series(load(fixtures, "bots_7d.json"))
    assert {"bot", "day", "volume_usd", "txns", "fees_usd"} <= set(bots[0])


def test_null_revenue_series_stays_null():
    body = {
        "days": ["2026-11-15", "2026-11-16"],
        "series": [
            {
                "chain": "arc",
                "pad": "x",
                "volume_usd": [1.0, 2.0],
                "tokens_launched": [3, 4],
                "revenue_usd": None,
            }
        ],
    }
    assert all(r["revenue_usd"] is None for r in teh.launchpad_series(body))


# ---- end-to-end ingest against a fake upstream ------------------------------------------
DAYS = ["2026-11-15", "2026-11-16"]
FAKE = {
    "/api/v1/status": {
        "synced_at": "2026-11-17 04:00:00+00",
        "source": "pipeline",
        "rows_grain": 1,
        "rows_pad": 1,
        "note": None,
    },
    "/api/v1/launchpads/series": {
        "window": "all",
        "through": DAYS[-1],
        "days": DAYS,
        "series": [
            {
                "chain": "solana",
                "pad": "pumpfun",
                "volume_usd": [1.0, 2.0],
                "tokens_launched": [10, 11],
                "revenue_usd": [0.1, 0.2],
            }
        ],
    },
    "/api/v1/launchpads/solana/pumpfun": {
        "chain": "solana",
        "pad": "pumpfun",
        "window": "all",
        "tokens_mode": "traded",
        "profile": {"name": "pump.fun"},
        "daily": [
            {"day": d, "tokens_launched": 1, "volume_usd": 1.0, "trade_txns": 5} for d in DAYS
        ],
        "top_tokens": [{"token": "Tok1", "volume_usd": 9.0, "trade_txns": 3, "first_day": DAYS[0]}],
    },
    "/api/v1/launchpads/solana/pumpfun/revenue": {
        "chain": "solana",
        "project": "pumpfun",
        "daily": [
            {
                "day": DAYS[0],
                "protocol_revenue_usd": 0.1,
                "creator_revenue_usd": None,
                "source": "allium_events",
                "buyback_usd": None,
            }
        ],
    },
    "/api/v1/bots": {
        "window": "all",
        "group": "bot",
        "chains": ["solana"],
        "through": DAYS[-1],
        "days": DAYS,
        "series": [
            {"name": "axiom", "volume_usd": [5.0, 6.0], "txns": [1, 2], "fees_usd": [0.05, 0.06]}
        ],
    },
    "/api/v1/bots/axiom": {
        "bot": "axiom",
        "window": "all",
        "through": DAYS[-1],
        "days": DAYS,
        "wallets_dedup": [None, 7],
        "series": [
            {
                "name": "solana",
                "volume_usd": [5.0, 6.0],
                "txns": [1, 2],
                "fees_usd": [0.05, 0.06],
                "wallets": [3, 4],
            }
        ],
        "top_tokens": [
            {"chain": "solana", "token": "Tok1", "volume_usd": 1.0, "txns": 1, "peak_wallets": 30}
        ],
    },
    "/api/v1/bots/axiom/perps": {
        "bot": "axiom",
        "days": [],
        "volume_usd": [],
        "fees_usd": [],
        "txns": [],
        "wallets": [],
    },
    "/api/v1/chains": {"chains": [{"chain": "solana"}]},
    "/api/v1/chains/solana": {
        "chain": "solana",
        "window": "all",
        "days": DAYS,
        "txns": [1, 2],
        "active_wallets": [3, 4],
        "dex_volume_usd": [5.0, 6.0],
        "dex_trades": [7, 8],
    },
    "/api/v1/rwa": {
        "through": DAYS[-1],
        "rows": [
            {
                "day": DAYS[0],
                "chain": "robinhood",
                "volume_usd": 1.0,
                "value_usd": None,
                "swaps": 1,
                "assets_traded": 1,
                "assets_valued": 0,
            }
        ],
    },
    "/api/v1/dexes": {"window": "all", "dexes": [{"chain": "solana", "dex": "pumpswap"}]},
    "/api/v1/dexes/solana/pumpswap": {
        "chain": "solana",
        "dex": "pumpswap",
        "daily": [
            {
                "day": DAYS[0],
                "volume_usd": 1.0,
                "trades": 2,
                "pools": 3,
                "traders": 4,
                "protocol_revenue_usd": 0.01,
            }
        ],
    },
}


def test_ingest_end_to_end(tmp_path, fixtures):
    fake = dict(FAKE)
    fake["/api/v1/trench"] = load(fixtures, "trench.json")

    def handler(req: httpx.Request):
        body = fake.get(req.url.path)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404)

    raw = RawStore(tmp_path / "raw")
    client = HttpClient(
        source="tehcscreener",
        base_url=teh.BASE_URL,
        raw_store=raw,
        max_per_minute=10_000,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
    )
    lake = Lake(tmp_path / "lake")
    rep = ingest.run(lake, raw, client)
    assert rep.not_found == []
    assert rep.rows["teh_launchpad_series"] == 2
    assert rep.rows["teh_trench_history"] == 1001
    con = lake.connect()
    # every row is traceable to a cached raw body
    n_null = con.execute("SELECT count(*) FROM teh_dex_daily WHERE raw_sha256 IS NULL").fetchone()
    assert n_null == (0,)
    assert con.execute(
        "SELECT wallets_dedup FROM teh_bot_wallets_dedup ORDER BY day"
    ).fetchall() == [(None,), (7,)]
    # a second run adds a new version rather than overwriting
    ingest.run(lake, raw, client)
    assert con.execute("SELECT count(DISTINCT run_id) FROM teh_trench_history").fetchone() == (2,)
