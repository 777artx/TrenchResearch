from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from trench import chains
from trench.http import HttpClient, NotFound, UpstreamError
from trench.lake import Lake, changed_rows
from trench.rawstore import RawStore
from trench.sources import defillama as dl
from trench.timeutil import utcnow


def run(lake: Lake, raw: RawStore, client: HttpClient | None = None) -> dict:
    run_id = f"llama_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    own = client is None
    client = client or HttpClient(source=dl.SOURCE, base_url=dl.BASE_URL, raw_store=raw,
                                  max_per_minute=dl.MAX_PER_MINUTE)
    rows, errors = [], []
    today = utcnow().date()
    try:
        for cid in chains.ACTIVE:
            try:
                f = client.get_json(
                    f"/overview/dexs/{dl.CHAIN_NAMES[cid]}",
                    {"excludeTotalDataChart": "false",
                     "excludeTotalDataChartBreakdown": "true", "dataType": "dailyVolume"},
                )
            except (NotFound, UpstreamError) as exc:
                errors.append(str(exc)[:200])
                continue
            for r in dl.dex_daily_rows(f.data, cid, before=today):
                r["raw_sha256"] = f.raw.sha256
                rows.append(r)
    finally:
        if own:
            client.close()
    rows = changed_rows(lake, "llama_dex_daily", rows, ["chain", "day"])
    if rows:
        lake.write("llama_dex_daily", rows, run_id=run_id, fetched_at=utcnow())
    prices = run_prices(lake, raw, run_id)
    return {"run_id": run_id, "rows": len(rows), "price_rows": prices, "errors": errors}


def run_prices(lake: Lake, raw: RawStore, run_id: str, start: date = date(2023, 1, 1)) -> int:
    """Daily ETH and SOL prices from start to yesterday (coins.llama.fi)."""
    client = HttpClient(source="defillama_coins", base_url=dl.COINS_URL, raw_store=raw,
                        max_per_minute=dl.MAX_PER_MINUTE)
    today = utcnow().date()
    rows: list[dict] = []
    try:
        for asset, coin in dl.PRICE_ASSETS.items():
            cur = start
            while cur < today:
                ts = int(datetime(cur.year, cur.month, cur.day, tzinfo=UTC).timestamp())
                f = client.get_json(f"/chart/{coin}",
                                    {"start": ts, "span": dl.MAX_POINTS, "period": "1d"})
                for r in dl.price_rows(f.data, asset, coin, before=today):
                    r["raw_sha256"] = f.raw.sha256
                    rows.append(r)
                cur += timedelta(days=dl.MAX_POINTS)
    finally:
        client.close()
    rows = changed_rows(lake, "llama_price_daily", rows, ["asset", "day"])
    if rows:
        lake.write("llama_price_daily", rows, run_id=run_id, fetched_at=utcnow())
    return len(rows)
