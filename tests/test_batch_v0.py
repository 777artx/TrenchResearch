import pandas as pd

from trench.indicators import batch_v0 as B


def test_fifo_uses_only_earlier_buys():
    df = pd.DataFrame([
        {"token": "t", "tx_from": "w", "block_timestamp": 1, "tok_delta": 10, "amt": 10.0,
         "px": 1.0, "organic": True},
        {"token": "t", "tx_from": "w", "block_timestamp": 2, "tok_delta": -15, "amt": 15.0,
         "px": 2.0, "organic": True},   # 5 tokens have no known basis
        {"token": "t", "tx_from": "w", "block_timestamp": 3, "tok_delta": 10, "amt": 10.0,
         "px": 9.0, "organic": True},   # a later buy must not be matched to the earlier sell
    ])
    s = B.fifo_cost_basis(df).iloc[0]
    assert s.cost == 10.0 and s.value == 20.0 and abs(s.known_share - 10 / 15) < 1e-12


def test_segments():
    assert B._segment("fresh_wallet,axiom") == "PRO"
    assert B._segment("fomo") == "CONSUMER"
    assert B._segment("trojan") == "TG-BOT"
    assert B._segment(None) is None
