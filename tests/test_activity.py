from datetime import date, timedelta

import numpy as np
import pandas as pd

from trench.indicators.activity import MIN_HISTORY, compute, trailing_pct_rank


def _inputs(n=500, seed=1):
    rng = np.random.default_rng(seed)
    d0 = date(2025, 1, 1)
    rows = []
    for c in ("solana", "base"):
        v = np.exp(np.cumsum(rng.normal(0, 0.1, n)) + 10)
        rows += [{"chain": c, "day": d0 + timedelta(i), "V": float(v[i])} for i in range(n)]
    return pd.DataFrame(rows)


def test_pct_rank_uses_only_the_past():
    x = pd.Series(np.arange(1, 400, dtype=float))  # strictly rising
    r = trailing_pct_rank(x)
    assert r.iloc[: MIN_HISTORY].isna().all()
    assert (r.dropna() == 100).all()  # every day above all previous days


def test_no_look_ahead():
    v = _inputs()
    full = compute(v)
    cut = date(2025, 1, 1) + timedelta(days=300)
    part = compute(v[v["day"] <= cut])
    a = full[full["day"] <= cut].set_index(["chain", "day"]).sort_index()
    b = part.set_index(["chain", "day"]).sort_index()
    pd.testing.assert_frame_equal(a, b)


def test_states_are_hot_or_cold_and_need_history():
    out = compute(_inputs())
    assert set(out["state"]) <= {"hot", "cold"}
    assert out["day"].min() >= date(2025, 1, 1) + timedelta(days=MIN_HISTORY)
