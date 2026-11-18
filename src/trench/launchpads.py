"""Launchpad Scorecard inputs for EVM launchpads (SPEC §6.3), starting with Long.xyz.

Long.xyz (Robinhood Chain) launches each token straight into a Uniswap V4 pool
paired against a quote token (often a tokenized stock such as META). Supply is
fixed at launch (1e9 tokens in the launch event). Per launch we collect:

* the launch (token, creator, block) from the factory's ``TokenLaunched`` event;
* its V4 pool from the PoolManager ``Initialize`` event (currency0/1 = token);
* every swap for 7 days, with the pool price from ``sqrtPriceX96``;
* the transaction sender of swaps in the first 60 minutes only (unique buyers,
  creator selling), which keeps RPC lookups small.

Outcomes follow SPEC §6.3 with uniform USD milestones; see ``score``.
"""

from __future__ import annotations

from dataclasses import dataclass

from trench import evm_swaps

INIT_TOPIC = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"


@dataclass(frozen=True)
class Pad:
    name: str
    chain: str
    factory: str
    launch_topic: str


LONG = Pad("long.xyz", "robinhood", "0x1eef016f22a943abc7dd11422edee9d235942104",
           "0x04c10fe2cc69507cbff4c84fc99414ca507db49d5c39eff84b67ea319f43ccf0")


def _addr(word: str) -> str:
    return "0x" + word[-40:].lower()


def launches(rpc, pad: Pad, start: int, end: int) -> list[dict]:
    out = []
    for logs in rpc.get_logs(start, end, address=pad.factory, topics=[pad.launch_topic],
                             step=900_000):
        for lg in logs:
            data = lg["data"][2:]
            supply = int(data[8 * 64 : 9 * 64], 16) if len(data) >= 9 * 64 else None
            out.append({"pad": pad.name, "chain": pad.chain, "token": _addr(lg["topics"][1]),
                        "creator": _addr(lg["topics"][2]),
                        "block_number": int(lg["blockNumber"], 16),
                        "tx_hash": lg["transactionHash"].lower(), "supply_raw": str(supply)})
    return out


def pools_for(rpc, chain: str, tokens: set[str], start: int, end: int) -> dict[str, dict]:
    """V4 pools initialized in [start, end] whose currency0 or currency1 is a token."""
    found = {}
    for logs in rpc.get_logs(start, end, address=evm_swaps.V4_POOL_MANAGER[chain],
                             topics=[INIT_TOPIC], step=200_000):
        for lg in logs:
            c0, c1 = _addr(lg["topics"][2]), _addr(lg["topics"][3])
            tok = c0 if c0 in tokens else c1 if c1 in tokens else None
            if tok and tok not in found:
                found[tok] = {"pool_id": lg["topics"][1].lower(), "token0": c0, "token1": c1,
                              "quote": c1 if tok == c0 else c0}
    return found


def price_in_quote(sqrt_price_x96: int, token_is_0: bool) -> float:
    """Quote per token (both 18 decimals): token1/token0 = (sqrtP / 2^96)^2."""
    p = (sqrt_price_x96 / 2**96) ** 2
    return p if token_is_0 else (1 / p if p else float("nan"))


def cohort_swaps(rpc, chain: str, pools: dict[str, dict], start: int, end: int) -> list[dict]:
    """All V4 swaps of the cohort's pools in [start, end], with price per swap."""
    by_id = {p["pool_id"]: (tok, p) for tok, p in pools.items()}
    ids = sorted(by_id)
    rows = []
    for i in range(0, len(ids), 20):
        grp = ids[i : i + 20]
        for logs in rpc.get_logs(start, end, address=evm_swaps.V4_POOL_MANAGER[chain],
                                 topics=[evm_swaps.TOPIC_V4, grp], step=400_000):
            for lg in logs:
                r = evm_swaps.decode(lg, chain)
                if r is None:
                    continue
                tok, p = by_id[r["pool_id"]]
                is0 = tok == p["token0"]
                w = lg["data"][2:]
                sqrt_p = int(w[2 * 64 : 3 * 64], 16)
                d_tok = int(r["d0"] if is0 else r["d1"])
                d_q = int(r["d1"] if is0 else r["d0"])
                rows.append({"token": tok, "quote": p["quote"], "block_number": r["block_number"],
                             "tx_hash": r["tx_hash"], "log_index": r["log_index"],
                             "tok_delta": d_tok / 1e18, "quote_delta": d_q / 1e18,
                             "price_q": price_in_quote(sqrt_p, is0)})
    return rows
