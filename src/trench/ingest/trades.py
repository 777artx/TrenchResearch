"""Trade collector: GeckoTerminal's recent-trades feed for every universe pool.

Each call returns at most the last 300 trades of a pool from the last 24 hours, so
the collector polls repeatedly and keeps only trades it has not stored yet. It also
records, per pool and poll, whether the feed reached back to the previous poll.
If it did not, trades in between were missed; that gap is logged rather than
hidden (``gt_trade_polls.gap``), and coverage is reported per pool and day.

Pools: for each token in the current universe on an active chain, its most liquid
pair in the latest DexScreener snapshot.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from trench import chains, universe
from trench.http import HttpClient, NotFound, UpstreamError
from trench.lake import Lake
from trench.pit import PITStore
from trench.rawstore import RawStore
from trench.sources import geckoterminal as gt
from trench.timeutil import utcnow

log = logging.getLogger(__name__)
FEED_MAX = 300
FLUSH_EVERY = 20  # pools; save progress so an interrupted cycle keeps its data


@dataclass
class TradesReport:
    run_id: str
    pools: int = 0
    requests: int = 0
    new_trades: int = 0
    gaps: int = 0
    errors: list[str] = field(default_factory=list)


def target_pools(lake: Lake, pit: PITStore) -> list[tuple[str, str, str]]:
    """(chain, pool_address, token) for the most liquid pair of each universe token."""
    members = universe.members(pit, utcnow().date())
    if not members or "dxs_pair_snapshot" not in lake.tables():
        return []
    con = lake.connect()
    con.execute("CREATE TEMP TABLE m(chain VARCHAR, token VARCHAR)")
    con.executemany("INSERT INTO m VALUES (?, ?)", [e.split(":", 1) for e in sorted(members)])
    return con.execute(
        """SELECT p.chain, arg_max(p.pair_address, p.liquidity_usd), p.base_token
           FROM dxs_pair_snapshot p JOIN m ON p.chain = m.chain AND p.base_token = m.token
           WHERE p.run_id = (SELECT max(run_id) FROM dxs_pair_snapshot)
           GROUP BY p.chain, p.base_token ORDER BY 1, 3"""
    ).fetchall()


def _state(lake: Lake) -> tuple[dict, set]:
    """Newest stored trade time per pool, and trade ids seen in the last 2 days."""
    if "gt_trades" not in lake.tables():
        return {}, set()
    con = lake.connect()
    newest = dict(
        ((c, p), ts) for c, p, ts in con.execute(
            "SELECT chain, pool_address, max(block_timestamp) FROM gt_trades GROUP BY ALL"
        ).fetchall()
    )
    since = utcnow() - timedelta(days=2)
    seen = {r[0] for r in con.execute(
        "SELECT trade_id FROM gt_trades WHERE block_timestamp >= ?", [since]).fetchall()}
    return newest, seen


def run_cycle(lake: Lake, raw: RawStore, pit: PITStore, client: HttpClient | None = None,
              pools: list[tuple[str, str, str]] | None = None) -> TradesReport:
    started = utcnow()
    rep = TradesReport(run_id=f"trd_{started:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}")
    own = client is None
    client = client or HttpClient(
        source=gt.SOURCE, base_url=gt.BASE_URL, raw_store=raw,
        max_per_minute=gt.MAX_PER_MINUTE, headers=gt.HEADERS, backoff_base=gt.BACKOFF_BASE,
    )
    pools = pools if pools is not None else target_pools(lake, pit)
    rep.pools = len(pools)
    newest, seen = _state(lake)
    trades, polls = [], []
    part = 0

    def flush() -> None:
        nonlocal trades, polls, part
        now = utcnow()
        if trades:
            lake.write("gt_trades", trades, run_id=f"{rep.run_id}_{part:03d}", fetched_at=now)
            rep.new_trades += len(trades)
        if polls:
            lake.write("gt_trade_polls", polls, run_id=f"{rep.run_id}_{part:03d}",
                       fetched_at=now)
        trades, polls, part = [], [], part + 1

    try:
        for i, (chain, pool, token) in enumerate(pools):
            if i and i % FLUSH_EVERY == 0:
                flush()
            net = chains.CHAINS[chain].geckoterminal
            rep.requests += 1
            polled_at = utcnow()
            try:
                f = client.get_json(f"/networks/{net}/pools/{pool}/trades")
            except (NotFound, UpstreamError) as exc:
                rep.errors.append(str(exc)[:200])
                continue
            rows = gt.trade_rows(f.data, chain, pool, token)
            n_feed = len(f.data.get("data") or [])
            oldest = min((r["block_timestamp"] for r in rows), default=None)
            prev = newest.get((chain, pool))
            # Gap: the feed was full and its oldest trade is newer than what we had,
            # so trades between ``prev`` and ``oldest`` were never seen.
            gap = bool(prev is not None and n_feed >= FEED_MAX and oldest is not None
                       and oldest > prev)
            fresh = [r for r in rows if r["trade_id"] not in seen]
            for r in fresh:
                r["raw_sha256"] = f.raw.sha256
                seen.add(r["trade_id"])
            trades += fresh
            rep.gaps += gap
            polls.append({"chain": chain, "pool_address": pool, "token": token,
                          "polled_at": polled_at, "n_feed": n_feed, "n_new": len(fresh),
                          "oldest_in_feed": oldest, "prev_newest": prev, "gap": gap,
                          "first_poll": prev is None})
    finally:
        flush()
        if own:
            client.close()
    log.info("trades cycle %s: %d pools, %d new trades, %d gaps", rep.run_id, rep.pools,
             rep.new_trades, rep.gaps)
    return rep
