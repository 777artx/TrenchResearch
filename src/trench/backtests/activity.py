"""Backtest of Activity 0-raw (SPEC §8 drop rule for Trench Regime: extremes must
separate forward basket returns).

Forward outcome: 14-day log return of the chain's base asset (SOL or ETH). This is
a proxy for a memecoin basket that has no survivorship bias; a true basket needs
a point-in-time universe with dead coins, which our data does not cover yet.
Samples: every 7th day (non-overlapping 14-day horizons are approximated by weekly
sampling with a date-block bootstrap).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trench import harness


def run(act: pd.DataFrame, prices: pd.DataFrame) -> dict:
    """``prices``: asset, day, price_usd."""
    from trench.indicators.activity import BASE_ASSET

    px = prices.pivot_table(index="day", columns="asset", values="price_usd").sort_index()
    fwd = np.log(px.shift(-14) / px)
    df = act.copy()
    df["fwd14"] = [fwd.at[d, BASE_ASSET[c]] if d in fwd.index else np.nan
                   for c, d in zip(df["chain"], df["day"], strict=True)]
    days = sorted(df["day"].unique())
    w = df[df["day"].isin(set(days[::7]))].dropna(subset=["fwd14", "activity"])

    def top_minus_bottom(x: pd.DataFrame) -> float:
        hi = x.loc[x["activity"] >= 80, "fwd14"]
        lo = x.loc[x["activity"] <= 20, "fwd14"]
        return float(hi.mean() - lo.mean()) if len(hi) and len(lo) else float("nan")

    def hot_minus_cold(x: pd.DataFrame) -> float:
        a, b = x.loc[x["state"] == "hot", "fwd14"], x.loc[x["state"] == "cold", "fwd14"]
        return float(a.mean() - b.mean()) if len(a) and len(b) else float("nan")

    ext = harness.block_bootstrap(w, top_minus_bottom, block=4)
    hc = harness.block_bootstrap(w, hot_minus_cold, block=4)
    ic = harness.block_bootstrap(w, lambda x: harness.spearman(x["activity"], x["fwd14"]),
                                 block=4)
    stab = {c: harness.median_days_per_state(g.set_index("day")["state"])
            for c, g in df.groupby("chain")}
    sig = lambda t: not (t[1] <= 0 <= t[2])  # noqa: E731
    return {
        "period": (str(min(days)), str(max(days))), "weekly_samples": int(len(w)),
        "extremes_top20_minus_bottom20_fwd14": ext, "hot_minus_cold_fwd14": hc,
        "rank_ic_activity_fwd14": ic, "median_days_per_state": stab,
        "extremes_separate": bool(sig(ext)), "states_separate": bool(sig(hc)),
        "stability_ok": bool(all(v >= 5 for v in stab.values())),
        "drop_signal_framing": bool(not sig(ext) and not sig(hc)),
    }
