"""Daily GMGN collection for the Solana universe (trades, holders, smart-wallet ranks).

Tables (all point in time, append-only):
* ``gmgn_trades``          new trades per token since the last stored trade
* ``gmgn_holders``         top-100 holders snapshot per token, with cost basis
* ``gmgn_wallet_rank``     top-100 wallets by PnL over 1d, 7d and 30d
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from trench import universe
from trench.lake import Lake
from trench.pit import PITStore
from trench.rawstore import RawStore
from trench.sources import gmgn
from trench.timeutil import utcnow

log = logging.getLogger(__name__)
SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "gmgn" / "collect.js"
FIRST_RUN_PAGES = 10   # 500 trades on first sight of a token
DAILY_PAGES = 40       # upper bound per token per run when catching up


def build_jobs(lake: Lake, pit: PITStore) -> list[dict]:
    tokens = sorted(e.split(":", 1)[1] for e in universe.members(pit, utcnow().date())
                    if e.startswith("solana:"))
    last = {}
    if "gmgn_trades" in lake.tables():
        last = dict(lake.connect().execute(
            "SELECT token, epoch(max(block_time))::BIGINT FROM gmgn_trades GROUP BY 1").fetchall())
    jobs = [{"id": f"rank:{w}", "path": f"/api/v1/rank/sol/wallets/{w}",
             "params": {"orderby": f"pnl_{w}", "direction": "desc"}, "pages": 1}
            for w in ("1d", "7d", "30d")]
    for t in tokens:
        jobs.append({"id": f"trades:{t}", "path": f"/vas/api/mul-region/token_trades_v2/sol/{t}",
                     "params": {"limit": 50},
                     "pages": DAILY_PAGES if t in last else FIRST_RUN_PAGES,
                     "stop_ts": last.get(t)})
        jobs.append({"id": f"holders:{t}", "path": f"/vas/api/v1/token_holders/sol/{t}",
                     "params": {"limit": 100, "cost": 20, "orderby": "amount_percentage",
                                "direction": "desc"}, "pages": 1})
    return jobs


def run(lake: Lake, raw: RawStore, pit: PITStore, jobs: list[dict] | None = None,
        timeout_s: int = 1500) -> dict:
    jobs = jobs if jobs is not None else build_jobs(lake, pit)
    run_id = f"gmgn_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    with tempfile.TemporaryDirectory() as td:
        jf, of = Path(td) / "jobs.json", Path(td) / "out.jsonl"
        jf.write_text(json.dumps(jobs))
        env = dict(os.environ)
        if Path("/opt/pw-browsers/chromium").exists() and "PW_CHROMIUM" not in env:
            pass  # the pre-installed Playwright finds its own browser
        proc = subprocess.run(["node", str(SCRIPT), str(jf), str(of)], capture_output=True,
                              text=True, timeout=timeout_s, env=env)
        lines = of.read_text().splitlines() if of.exists() else []
    if proc.returncode != 0 and not lines:
        raise RuntimeError(f"gmgn collector failed: {proc.stderr[-400:]}")

    seen: set[str] = set()
    if "gmgn_trades" in lake.tables():
        since = utcnow() - timedelta(days=3)
        seen = {r[0] for r in lake.connect().execute(
            "SELECT trade_id FROM gmgn_trades WHERE block_time >= ?", [since]).fetchall()}
    out: dict[str, list[dict]] = {"gmgn_trades": [], "gmgn_holders": [], "gmgn_wallet_rank": []}
    errors = []
    for line in lines:
        rec = json.loads(line)
        rr = raw.save(source="gmgn", url=rec["url"], endpoint=rec["id"], params={},
                      status=rec["status"], body=json.dumps(rec["body"]).encode(),
                      fetched_at=utcnow())
        kind, _, key = rec["id"].partition(":")
        if rec["status"] != 200 or not isinstance(rec["body"], dict):
            errors.append(f"{rec['id']}: {rec['status']}")
            continue
        try:
            if kind == "trades":
                rows = [r for r in gmgn.trade_rows(rec["body"], key) if r["trade_id"] not in seen]
                seen |= {r["trade_id"] for r in rows}
                out["gmgn_trades"] += [{**r, "raw_sha256": rr.sha256} for r in rows]
            elif kind == "holders":
                out["gmgn_holders"] += [{**r, "raw_sha256": rr.sha256}
                                        for r in gmgn.holder_rows(rec["body"], key)]
            elif kind == "rank":
                out["gmgn_wallet_rank"] += [{**r, "raw_sha256": rr.sha256}
                                            for r in gmgn.wallet_rank_rows(rec["body"], key)]
        except (KeyError, TypeError) as exc:  # shape changed: fail loudly in the report
            errors.append(f"{rec['id']}: unexpected shape ({exc})")
    now = utcnow()
    for table, rows in out.items():
        if rows:
            lake.write(table, rows, run_id=run_id, fetched_at=now)
    rep = {"run_id": run_id, "jobs": len(jobs), "responses": len(lines),
           "rows": {k: len(v) for k, v in out.items()}, "errors": errors[:10],
           "n_errors": len(errors)}
    if lines and len(errors) > len(lines) / 2:
        raise RuntimeError(f"gmgn: most responses failed: {rep}")
    return rep
