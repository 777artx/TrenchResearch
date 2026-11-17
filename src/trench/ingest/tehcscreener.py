"""Ingest every TEHscreener endpoint into the lake.

One run fetches full history (``window=all``) for every series. That is cheap
(about 120 requests) and, because every row is stamped with ``fetched_at``, it
records upstream revisions instead of hiding them. Top-token lists are only
meaningful as daily snapshots, so they are fetched with ``window=1d`` and can
not be backfilled: they accumulate from the first run onward.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from trench.http import HttpClient, NotFound
from trench.lake import Lake
from trench.rawstore import RawStore
from trench.sources import tehcscreener as teh
from trench.timeutil import utcnow

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    run_id: str
    requests: int = 0
    not_found: list[str] = field(default_factory=list)
    rows: dict[str, int] = field(default_factory=dict)


def run(lake: Lake, raw: RawStore, client: HttpClient | None = None) -> RunReport:
    started = utcnow()
    run_id = f"teh_{started:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    own_client = client is None
    client = client or HttpClient(
        source=teh.SOURCE, base_url=teh.BASE_URL, raw_store=raw, max_per_minute=teh.MAX_PER_MINUTE
    )
    report = RunReport(run_id=run_id)
    buf: dict[str, list[dict]] = defaultdict(list)

    def fetch(endpoint: str, params: dict | None = None):
        report.requests += 1
        try:
            f = client.get_json(endpoint, params)
        except NotFound:
            report.not_found.append(endpoint)
            return None
        return f

    def add(table: str, fn: Callable, body: dict, raw_sha: str, *args) -> None:
        for r in fn(body, *args):
            r["raw_sha256"] = raw_sha
            buf[f"teh_{table}"].append(r)

    try:
        # Status first, so the run records which upstream sync it read.
        if f := fetch("/status"):
            add("status", teh.status, f.data, f.raw.sha256)

        # Launchpads
        if f := fetch("/launchpads/series", {"window": "all"}):
            add("launchpad_series", teh.launchpad_series, f.data, f.raw.sha256)
            through = f.data.get("through")
            pads = [(s["chain"], s["pad"]) for s in f.data["series"]]
            for chain, pad in pads:
                if g := fetch(f"/launchpads/{chain}/{pad}", {"window": "all"}):
                    add("launchpad_daily", teh.launchpad_detail_daily, g.data, g.raw.sha256)
                    add("launchpad_profile", teh.launchpad_profile, g.data, g.raw.sha256)
                for mode in ("traded", "launched"):
                    if g := fetch(f"/launchpads/{chain}/{pad}", {"window": "1d", "tokens": mode}):
                        add(
                            "launchpad_top_tokens",
                            teh.launchpad_top_tokens,
                            g.data,
                            g.raw.sha256,
                            through,
                        )
                if g := fetch(f"/launchpads/{chain}/{pad}/revenue"):
                    add("launchpad_revenue", teh.launchpad_revenue, g.data, g.raw.sha256)

        # Bots / terminals
        bots: list[str] = []
        for group in ("bot", "chain"):
            if f := fetch("/bots", {"window": "all", "group": group}):
                add(f"bots_by_{group}", teh.bots_series, f.data, f.raw.sha256)
                if group == "bot":
                    bots = [s["name"] for s in f.data["series"]]
        for bot in bots:
            if g := fetch(f"/bots/{bot}", {"window": "all"}):
                add("bot_chain_daily", teh.bot_chain_daily, g.data, g.raw.sha256)
                add("bot_wallets_dedup", teh.bot_wallets_dedup, g.data, g.raw.sha256)
                add("bot_profile", teh.bot_profile, g.data, g.raw.sha256)
            if g := fetch(f"/bots/{bot}", {"window": "1d"}):
                add("bot_top_tokens", teh.bot_top_tokens, g.data, g.raw.sha256)
            if g := fetch(f"/bots/{bot}/perps"):
                add("bot_perps_daily", teh.bot_perps_daily, g.data, g.raw.sha256)

        # Chains
        if f := fetch("/chains"):
            for c in f.data["chains"]:
                if g := fetch(f"/chains/{c['chain']}", {"window": "all"}):
                    add("chain_daily", teh.chain_daily, g.data, g.raw.sha256)

        # RWA
        if f := fetch("/rwa"):
            add("rwa_daily", teh.rwa_daily, f.data, f.raw.sha256)

        # DEXes
        if f := fetch("/dexes", {"window": "all"}):
            for d in f.data["dexes"]:
                if g := fetch(f"/dexes/{d['chain']}/{d['dex']}"):
                    add("dex_daily", teh.dex_daily, g.data, g.raw.sha256)

        # Trench Index (competitor reference, stored for comparison only)
        if f := fetch("/trench"):
            add("trench_history", teh.trench_history, f.data, f.raw.sha256)
            add("trench_today", teh.trench_today, f.data, f.raw.sha256)
            add("trench_method", teh.trench_method, f.data, f.raw.sha256)
    finally:
        if own_client:
            client.close()

    fetched_at = utcnow()
    for table, rows in sorted(buf.items()):
        lake.write(table, rows, run_id=run_id, fetched_at=fetched_at)
        report.rows[table] = len(rows)
    log.info("tehcscreener run %s: %d requests, %d tables", run_id, report.requests, len(buf))
    return report
