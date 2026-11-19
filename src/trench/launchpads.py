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


# ---- PonsFamily: one bonding-curve contract per token ------------------------------
PONS = Pad("ponsfamily.com", "robinhood", "0xe33e9e479df8802cb0866d5d05258bec4cf62948",
           "0xdcacba5e347ae7abd91cb519eb877af8fa7774e347b85dd3ddcd24a2ba8cdf37")
PONS_BUY = "0xec36bf571f136799e8dc0b0b8bea4b04d8bd3d43de838aab0d5fc21d4cbfc455"
PONS_SELL = "0x8113d738abdcb6b38357e9d53a54a7157861a09031b453651f0fe7fe151f59df"


def pons_launches(rpc, start: int, end: int) -> list[dict]:
    out = []
    for logs in rpc.get_logs(start, end, address=PONS.factory, topics=[PONS.launch_topic],
                             step=900_000):
        for lg in logs:
            out.append({"pad": PONS.name, "chain": PONS.chain, "token": _addr(lg["topics"][1]),
                        "curve": _addr(lg["topics"][2]), "creator": _addr(lg["topics"][3]),
                        "block_number": int(lg["blockNumber"], 16),
                        "tx_hash": lg["transactionHash"].lower()})
    return out


def pons_trades(rpc, launches: list[dict], start: int, end: int) -> list[dict]:
    """Curve trades. Buy: topics (router, buyer), data (eth_in, tokens_out, fee, fee).
    Sell: topics (seller, recipient), data (tokens_in, eth_out, fee, fee)."""
    by_curve = {x["curve"]: x["token"] for x in launches}
    curves = sorted(by_curve)
    rows = []
    for i in range(0, len(curves), 50):
        for logs in rpc.get_logs(start, end, address=curves[i : i + 50],
                                 topics=[[PONS_BUY, PONS_SELL]], step=400_000):
            for lg in logs:
                w = lg["data"][2:]
                a, b = int(w[0:64], 16) / 1e18, int(w[64:128], 16) / 1e18
                buy = lg["topics"][0] == PONS_BUY
                rows.append({"token": by_curve[lg["address"].lower()],
                             "block_number": int(lg["blockNumber"], 16),
                             "tx_hash": lg["transactionHash"].lower(),
                             "trader": _addr(lg["topics"][2] if buy else lg["topics"][1]),
                             "tok_delta": b if buy else -a, "eth": a if buy else b})
    return rows


# ---- shared scoring (SPEC §6.3) ----------------------------------------------------
MIN_BUYERS = 10          # L*: unique non-creator buyers in the first 60 minutes
GRAD_USD, SURV_USD, RUNNER_USD = 100_000, 50_000, 1_000_000


def score_launches(launches, trades):
    """``launches``: token, creator, t0 (unix s). ``trades``: token, ts, trader, tok_delta,
    usd, mcap. Returns one row per launch with the SPEC §6.3 outcomes."""
    import pandas as pd

    tr = trades.merge(launches[["token", "t0", "creator"]], on="token")
    tr["age_min"] = (tr["ts"] - tr["t0"]) / 60
    tr = tr.sort_values("ts")
    rows = []
    for lr in launches.itertuples():
        g = tr[tr["token"] == lr.token]
        f = g[g["age_min"] <= 60]
        buyers = set(f.loc[(f.tok_delta > 0) & (f.trader != lr.creator), "trader"].dropna())
        cb = f.loc[(f.trader == lr.creator) & (f.tok_delta > 0), "tok_delta"].sum()
        cs = -f.loc[(f.trader == lr.creator) & (f.tok_delta < 0), "tok_delta"].sum()
        d24, d7 = g[g.age_min <= 1440], g[g.age_min <= 7 * 1440]
        vw = f.usd.sum() / f.tok_delta.abs().sum() if f.tok_delta.abs().sum() else float("nan")
        last24 = d24.iloc[-1] if len(d24) else None
        p24 = float("nan")
        if last24 is not None and last24.tok_delta:
            p24 = last24.usd / abs(last24.tok_delta)
        at7 = d7.mcap.iloc[-1] if len(d7) else float("nan")
        rows.append({
            "token": lr.token, "buyers_60m": len(buyers), "lstar": len(buyers) >= MIN_BUYERS,
            "grad": bool(len(d24) and d24.mcap.max() >= GRAD_USD),
            "surv7": bool(at7 >= SURV_USD), "runner": bool(len(d7) and d7.mcap.max() >= RUNNER_USD),
            "rug": bool(cb > 0 and cs >= 0.5 * cb),
            "buyret": p24 / vw - 1 if vw == vw and vw else float("nan"),
            "peak_mcap_7d": float(d7.mcap.max()) if len(d7) else float("nan"),
            "vol_usd_7d": float(d7.usd.sum()), "n_trades_7d": int(len(d7)),
        })
    return pd.DataFrame(rows)


def shrunk_rate(k: float, n: float, alpha: float, beta: float) -> float:
    """Beta-binomial posterior mean: (k + α) / (n + α + β)."""
    return (k + alpha) / (n + alpha + beta)


def fit_beta_prior(ks, ns) -> tuple[float, float]:
    """Method-of-moments Beta prior on pooled pad rates (weak if few pads)."""
    import numpy as np

    rates = np.array([k / n for k, n in zip(ks, ns, strict=True) if n > 0])
    if len(rates) < 2:
        m = float(rates.mean()) if len(rates) else 0.1
        return m * 2, (1 - m) * 2  # prior worth 2 launches
    m, v = rates.mean(), rates.var(ddof=1)
    v = max(v, 1e-6)
    common = m * (1 - m) / v - 1
    common = min(max(common, 2.0), 200.0)
    return float(m * common), float((1 - m) * common)
