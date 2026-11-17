import pandas as pd

from trench import organic

TOK, Q = "0x" + "11" * 20, "0x4200000000000000000000000000000000000006"


def _sw(i, who, delta, block, ts, tx=None, pool="p1"):
    t0, t1 = sorted([TOK, Q])
    is0 = TOK == t0
    d_tok, d_q = delta, -delta * 10**12
    return {"chain": "base", "pool_id": pool, "block_number": block, "log_index": i,
            "block_timestamp": ts, "tx_hash": tx or f"tx{i}", "token": TOK, "token0": t0,
            "token1": t1, "d0": str(d_tok if is0 else d_q), "d1": str(d_q if is0 else d_tok),
            "tx_from": who}


def _run(rows):
    df = organic.prepare(pd.DataFrame(rows), {})
    return organic.classify(df).set_index("log_index")["reason"].to_dict()


def test_plain_trades_are_organic():
    r = _run([_sw(1, "a", 5, 10, 1000), _sw(2, "b", -3, 20, 5000)])
    assert r == {1: None, 2: None}


def test_atomic_arb():
    r = _run([_sw(1, "a", 5, 10, 1000, tx="t"), _sw(2, "a", -5, 10, 1000, tx="t", pool="p2")])
    assert r == {1: "atomic_arb", 2: "atomic_arb"}


def test_sandwich_flags_attacker_not_victim():
    r = _run([_sw(1, "atk", 5, 10, 1000), _sw(2, "victim", 3, 10, 1000),
              _sw(3, "atk", -5, 10, 1000)])
    assert r == {1: "sandwich", 2: None, 3: "sandwich"}


def test_same_block_round_trip():
    r = _run([_sw(1, "a", 5, 10, 1000, pool="p1"), _sw(2, "a", -5, 10, 1000, pool="p2")])
    assert set(r.values()) == {"same_block_rt"}


def test_high_frequency():
    rows = [_sw(i, "hf", 1, 10 + i, 1000 + i * 5) for i in range(6)]  # 6 swaps in 25 s
    rows.append(_sw(9, "slow", 1, 100, 9000))
    r = _run(rows)
    assert all(r[i] == "high_frequency" for i in range(6)) and r[9] is None


def test_bot_mm():
    rows = [_sw(i, "mm", 1 if i % 2 else -1, 10 + i, 1000 + i * 600) for i in range(10)]
    assert set(_run(rows).values()) == {"bot_mm"}
