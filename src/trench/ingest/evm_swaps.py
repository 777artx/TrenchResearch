"""Swap history for universe pools on EVM chains (Robinhood, Base, Ethereum).

For each universe token on the chain, every pair with at least $25K liquidity in
the latest DexScreener snapshot is tracked. Logs are read from the block after the
last stored swap of the group (or ``days_back`` days ago on first sight) up to the
current head. The trader of each swap is the transaction's sender (``tx.from``),
fetched in batches and cached in ``evm_tx_from``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from trench import chains, evm_swaps, universe
from trench.lake import Lake
from trench.pit import PITStore
from trench.sources.evm_rpc import RPC_URLS, EvmRPC
from trench.timeutil import utcnow

log = logging.getLogger(__name__)
BLOCKS_PER_DAY = {"robinhood": 842_000, "base": 43_200, "ethereum": 7_200}
GROUP = 20
TX_BATCH = 100  # Robinhood's RPC accepts 100 per batch (200 fails)
MAX_TX_LOOKUPS = 15_000  # per chain per run (~15 min at 1,000/min); the rest carry over
CALLS_PER_MINUTE = 1_000  # counts items inside batches; ~1,200/min was the last safe rate


@dataclass
class EvmReport:
    run_id: str
    chain: str
    pools: int = 0
    swaps: int = 0
    tx_lookups: int = 0
    rpc_calls: int = 0
    errors: list[str] = field(default_factory=list)


def tracked_pools(lake: Lake, pit: PITStore, chain: str, min_liq: float = 25_000.0):
    members = {e.split(":", 1)[1] for e in universe.members(pit, utcnow().date())
               if e.startswith(chain + ":")}
    if not members:
        return []
    con = lake.connect()
    rows = con.execute(
        """SELECT pair_address, base_token, quote_token, dex, liquidity_usd
           FROM dxs_pair_snapshot
           WHERE chain = ? AND run_id = (SELECT max(run_id) FROM dxs_pair_snapshot)
             AND liquidity_usd >= ?""", [chain, min_liq]).fetchall()
    out = []
    for pair, base, quote, dex, _liq in rows:
        if base in members:
            t0, t1 = sorted([base.lower(), quote.lower()])
            out.append({"pool_id": pair.lower(), "token": base, "token0": t0, "token1": t1,
                        "dex": dex, "kind": "v4" if len(pair) == 66 else "pool"})
    return out


def run(lake: Lake, pit: PITStore, chain: str, *, days_back: float = 2.0,
        rpc: EvmRPC | None = None, pools: list[dict] | None = None,
        time_budget_s: float = 480.0) -> EvmReport:
    """``time_budget_s`` bounds the log scan and the trader lookups separately, so a
    slow or throttling RPC cannot exhaust the scheduled job's time. Whatever is
    fetched is saved; the next run resumes from each pool's last stored block."""
    import time as _time

    deadline = _time.monotonic() + time_budget_s
    rep = EvmReport(run_id=f"evm_{chain}_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}",
                    chain=chain)
    own = rpc is None
    rpc = rpc or EvmRPC(RPC_URLS[chain], per_minute=CALLS_PER_MINUTE)
    pools = pools if pools is not None else tracked_pools(lake, pit, chain)
    rep.pools = len(pools)
    meta = {p["pool_id"]: p for p in pools}
    head = rpc.head()
    default_start = head - int(BLOCKS_PER_DAY[chain] * days_back)

    cursor: dict[str, int] = {}
    seen: set[tuple[str, int]] = set()
    if "evm_swaps" in lake.tables():
        con = lake.connect()
        cursor = dict(con.execute(
            "SELECT pool_id, max(block_number) FROM evm_swaps WHERE chain = ? GROUP BY 1",
            [chain]).fetchall())

    swaps: list[dict] = []
    v4 = [p for p in pools if p["kind"] == "v4"]
    other = [p for p in pools if p["kind"] != "v4"]
    groups = [("pool", other[i : i + GROUP]) for i in range(0, len(other), GROUP)]
    groups += [("v4", v4[i : i + GROUP]) for i in range(0, len(v4), GROUP)]
    for kind, grp in groups:
        if _time.monotonic() > deadline:
            rep.errors.append("time budget reached during log scan; resuming next run")
            break
        start = min(cursor.get(p["pool_id"], default_start - 1) + 1 for p in grp)
        ids = [p["pool_id"] for p in grp]
        if kind == "v4":
            address, topics = evm_swaps.V4_POOL_MANAGER[chain], [evm_swaps.TOPIC_V4, ids]
        else:
            address, topics = ids, [evm_swaps.POOL_TOPICS]
        try:
            for logs in rpc.get_logs(start, head, address=address, topics=topics):
                if _time.monotonic() > deadline:
                    break
                for lg in logs:
                    r = evm_swaps.decode(lg, chain)
                    if r is None or r["pool_id"] not in meta:
                        continue
                    if r["block_number"] <= cursor.get(r["pool_id"], -1):
                        continue  # already stored by an earlier run
                    key = (r["tx_hash"], r["log_index"])
                    if key in seen:
                        continue
                    seen.add(key)
                    m = meta[r["pool_id"]]
                    r.update(token=m["token"], token0=m["token0"], token1=m["token1"],
                             dex=m["dex"])
                    swaps.append(r)
        except Exception as exc:  # keep other groups going; report the failure
            rep.errors.append(f"{kind} group: {str(exc)[:200]}")


    # Save swaps first, so a later failure cannot lose them.
    # (Block timestamps are resolved afterwards into evm_block_ts.)
    if swaps:
        lake.write("evm_swaps", swaps, run_id=rep.run_id, fetched_at=utcnow())
    rep.swaps = len(swaps)

    # Trader = transaction sender, cached per tx hash. Includes swaps from earlier
    # runs whose lookup did not finish.
    senders: list[dict] = []
    try:
        con = lake.connect()
        tables = set(lake.tables())
        if "evm_swaps" in tables:
            known = ("SELECT tx_hash FROM evm_tx_from WHERE chain = $c"
                     if "evm_tx_from" in tables else "SELECT NULL::VARCHAR AS tx_hash WHERE false")
            todo = [h for (h,) in con.execute(
                f"""SELECT DISTINCT tx_hash FROM evm_swaps WHERE chain = $c
                    AND tx_hash NOT IN ({known}) ORDER BY 1 LIMIT {MAX_TX_LOOKUPS}""",
                {"c": chain}).fetchall()]
        else:
            todo = []
        lookup_deadline = _time.monotonic() + time_budget_s
        for i in range(0, len(todo), TX_BATCH):
            if _time.monotonic() > lookup_deadline:
                rep.errors.append(f"time budget reached at {i}/{len(todo)} tx lookups")
                break
            batch = todo[i : i + TX_BATCH]
            try:
                res = rpc.batch("eth_getTransactionByHash", [[h] for h in batch])
            except Exception as exc:
                rep.errors.append(f"tx lookup stopped at {i}/{len(todo)}: {str(exc)[:150]}")
                break
            for h, tx in zip(batch, res, strict=True):
                if tx:
                    senders.append({"chain": chain, "tx_hash": h,
                                    "tx_from": (tx.get("from") or "").lower(),
                                    "tx_to": (tx.get("to") or "").lower()})
        rep.tx_lookups = len(senders)
    finally:
        rep.rpc_calls = rpc.calls
        if own:
            rpc.close()

    if senders:
        lake.write("evm_tx_from", senders, run_id=rep.run_id, fetched_at=utcnow())
    try:
        blk_rpc = EvmRPC(RPC_URLS[chain], per_minute=CALLS_PER_MINUTE)
        resolve_block_times(lake, blk_rpc, chain, run_id=rep.run_id)
        blk_rpc.close()
    except Exception as exc:
        rep.errors.append(f"block times: {str(exc)[:150]}")
    log.info("evm %s: %d pools, %d swaps, %d tx lookups, %d rpc calls", chain, rep.pools,
             rep.swaps, rep.tx_lookups, rep.rpc_calls)
    return rep


