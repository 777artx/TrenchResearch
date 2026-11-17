from __future__ import annotations

import uuid

from trench import chains
from trench.http import HttpClient, NotFound, UpstreamError
from trench.lake import Lake
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
    if rows:
        lake.write("llama_dex_daily", rows, run_id=run_id, fetched_at=utcnow())
    return {"run_id": run_id, "rows": len(rows), "errors": errors}
