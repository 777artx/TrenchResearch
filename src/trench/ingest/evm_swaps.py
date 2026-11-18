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
MAX_TX_LOOKUPS = 100_000  # per run; the rest carry over


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
        rpc: EvmRPC | None = None, pools: list[dict] | None = None) -> EvmReport:
    rep = EvmReport(run_id=f"evm_{chain}_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}",
                    chain=chain)
    own = rpc is None
    rpc = rpc or EvmRPC(RPC_URLS[chain], per_minute=120)
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
        start = min(cursor.get(p["pool_id"], default_start - 1) + 1 for p in grp)
        ids = [p["pool_id"] for p in grp]
        if kind == "v4":
            address, topics = evm_swaps.V4_POOL_MANAGER[chain], [evm_swaps.TOPIC_V4, ids]
        else:
            address, topics = ids, [evm_swaps.POOL_TOPICS]
        try:
            for logs in rpc.get_logs(start, head, address=address, topics=topics):
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
        for i in range(0, len(todo), TX_BATCH):
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
    log.info("evm %s: %d pools, %d swaps, %d tx lookups, %d rpc calls", chain, rep.pools,
             rep.swaps, rep.tx_lookups, rep.rpc_calls)
    return rep


__all__ = ["run", "tracked_pools", "chains"]
