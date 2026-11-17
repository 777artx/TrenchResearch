"""Daily Solana transfer extract for tracked mints (BigQuery).

Tracked mints are the Solana tokens in the universe plus every registered Solana
token with at least $25K liquidity in its latest snapshot. This is a raw-ingestion
choice, not a scoring one: indicators filter to the point-in-time universe later,
so using today's token list to fetch past days introduces no look-ahead.

Each run writes ``sol_transfers`` (one row per transfer, numeric values as strings
to keep full precision) and appends a line to ``sol_extract_log`` with the job id,
bytes scanned and the mint list hash, so every extract is reproducible.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

import pyarrow as pa
import pyarrow.compute as pc

from trench.lake import Lake
from trench.sources import bq_solana
from trench.timeutil import utcnow


def tracked_mints(lake: Lake, min_liquidity: float = 25_000.0) -> list[str]:
    con = lake.connect()
    tables = set(lake.tables())
    mints: set[str] = set()
    if "dxs_pair_snapshot" in tables:
        mints |= {
            r[0]
            for r in con.execute(
                """SELECT base_token FROM dxs_pair_snapshot
                   WHERE chain = 'solana'
                     AND run_id = (SELECT max(run_id) FROM dxs_pair_snapshot
                                   WHERE chain = 'solana')
                   GROUP BY base_token HAVING sum(liquidity_usd) >= ?""",
                [min_liquidity],
            ).fetchall()
        }
    return sorted(m for m in mints if m)


def run(lake: Lake, start: datetime, end: datetime, *, mints: list[str] | None = None,
        max_gb: float = 25.0, bq=None) -> dict:
    mints = mints if mints is not None else tracked_mints(lake)
    bq = bq or bq_solana.client()
    res = bq_solana.extract_transfers(bq, start, end, mints, max_gb=max_gb)
    t = res.table
    # BigQuery NUMERIC arrives as decimal128; keep exact values as strings.
    for col in ("value",):
        if col in t.column_names:
            t = t.set_column(t.column_names.index(col), col, pc.cast(t[col], pa.string()))
    fetched_at = utcnow()
    run_id = f"solx_{start:%Y%m%dT%H}_{fetched_at:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    lake.write("sol_transfers", t, run_id=run_id, fetched_at=fetched_at)
    log = {
        "window_start": start, "window_end": end, "n_mints": len(mints),
        "mints_sha256": hashlib.sha256("\n".join(sorted(mints)).encode()).hexdigest(),
        "rows": t.num_rows, "n_tx": len(pc.unique(t["tx_signature"])) if t.num_rows else 0,
        "bytes_processed": res.bytes_processed, "bytes_billed": res.bytes_billed,
        "job_id": res.job_id,
    }
    lake.write("sol_extract_log", [log], run_id=run_id, fetched_at=fetched_at)
    return log
