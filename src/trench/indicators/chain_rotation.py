"""Chain Rotation Monitor (SPEC §6.2).

    S_c,t           = V_c,t / Σ_c V_c,t                 share of DEX volume
    RS-Ratio_c,t    = 100 × EMA_5(S_c,t) / mean(S_c, t−29…t)
    RS-Momentum_c,t = 100 × RS-Ratio_c,t / RS-Ratio_c,t−7
    Leading (>100, >100) · Weakening (>100, <100) · Lagging (<100, <100) · Improving (<100, >100)

Coverage changes (a chain whose history starts mid-window, such as Robinhood in
June 2026) are chain-linked: each day is computed only over the chains that have
data for the whole lookback window, so a new chain cannot make the others' shares
jump. The published state changes only after two consecutive readings agree.

Formula versions:
* ``0-raw``: V = DefiLlama total DEX volume (all pairs, unfiltered). For backtests
  and internal use only; never displayed, because CLAUDE.md requires organic inputs
  for anything user-facing.
* ``1`` (planned): V = our organic memecoin volume once it has 60+ days of history.

No look-ahead: the value for day t uses only volumes for days <= t, read as they
were known at the input cutoff.
"""

from __future__ import annotations

import pandas as pd

from trench.indicators.common import confirm_states

EMA_SPAN = 5
MEAN_WINDOW = 30
MOMENTUM_LAG = 7
LOOKBACK = MEAN_WINDOW + MOMENTUM_LAG  # days of complete history needed per chain


def quadrant(ratio: float, mom: float) -> str | None:
    if pd.isna(ratio) or pd.isna(mom):
        return None
    if ratio >= 100:
        return "leading" if mom >= 100 else "weakening"
    return "improving" if mom >= 100 else "lagging"


def _rs_on_window(win: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """``win``: days × chains volumes, complete. Returns RS-Ratio and RS-Momentum
    for the last day of the window."""
    share = win.div(win.sum(axis=1), axis=0)
    ema = share.ewm(span=EMA_SPAN, adjust=False).mean()
    mean30 = share.rolling(MEAN_WINDOW).mean()
    ratio = 100 * ema / mean30
    mom = 100 * ratio.iloc[-1] / ratio.iloc[-1 - MOMENTUM_LAG]
    return ratio.iloc[-1], mom


def compute(volumes: pd.DataFrame) -> pd.DataFrame:
    """``volumes``: columns chain, day, volume_usd. Returns one row per (chain, day)
    with share, rs_ratio, rs_momentum, quadrant (raw) and state (confirmed)."""
    wide = volumes.pivot_table(index="day", columns="chain", values="volume_usd")
    wide = wide.sort_index()
    wide = wide.where(wide > 0)
    out = []
    days = list(wide.index)
    for i in range(LOOKBACK - 1, len(days)):
        win = wide.iloc[i - LOOKBACK + 1 : i + 1]
        cols = [c for c in win.columns if win[c].notna().all()]
        if len(cols) < 2:
            continue
        win = win[cols]
        ratio, mom = _rs_on_window(win)
        share_t = win.iloc[-1] / win.iloc[-1].sum()
        for c in cols:
            out.append({"day": days[i], "chain": c, "share": float(share_t[c]),
                        "rs_ratio": float(ratio[c]), "rs_momentum": float(mom[c]),
                        "quadrant": quadrant(ratio[c], mom[c]), "n_chains": len(cols)})
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df = df.sort_values(["chain", "day"])
    df["state"] = df.groupby("chain")["quadrant"].transform(
        lambda s: pd.Series(confirm_states(list(s)), index=s.index))
    return df.reset_index(drop=True)


METRIC = "chain_rotation"


def publish(pit, rot: pd.DataFrame, *, formula_version: str, input_cutoff,
            drop_rule_failed: bool, backfill: bool) -> int:
    """Append readings to the point-in-time store. Values that already exist for
    this formula version are skipped (never overwritten)."""
    from trench.pit import Reading

    existing: set[tuple[str, object]] = set()
    if METRIC in pit.lake.tables():
        existing = {(r[1], r[2]) for r in
                    pit.read(METRIC, formula_version=formula_version).fetchall()}
    readings = [
        Reading(
            entity=f"chain={r.chain}", as_of=r.day, value=float(r.rs_ratio), state=r.state,
            detail={"share": r.share, "rs_ratio": r.rs_ratio, "rs_momentum": r.rs_momentum,
                    "quadrant_raw": r.quadrant, "n_chains": r.n_chains, "backfill": backfill,
                    "display": "description_only" if drop_rule_failed else "signal"},
        )
        for r in rot.itertuples()
        if (f"chain={r.chain}", r.day) not in existing
    ]
    if not readings:
        return 0
    return pit.publish(METRIC, readings, formula_version=formula_version,
                       input_cutoff=input_cutoff)
