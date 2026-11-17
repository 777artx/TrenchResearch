"""Organic filter for EVM swaps (SPEC §5.5), formula version 1.

A swap is organic unless one of these rules flags it. The trader is the
transaction sender. Rules are applied in this order and the first match is the
recorded reason:

1. ``atomic_arb``      the same trader both buys and sells the token inside one
                       transaction (net position change within the tx).
2. ``sandwich``        in one pool and block, a trader has opposite-direction legs
                       before and after another trader's swap.
3. ``same_block_rt``   the same trader buys and sells the token in one block,
                       across separate transactions.
4. ``high_frequency``  the trader made more than 5 swaps within some 60-second
                       window that day (all of that trader's swaps that day).
5. ``bot_mm``          on a token and day, at least 10 swaps, each side at least 30%
                       of the count, and net tokens at most 10% of gross: two-sided
                       flow with near-zero inventory, the BOT/MM signature.

USD value comes from the quote side when the quote is the chain's native token,
wrapped native or a USD stablecoin; other quotes are left without a USD value and
are counted in coverage.
"""

from __future__ import annotations

import pandas as pd

VERSION = "1"
HF_MAX_PER_MINUTE = 5  # spec leaves N open; see docs/validation/organic_filter_v1.md
MM_MIN_SWAPS, MM_MIN_SIDE_SHARE, MM_MAX_NET_SHARE = 10, 0.30, 0.10

ETH_ZERO = "0x0000000000000000000000000000000000000000"
# (asset priced in USD, decimals) per quote token
QUOTES = {
    "robinhood": {ETH_ZERO: ("ETH", 18),
                  "0x0bd7d308f8e1639fab988df18a8011f41eacad73": ("ETH", 18),
                  "0x5fc5360d0400a0fd4f2af552add042d716f1d168": ("USD", 6)},
    "base": {ETH_ZERO: ("ETH", 18),
             "0x4200000000000000000000000000000000000006": ("ETH", 18),
             "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USD", 6)},
    "ethereum": {ETH_ZERO: ("ETH", 18),
                 "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": ("ETH", 18),
                 "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USD", 6),
                 "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USD", 6)},
}


def prepare(swaps: pd.DataFrame, eth_usd: dict) -> pd.DataFrame:
    """Add token delta, side, quote and USD value. ``eth_usd``: day -> price."""
    df = swaps.copy()
    is0 = df["token"] == df["token0"]
    d0 = df["d0"].map(int)
    d1 = df["d1"].map(int)
    df["tok_delta"] = [a if z else b for a, b, z in zip(d0, d1, is0, strict=True)]
    df["quote_delta"] = [b if z else a for a, b, z in zip(d0, d1, is0, strict=True)]
    df["quote_token"] = df["token1"].where(is0, df["token0"])
    df["side"] = ["buy" if x > 0 else "sell" if x < 0 else "none" for x in df["tok_delta"]]
    df["ts"] = pd.to_datetime(df["block_timestamp"], unit="s", utc=True)
    df["day"] = df["ts"].dt.date

    def usd(row) -> float | None:
        q = QUOTES.get(row.chain, {}).get(row.quote_token)
        if q is None:
            return None
        asset, dec = q
        amt = abs(row.quote_delta) / 10**dec
        if asset == "USD":
            return amt
        px = eth_usd.get(row.day)
        return amt * px if px else None

    df["usd"] = [usd(r) for r in df.itertuples()]
    return df


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``reason`` (None when organic) and ``organic``."""
    df = df.sort_values(["chain", "block_number", "log_index"]).reset_index(drop=True)
    reason = pd.Series([None] * len(df), index=df.index, dtype=object)
    sign = df["tok_delta"].map(lambda x: (x > 0) - (x < 0))

    def mark(mask, label):
        nonlocal reason
        reason = reason.where(reason.notna() | ~mask, label)

    # 1. atomic arbitrage
    k = ["chain", "tx_hash", "tx_from", "token"]
    both = df.assign(s=sign).groupby(k)["s"].transform(lambda s: (s > 0).any() & (s < 0).any())
    mark(both, "atomic_arb")

    # 2. sandwich: per pool and block, a trader with legs before and after another's
    sand = pd.Series(False, index=df.index)
    for _, g in df.groupby(["chain", "pool_id", "block_number"], sort=False):
        if len(g) < 3 or g["tx_from"].nunique() < 2:
            continue
        rows = list(g.itertuples())
        for i, a in enumerate(rows):
            for c in rows[i + 2 :]:
                if c.tx_from != a.tx_from or sign[a.Index] * sign[c.Index] >= 0:
                    continue
                if any(m.tx_from != a.tx_from for m in rows[i + 1 : rows.index(c)]):
                    sand[a.Index] = sand[c.Index] = True
    mark(sand, "sandwich")

    # 3. same-block round trip across transactions
    k = ["chain", "block_number", "tx_from", "token"]
    rt = df.assign(s=sign).groupby(k)["s"].transform(lambda s: (s > 0).any() & (s < 0).any())
    mark(rt, "same_block_rt")

    # 4. high frequency: > N swaps within any 60 s window, per trader and day
    hf_keys = set()
    for (ch, w, d), g in df.groupby(["chain", "tx_from", "day"]):
        if len(g) <= HF_MAX_PER_MINUTE:
            continue
        t = g["block_timestamp"].astype("int64").sort_values().to_numpy()  # unix seconds
        j = 0
        for i in range(len(t)):
            while t[i] - t[j] >= 60:
                j += 1
            if i - j + 1 > HF_MAX_PER_MINUTE:
                hf_keys.add((ch, w, d))
                break
    hf = pd.Series([(c, w, d) in hf_keys for c, w, d in
                    zip(df["chain"], df["tx_from"], df["day"], strict=True)], index=df.index)
    mark(hf, "high_frequency")

    # 5. BOT/MM: two-sided, near-zero net inventory
    g = df.assign(s=sign, a=df["tok_delta"].abs()).groupby(["chain", "tx_from", "token", "day"])
    n = g["s"].transform("size")
    buys = g["s"].transform(lambda s: (s > 0).sum())
    net = g["tok_delta"].transform("sum").abs()
    gross = g["a"].transform("sum")
    mm = ((n >= MM_MIN_SWAPS) & (buys / n >= MM_MIN_SIDE_SHARE)
          & ((n - buys) / n >= MM_MIN_SIDE_SHARE) & (net <= MM_MAX_NET_SHARE * gross))
    mark(mm, "bot_mm")

    df["reason"] = reason
    df["organic"] = reason.isna()
    return df
