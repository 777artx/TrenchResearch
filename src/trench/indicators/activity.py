"""Trench Regime: Activity reading (SPEC §6.1), formula 0-raw.

    s_i,t      = PctRank(log X_i,t ; trailing 365 days before t) × 100
    Activity_t = mean of available s_i,t                  (equal weights)
    Trend_t    = Activity_t − Activity_t−7
    State      = hot if Activity >= 50 else cold, confirmed by two consecutive readings

Inputs in 0-raw (what has history today):
* V: DefiLlama total DEX volume divided by the chain's base-asset price (SOL for
  Solana, ETH for Base, Ethereum and Robinhood), so a base-asset rally does not
  read as more activity.
* P: TEHscreener daily active wallets (from 2026-04-01; Solana, Base, Robinhood).
  Not organic: includes bots.
Q (graduation × survival) and R (graduates above graduation price) have no history
yet and are absent.

No look-ahead: today's value is ranked only against the trailing window before
today. A component is used only once it has 180 days of trailing history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trench.indicators.common import confirm_states

WINDOW = 365
MIN_HISTORY = 180
BASE_ASSET = {"solana": "SOL", "base": "ETH", "ethereum": "ETH", "robinhood": "ETH"}


def trailing_pct_rank(x: pd.Series, window: int = WINDOW, min_hist: int = MIN_HISTORY):
    """Percent of the previous ``window`` values strictly below today's (ties half)."""
    v = np.log(x.where(x > 0)).to_numpy()
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        if np.isnan(v[i]):
            continue
        past = v[max(0, i - window) : i]
        past = past[~np.isnan(past)]
        if len(past) < min_hist:
            continue
        out[i] = 100 * ((past < v[i]).sum() + 0.5 * (past == v[i]).sum()) / len(past)
    return pd.Series(out, index=x.index)


def compute(inputs: pd.DataFrame) -> pd.DataFrame:
    """``inputs``: chain, day, and one column per component (V, P, ...)."""
    comps = [c for c in inputs.columns if c not in ("chain", "day")]
    out = []
    for chain, g in inputs.groupby("chain"):
        g = g.set_index("day").sort_index()
        g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="D").date)
        s = pd.DataFrame({f"s_{c}": trailing_pct_rank(g[c]) for c in comps}, index=g.index)
        act = s.mean(axis=1, skipna=True)
        df = s.assign(chain=chain, activity=act, n_components=s.notna().sum(axis=1))
        df["trend"] = df["activity"] - df["activity"].shift(7)
        raw = [None if pd.isna(a) else ("hot" if a >= 50 else "cold") for a in df["activity"]]
        df["state"] = confirm_states(raw)
        out.append(df.reset_index(names="day"))
    res = pd.concat(out, ignore_index=True)
    return res[res["activity"].notna()].reset_index(drop=True)


METRIC = "trench_activity"


def publish(pit, act: pd.DataFrame, *, formula_version: str, input_cutoff,
            drop_rule_failed: bool, backfill: bool) -> int:
    from trench.pit import Reading

    existing: set = set()
    if METRIC in pit.lake.tables():
        existing = {(r[1], r[2]) for r in
                    pit.read(METRIC, formula_version=formula_version).fetchall()}
    comps = [c for c in act.columns if c.startswith("s_")]
    readings = [
        Reading(entity=f"chain={r['chain']}", as_of=r["day"], value=float(r["activity"]),
                state=r["state"],
                detail={**{c: (None if pd.isna(r[c]) else float(r[c])) for c in comps},
                        "trend": None if pd.isna(r["trend"]) else float(r["trend"]),
                        "n_components": int(r["n_components"]), "backfill": backfill,
                        "display": "description_only" if drop_rule_failed else "signal"})
        for r in act.to_dict("records") if (f"chain={r['chain']}", r["day"]) not in existing
    ]
    return pit.publish(METRIC, readings, formula_version=formula_version,
                       input_cutoff=input_cutoff) if readings else 0
