"""Backtest of the Chain Rotation Monitor against its drop rule (SPEC §8).

Drop rule: drop signal framing if share changes show no persistence beyond one
week AND quadrants do not separate forward relative outcomes.

Tests, all on non-overlapping weekly samples (every 7th day):
1. Persistence beyond one week: rank correlation between a chain's share change
   over [t−7, t] and over [t+7, t+14] (skipping the first week ahead).
2. Separation: forward change in log share over [t, t+14] by confirmed state;
   Leading minus Lagging, with a date-block bootstrap interval.
3. Stability: median days per confirmed state (>= 5 required).

Forward *price* returns of each chain's memecoin basket are not used yet: our only
price history covers six months of tokens that are in today's universe, which
would bias the test toward survivors. The forward outcome used instead is the
chain's own share of DEX volume, which has no survivorship problem.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trench import harness


def run(rot: pd.DataFrame) -> dict:
    df = rot.sort_values(["chain", "day"]).copy()
    df["log_share"] = np.log(df["share"])
    g = df.groupby("chain")["log_share"]
    df["past7"] = df["log_share"] - g.shift(7)
    df["fut_7_14"] = g.shift(-14) - g.shift(-7)
    df["fut_0_14"] = g.shift(-14) - df["log_share"]
    days = sorted(df["day"].unique())
    weekly = set(days[::7])
    w = df[df["day"].isin(weekly)].dropna(subset=["past7", "fut_7_14", "fut_0_14"])

    pers = harness.block_bootstrap(
        w, lambda x: harness.spearman(x["past7"], x["fut_7_14"]), block=4)

    def lead_minus_lag(x: pd.DataFrame) -> float:
        a = x.loc[x["state"] == "leading", "fut_0_14"]
        b = x.loc[x["state"] == "lagging", "fut_0_14"]
        return float(a.mean() - b.mean()) if len(a) and len(b) else float("nan")

    sep = harness.block_bootstrap(w, lead_minus_lag, block=4)
    by_state = (w.groupby("state")["fut_0_14"].agg(["count", "mean", "median"])
                .round(4).to_dict("index"))
    stability = {c: harness.median_days_per_state(x.set_index("day")["state"])
                 for c, x in df.groupby("chain")}
    persistence_ok = pers[1] > 0
    separation_ok = sep[1] > 0
    return {
        "period": (str(min(days)), str(max(days))),
        "weekly_samples": int(len(w)),
        "persistence_rank_ic": pers,
        "lead_minus_lag_fwd14_logshare": sep,
        "fwd14_by_state": by_state,
        "median_days_per_state": stability,
        "persistence_ok": bool(persistence_ok),
        "separation_ok": bool(separation_ok),
        "stability_ok": bool(all(v >= 5 for v in stability.values())),
        "drop_signal_framing": bool(not persistence_ok and not separation_ok),
    }
