"""Daily Launchpad Scorecard cohorts (SPEC §6.3), formula v0.

For cohort day D (launches between D 00:00 and D+1 00:00 UTC), each launch is
followed until D+8 00:00 so every launch has a full 7 days. Run on day D+8 or later.

Pads: Long.xyz (Uniswap V4 pools paired with tokenized stocks) and PonsFamily
(one bonding curve per token, priced in ETH). After a PonsFamily token leaves its
curve, its outcomes come from GeckoTerminal daily candles of its DEX pool.

Outputs: ``lp_launch_outcomes`` (one row per launch, lake) and the point-in-time
metric ``launchpad_scorecard`` (one reading per pad and cohort day).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd

from trench import launchpads as LP
from trench.ingest.evm_swaps import ANCHOR_STEP, BLOCK_BATCH, _interpolate
from trench.lake import Lake
from trench.pit import PITStore, Reading
from trench.sources.evm_rpc import RPC_URLS, EvmRPC
from trench.timeutil import utcnow

log = logging.getLogger(__name__)
METRIC = "launchpad_scorecard"
FORMULA = "0"
PONS_GRAD = "0x2cc664e1"  # rare curve event, observed only on tokens that left the curve


def block_ts(rpc: EvmRPC, b: int) -> int:
    return int(rpc.call("eth_getBlockByNumber", [hex(b), False])["timestamp"], 16)


def block_at(rpc: EvmRPC, ts: int) -> int:
    """First block with timestamp >= ts (binary search)."""
    lo, hi = 1, rpc.head()
    while lo < hi:
        mid = (lo + hi) // 2
        if block_ts(rpc, mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _times(rpc: EvmRPC, blocks: list[int]) -> dict[int, int]:
    anch = sorted({b - b % ANCHOR_STEP for b in blocks} |
                  {b - b % ANCHOR_STEP + ANCHOR_STEP for b in blocks})
    head = rpc.head()
    anch = [a for a in anch if a <= head] + ([head] if anch and anch[-1] > head else [])
    t: dict[int, int] = {}
    for i in range(0, len(anch), BLOCK_BATCH):
        chunk = anch[i : i + BLOCK_BATCH]
        res = rpc.batch("eth_getBlockByNumber", [[hex(b), False] for b in chunk])
        t.update({b: int(r["timestamp"], 16) for b, r in zip(chunk, res, strict=True) if r})
    return _interpolate(blocks, t)


def _dxs_prices(addrs: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for i in range(0, len(addrs), 30):
        r = httpx.get("https://api.dexscreener.com/tokens/v1/robinhood/" + ",".join(addrs[i:i+30]),
                      timeout=60).json()
        for p in sorted(r or [], key=lambda p: (p.get("liquidity") or {}).get("usd") or 0):
            a = p["baseToken"]["address"].lower()
            if a in addrs and p.get("priceUsd"):
                out[a] = float(p["priceUsd"])
    return out


def long_cohort(rpc, s, e, horizon):
    L = pd.DataFrame(LP.launches(rpc, LP.LONG, s, e))
    if L.empty:
        return L, pd.DataFrame()
    pools = LP.pools_for(rpc, "robinhood", set(L.token), s, e + 5_000)
    sw = pd.DataFrame(LP.cohort_swaps(rpc, "robinhood", pools, s, horizon))
    bt = _times(rpc, sorted(set(L.block_number) | set(sw.get("block_number", []))))
    L["t0"] = L.block_number.map(bt)
    if sw.empty:
        return L, sw
    sw["ts"] = sw.block_number.map(bt)
    first = sw.merge(L[["token", "t0"]], on="token")
    hs = sorted(first.loc[first.ts - first.t0 <= 3600, "tx_hash"].unique())
    frm = {}
    for i in range(0, len(hs), 100):
        res = rpc.batch("eth_getTransactionByHash", [[h] for h in hs[i : i + 100]])
        frm.update({h: (x or {}).get("from", "").lower() for h, x in zip(hs[i:i+100], res,
                                                                       strict=True)})
    sw["trader"] = sw.tx_hash.map(frm)
    q = _dxs_prices(sorted(sw.quote.unique()))
    sw["usd"] = sw.quote_delta.abs() * sw.quote.map(q)
    sw["mcap"] = sw.price_q * sw.quote.map(q) * 1e9
    return L, sw[["token", "ts", "trader", "tok_delta", "usd", "mcap"]]


def pons_cohort(rpc, s, e, horizon, eth_usd: dict, day0: date):
    L = pd.DataFrame(LP.pons_launches(rpc, s, e))
    if L.empty:
        return L, pd.DataFrame()
    tr = pd.DataFrame(LP.pons_trades(rpc, L.to_dict("records"), s, horizon))
    supplies = []
    toks = L.token.tolist()
    for i in range(0, len(toks), BLOCK_BATCH):  # the RPC rejects large batches
        supplies += rpc.batch("eth_call", [[{"to": t, "data": "0x18160ddd"}, "latest"]
                                           for t in toks[i : i + BLOCK_BATCH]])
    L["supply"] = [int(x, 16) / 1e18 if x else 1e9 for x in supplies]
    bt = _times(rpc, sorted(set(L.block_number) | set(tr.get("block_number", []))))
    L["t0"] = L.block_number.map(bt)
    if tr.empty:
        return L, tr
    tr["ts"] = tr.block_number.map(bt)
    px = tr.ts.map(lambda t: eth_usd.get(datetime.fromtimestamp(t, UTC).date(),
                                         eth_usd[max(eth_usd)]))
    tr["usd"] = tr.eth * px
    tr = tr.merge(L[["token", "supply"]], on="token")
    tr["mcap"] = tr.usd / tr.tok_delta.abs() * tr.supply
    # Tokens that left the curve: add daily candles from their DEX pool.
    grads = set()
    curves = L.curve.tolist()
    for i in range(0, len(curves), 50):
        for logs in rpc.get_logs(s, horizon, address=curves[i:i+50], step=400_000):
            grads |= {lg["address"].lower() for lg in logs if lg["topics"][0].startswith(PONS_GRAD)}
    extra = []
    for tok in L.loc[L.curve.isin(grads), "token"]:
        extra += _gt_candles(tok, L.loc[L.token == tok, "supply"].iat[0], day0)
    out = tr[["token", "ts", "trader", "tok_delta", "usd", "mcap"]]
    L["left_curve"] = L.curve.isin(grads)
    return L, pd.concat([out, pd.DataFrame(extra)], ignore_index=True) if extra else out


def _gt_candles(token: str, supply: float, day0: date) -> list[dict]:
    """Daily candles as synthetic observations (high and close per day)."""
    h = {"Accept": "application/json"}
    base = "https://api.geckoterminal.com/api/v2/networks/robinhood"
    import time

    try:
        time.sleep(4)  # GeckoTerminal free tier: stay well under its rate limit
        pools = httpx.get(f"{base}/tokens/{token}/pools", headers=h, timeout=60).json()["data"]
        pool = pools[0]["attributes"]["address"]
        time.sleep(4)
        c = httpx.get(f"{base}/pools/{pool}/ohlcv/day", headers=h, timeout=60,
                      params={"limit": 12, "token": token, "currency": "usd"}).json()
        candles = c["data"]["attributes"]["ohlcv_list"]
    except Exception:
        log.warning("post-curve prices unavailable for %s", token)
        return []
    rows = []
    for ts, _o, hi, _l, cl, _v in candles:
        d = datetime.fromtimestamp(ts, UTC).date()
        if day0 <= d <= day0 + timedelta(days=8):
            for t, p in ((ts + 43_200, hi), (ts + 86_399, cl)):
                rows.append({"token": token, "ts": t, "trader": None, "tok_delta": 0.0,
                             "usd": 0.0, "mcap": float(p) * supply})
    return rows


def pad_summary(outcomes: pd.DataFrame) -> dict:
    ls = outcomes[outcomes.lstar]
    return {"launches": int(len(outcomes)), "lstar": int(len(ls)),
            "spam_share": float(1 - len(ls) / len(outcomes)) if len(outcomes) else None,
            "creators": int(outcomes.creator.nunique()),
            **{k: int(ls[k].sum()) for k in ("grad", "surv7", "runner", "rug")},
            "buyret_median": float(ls.buyret.median()) if len(ls) else None}


def run_day(lake: Lake, pit: PITStore, day: date, pads: tuple[str, ...] = ("long", "pons")
            ) -> dict:
    if day + timedelta(days=8) > utcnow().date():
        raise ValueError(f"cohort {day} needs 7 full days after launch day")
    rpc = EvmRPC(RPC_URLS["robinhood"], per_minute=900)
    ts0 = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
    s, e1 = block_at(rpc, ts0), block_at(rpc, ts0 + 86_400)
    horizon = block_at(rpc, ts0 + 8 * 86_400)
    eth = dict(lake.connect().execute(
        "SELECT day, price_usd FROM llama_price_daily WHERE asset = 'ETH'").fetchall())
    res = {}
    run_id = f"lp_{day:%Y%m%d}_{utcnow():%Y%m%dT%H%M%S}"
    jobs = {"long": (LP.LONG.name, lambda: long_cohort(rpc, s, e1 - 1, horizon)),
            "pons": (LP.PONS.name, lambda: pons_cohort(rpc, s, e1 - 1, horizon, eth, day))}
    for key in pads:
        pad, fn = jobs[key]
        try:
            L, tr = fn()
        except Exception as exc:  # one pad failing must not lose the others
            log.exception("cohort %s %s failed", pad, day)
            res[pad] = {"error": str(exc)[:200]}
            continue
        if L.empty:
            continue
        sc = LP.score_launches(L, tr) if len(tr) else pd.DataFrame({"token": L.token})
        out = L.merge(sc, on="token", how="left")
        for c in ("lstar", "grad", "surv7", "runner", "rug"):
            out[c] = out[c].fillna(False).astype(bool)
        out["pad"], out["cohort_day"] = pad, day
        keep = [c for c in out.columns if c not in ("tx_hash",)]
        lake.write("lp_launch_outcomes", out[keep].to_dict("records"),
                   run_id=f"{run_id}_{pad.split('.')[0]}", fetched_at=utcnow())
        res[pad] = pad_summary(out)
    return res


def publish(lake: Lake, pit: PITStore, day: date) -> int:
    """Shrunk rates and LQS for every pad for ``day``, using only cohorts up to ``day``."""
    con = lake.connect()
    df = con.execute("SELECT * FROM lp_launch_outcomes WHERE cohort_day <= ? "
                     "QUALIFY row_number() OVER (PARTITION BY pad, token "
                     "ORDER BY fetched_at DESC) = 1", [day]).df()
    pooled = df.groupby("pad").agg(n=("lstar", "sum"), grad=("grad", "sum"),
                                   surv7=("surv7", "sum"), runner=("runner", "sum"),
                                   rug=("rug", "sum"))
    today = df[df.cohort_day == pd.Timestamp(day).date()] if len(df) else df
    if today.empty:
        return 0
    rows = {}
    for pad, g in today.groupby("pad"):
        ls = g[g.lstar]
        rec = {"launches": int(len(g)), "lstar": int(len(ls))}
        for k in ("grad", "surv7", "runner", "rug"):
            a, b = LP.fit_beta_prior(pooled[k].tolist(), pooled["n"].tolist())
            rec[k] = LP.shrunk_rate(int(ls[k].sum()), len(ls), a, b)
        rec["buyret"] = float(ls.buyret.median()) if len(ls) else float("nan")
        rows[pad] = rec
    t = pd.DataFrame(rows).T
    t["one_minus_rug"] = 1 - t["rug"]
    comps = ["grad", "surv7", "runner", "one_minus_rug", "buyret"]
    t["lqs"] = t[comps].rank(pct=True).mean(axis=1) * 100
    readings = [Reading(entity=f"pad={p}", as_of=day, value=float(r.lqs), state=None,
                        detail={k: (None if pd.isna(v) else float(v)) for k, v in r.items()}
                        | {"n_pads": len(t), "validated": False})
                for p, r in t.iterrows()]
    return pit.publish(METRIC, readings, formula_version=FORMULA, input_cutoff=utcnow())
