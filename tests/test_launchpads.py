import pandas as pd

from trench import launchpads as LP


def test_price_in_quote_orientation():
    sqrt = int(2**96 * 2)  # price token1/token0 = 4
    assert LP.price_in_quote(sqrt, True) == 4
    assert LP.price_in_quote(sqrt, False) == 0.25


def test_shrinkage_pulls_small_samples_to_prior():
    a, b = 1.0, 9.0  # prior mean 10%
    assert abs(LP.shrunk_rate(1, 1, a, b) - 2 / 11) < 1e-12   # 1 of 1 -> 18%, not 100%
    assert abs(LP.shrunk_rate(500, 1000, a, b) - 501 / 1010) < 1e-12


def test_score_launch_outcomes():
    L = pd.DataFrame([{"token": "t", "creator": "dev", "t0": 0}])
    rows = [{"token": "t", "ts": 60 * i, "trader": f"w{i}", "tok_delta": 10.0, "usd": 10.0,
             "mcap": 20_000 + 10_000 * i} for i in range(12)]           # 12 buyers in 12 min
    rows += [{"token": "t", "ts": 30, "trader": "dev", "tok_delta": 100.0, "usd": 1, "mcap": 1},
             {"token": "t", "ts": 90, "trader": "dev", "tok_delta": -80.0, "usd": 1, "mcap": 1},
             {"token": "t", "ts": 3 * 86400, "trader": "w1", "tok_delta": -1.0, "usd": 1.0,
              "mcap": 60_000}]
    r = LP.score_launches(L, pd.DataFrame(rows)).iloc[0]
    assert r.lstar and r.buyers_60m == 12
    assert r.grad and not r.runner and r.surv7 and r.rug
