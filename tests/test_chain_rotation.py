from datetime import date, timedelta

import numpy as np
import pandas as pd

from trench.indicators.chain_rotation import LOOKBACK, compute
from trench.indicators.common import confirm_states


def _vols(n_days=120, seed=0, late_chain_start=None):
    rng = np.random.default_rng(seed)
    d0 = date(2026, 1, 1)
    rows = []
    for c, base in [("solana", 100), ("base", 60), ("ethereum", 80), ("robinhood", 20)]:
        level = base * np.exp(np.cumsum(rng.normal(0, 0.05, n_days)))
        for i in range(n_days):
            if c == "robinhood" and late_chain_start is not None and i < late_chain_start:
                continue
            rows.append({"chain": c, "day": d0 + timedelta(i), "volume_usd": float(level[i])})
    return pd.DataFrame(rows)


def test_confirmation_is_symmetric_and_needs_two_readings():
    raw = ["a", "a", "b", "a", "b", "b", "a", "a"]
    assert confirm_states(raw) == ["a", "a", "a", "a", "a", "b", "b", "a"]


def test_no_look_ahead():
    """Values for day t are identical whether or not later days exist."""
    v = _vols()
    full = compute(v)
    cut = v["day"].min() + timedelta(days=80)
    part = compute(v[v["day"] <= cut])
    a = full[full["day"] <= cut].set_index(["chain", "day"]).sort_index()
    b = part.set_index(["chain", "day"]).sort_index()
    pd.testing.assert_frame_equal(a, b)


def test_new_chain_does_not_move_others_until_it_has_full_lookback():
    v = _vols(late_chain_start=50)
    out = compute(v)
    # Robinhood appears only once it has LOOKBACK days of data.
    first_rh = out[out["chain"] == "robinhood"]["day"].min()
    assert first_rh == v["day"].min() + timedelta(days=50 + LOOKBACK - 1)
    # Before that, other chains are computed among the 3 chains only.
    before = out[out["day"] < first_rh]
    assert set(before["n_chains"]) == {3}
    s = before.groupby("day")["share"].sum()
    assert np.allclose(s.values, 1.0)


def test_quadrant_values():
    out = compute(_vols())
    assert set(out["quadrant"].dropna()) <= {"leading", "weakening", "lagging", "improving"}
