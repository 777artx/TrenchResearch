"""Compute every v0 indicator, publish to the point-in-time store, write the status list."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from trench.indicators import batch_v0 as B
from trench.lake import Lake
from trench.pit import PITStore
from trench.timeutil import utcnow

log = logging.getLogger(__name__)


RESTATEMENT: str | None = None  # set by run() when correcting an earlier publish


def _pub(pit: PITStore, metric: str, readings) -> int:
    """Publish new readings. A reading that already exists for the same day is only
    re-published as an explicit restatement (with its reason) when its value changed."""
    if not readings:
        return 0
    existing = {}
    if metric in pit.lake.tables():
        existing = {(r[1], r[2]): r[3] for r in pit.read(metric, formula_version="0").fetchall()}
    new = [r for r in readings if (r.entity, r.as_of) not in existing]
    changed = [r for r in readings if (r.entity, r.as_of) in existing
               and existing[(r.entity, r.as_of)] != r.value]
    n = pit.publish(metric, new, formula_version="0", input_cutoff=utcnow()) if new else 0
    if changed and RESTATEMENT:
        n += pit.publish(metric, changed, formula_version="0", input_cutoff=utcnow(),
                         restatement_reason=RESTATEMENT)
    return n


def run(lake: Lake, pit: PITStore, out: Path, restatement: str | None = None) -> list[tuple]:
    global RESTATEMENT
    RESTATEMENT = restatement
    rows: list[tuple] = []  # (group, name, status, reading)

    def step(group, name, metric, fn, status="Computing, not validated"):
        try:
            readings, summary = fn()
            _pub(pit, metric, readings)
            rows.append((group, name, status if readings else "Pending data", summary))
            return readings
        except Exception as exc:
            traceback.print_exc()
            rows.append((group, name, "Error", f"{type(exc).__name__}: {str(exc)[:120]}"))
            return []

    # Existing published indicators
    def latest(metric, fmt):
        if metric not in pit.lake.tables():
            return [], "not computed"
        df = pit.read(metric).df()
        last = df[df.as_of == df.as_of.max()]
        return [], fmt(last)

    rows.append(("Market", "Trench Regime: Activity", "Description only (failed backtest)",
                 latest("trench_activity", lambda d: ", ".join(
                     f"{r.entity.split('=')[1]} {r.value:.0f} {r.state}" for r in d.itertuples())
                 )[1]))
    step("Market", "Trench Regime: Sentiment (mSOPR)", "sentiment_msopr",
         lambda: B.sentiment_msopr(lake))
    rows.append(("Market", "Regime state (Activity × Sentiment)", "Pending data",
                 "Sentiment has no 365-day percentile history yet; first state needs ~180 days "
                 "of organic mSOPR"))
    rows.append(("Market", "Chain Rotation", "Description only (failed backtest)",
                 latest("chain_rotation", lambda d: ", ".join(
                     f"{r.entity.split('=')[1]} {r.state}" for r in d.itertuples()))[1]))
    rows.append(("Market", "Launchpad Scorecard", "Computing, not validated",
                 "see launchpad cohort reports; Long.xyz and PonsFamily, cohort 2026-11-11"))
    step("Flow", "Retail Flow Desk (market)", "retail_flow_market",
         lambda: B.retail_flow_market(lake))
    step("Flow", "Retail Flow Desk (token flags)", "retail_flow_tokens",
         lambda: B.retail_flow_tokens(lake))
    cohort = step("Flow", "Cohort Flow", "cohort_flow", lambda: B.cohort_flow_solana(lake))
    rows.append(("Flow", "Attention vs Flow", "Pending data",
                 "needs a social feed; GMGN callouts are not yet collected daily"))
    cbm = step("Coin", "Cost-basis map", "cost_basis_map", lambda: B.cost_basis_map(lake))
    step("Coin", "Quality × Flow setup", "quality_flow",
         lambda: B.quality_flow(lake, cohort, cbm))

    def bottoms():
        readings, deep, n = B.drawdowns(lake, pit)
        return readings, (f"{deep} of {n} universe coins with price history are at least 50% "
                          "below their 90-day high (eligible); the probability model needs "
                          "labelled drawdown history and is not trained")
    step("Coin", "Bottom Probability (eligibility)", "bottom_eligible", bottoms)
    rows.append(("Trust", "Public track record", "Pending data",
                 "storage and logging ready; no indicator has signal status, so no live "
                 "signals are logged yet"))
    step("Trust", "Organic ratio", "organic_ratio", lambda: B.organic_ratio(lake))

    step("Extra", "Meme perp positioning", "meme_perps", B.meme_perps)
    step("Extra", "Net capital inflow by chain", "capital_inflow", B.capital_inflow)

    def lp():
        serial, pnl, summary = B.launchpad_extras(lake)
        _pub(pit, "trench_pnl", pnl)
        return serial, summary
    step("Extra", "Serial-deployer concentration + Trench PnL", "serial_deployer", lp)
    step("Extra", "Urgency index (Solana)", "urgency", lambda: B.urgency_solana(lake))
    step("Extra", "Smart-flow breadth", "smart_flow_breadth",
         lambda: ([], "included in Cohort Flow line above"))

    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Indicator status ({utcnow():%Y-%m-%d %H:%M} UTC)", "",
             "Every reading is research, not financial advice. \"Not validated\" means the "
             "indicator has no backtest yet; nothing here has signal status.", "",
             "| Group | Indicator | Status | Current reading |", "|---|---|---|---|"]
    lines += [f"| {g} | {n} | {s} | {r} |" for g, n, s, r in rows]
    out.write_text("\n".join(lines) + "\n")
    return rows
