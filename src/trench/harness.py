"""Shared validation harness (SPEC §8): statistics used by every indicator backtest.

Small, explicit functions rather than a framework: rank correlation, a date-block
bootstrap for confidence intervals (dates are resampled in blocks, so serial
correlation and the common shock across chains or tokens on a date are respected),
group separation of forward outcomes by state, and state stability.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def spearman(x: pd.Series, y: pd.Series) -> float:
    m = x.notna() & y.notna()
    if m.sum() < 3:
        return float("nan")
    return float(x[m].rank().corr(y[m].rank()))


def block_bootstrap(df: pd.DataFrame, stat, *, date_col: str = "day", block: int = 4,
                    n: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Point estimate and 95% interval of ``stat(df)``, resampling blocks of
    consecutive dates (``block`` dates per block) with replacement."""
    rng = np.random.default_rng(seed)
    dates = np.array(sorted(df[date_col].unique()))
    by_date = {d: g for d, g in df.groupby(date_col)}
    point = stat(df)
    if len(dates) < 2 * block:
        return point, float("nan"), float("nan")
    starts = np.arange(0, len(dates) - block + 1)
    k = int(np.ceil(len(dates) / block))
    vals = []
    for _ in range(n):
        picks = rng.choice(starts, size=k)
        ds = np.concatenate([dates[s : s + block] for s in picks])[: len(dates)]
        sample = pd.concat([by_date[d] for d in ds], ignore_index=True)
        v = stat(sample)
        if not np.isnan(v):
            vals.append(v)
    lo, hi = np.percentile(vals, [2.5, 97.5]) if vals else (np.nan, np.nan)
    return float(point), float(lo), float(hi)


def median_days_per_state(states: pd.Series) -> float:
    """Median length of runs of an unchanged state (SPEC §8 requires >= 5)."""
    s = states.dropna()
    if s.empty:
        return float("nan")
    runs = (s != s.shift()).cumsum()
    return float(s.groupby(runs).size().median())