__all__ = ["run", "tracked_pools", "chains"]


BLOCK_BATCH = 50  # Robinhood RPC rejects batches of 100
ANCHOR_STEP = 2_000  # blocks between exact timestamps (~3 minutes on Robinhood)


def _interpolate(blocks: list[int], anchors: dict[int, int]) -> dict[int, int]:
    """Linear interpolation of block timestamps between exact anchor blocks."""
    import bisect

    keys = sorted(anchors)
    out = {}
    for b in blocks:
        if b in anchors:
            out[b] = anchors[b]
            continue
        i = bisect.bisect_left(keys, b)
        if i == 0 or i == len(keys):
            continue
        b0, b1 = keys[i - 1], keys[i]
        t0, t1 = anchors[b0], anchors[b1]
        out[b] = round(t0 + (t1 - t0) * (b - b0) / (b1 - b0))
    return out


def resolve_block_times(lake: Lake, rpc: EvmRPC, chain: str, run_id: str) -> int:
    """Timestamps for blocks that have swaps but no cached time.

    Exact timestamps are fetched for anchor blocks every ``ANCHOR_STEP`` blocks and
    the blocks in between are interpolated (``exact = false``). On Robinhood that is
    about 420 lookups per day instead of one per block; the error is measured in
    docs/validation/organic_filter_v1.md.
    """
    tables = set(lake.tables())
    if "evm_swaps" not in tables:
        return 0
    known = ("SELECT block_number FROM evm_block_ts WHERE chain = $c"
             if "evm_block_ts" in tables else "SELECT NULL::BIGINT AS block_number WHERE false")
    todo = [b for (b,) in lake.connect().execute(
        f"""SELECT DISTINCT block_number FROM evm_swaps WHERE chain = $c
            AND block_number NOT IN ({known}) ORDER BY 1""", {"c": chain}).fetchall()]
    if not todo:
        return 0
    lo = todo[0] - todo[0] % ANCHOR_STEP
    hi = todo[-1] - todo[-1] % ANCHOR_STEP + ANCHOR_STEP
    anchors_needed = sorted({lo + k * ANCHOR_STEP for k in range((hi - lo) // ANCHOR_STEP + 1)}
                            | ({todo[0], todo[-1]} if len(todo) < 3 else set()))
    anchors: dict[int, int] = {}
    for i in range(0, len(anchors_needed), BLOCK_BATCH):
        batch = anchors_needed[i : i + BLOCK_BATCH]
        res = rpc.batch("eth_getBlockByNumber", [[hex(b), False] for b in batch])
        for b, blk in zip(batch, res, strict=True):
            if blk and blk.get("timestamp"):
                anchors[b] = int(blk["timestamp"], 16)
    times = _interpolate(todo, anchors)
    rows = [{"chain": chain, "block_number": b, "block_timestamp": ts, "exact": b in anchors}
            for b, ts in times.items()]
    if rows:
        lake.write("evm_block_ts", rows, run_id=f"{run_id}_blk", fetched_at=utcnow())
    return len(rows)


SWAPS_WITH_TIMES = """
SELECT s.* REPLACE (coalesce(nullif(s.block_timestamp, 0), b.block_timestamp)
                    AS block_timestamp),
       f.tx_from
FROM evm_swaps s
JOIN evm_tx_from f USING (chain, tx_hash)
LEFT JOIN (SELECT chain, block_number, any_value(block_timestamp) AS block_timestamp
           FROM evm_block_ts GROUP BY ALL) b USING (chain, block_number)
"""
