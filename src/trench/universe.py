"""Rule-based, point-in-time token universe (SPEC §5.2).

Rule v1: a token enters the universe on the first day we observe it with market
cap >= $1M and liquidity >= $50K. Liquidity is the sum over the token's pairs
where it is the base token; market cap is that of its most liquid pair, falling
back to FDV. Quote assets (wrapped native, stablecoins, LSTs) never enter.

Entries are published to the point-in-time store and never removed, so dead coins
stay in history. Membership on a date uses only entries observed on or before it.

Coverage caveat: observations come from our own snapshots, which start on our
first run. Entries before that need trade-level history (Dune) and will be added
as a separately versioned backfill, not mixed into v1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from trench.chains import ACTIVE, QUOTE_ASSETS
from trench.lake import Lake
from trench.pit import PITStore, Reading
from trench.timeutil import utcnow

METRIC = "universe_entry"


@dataclass(frozen=True)
class UniverseRule:
    min_market_cap_usd: float = 1_000_000.0
    min_liquidity_usd: float = 50_000.0
    version: str = "1"


def _observations(lake: Lake, cutoff: datetime) -> list[tuple]:
    """(chain, token, observed_at, market_cap, liquidity, source) per token per fetch."""
    tables = set(lake.tables())
    con = lake.connect()
    parts = []
    if "dxs_pair_snapshot" in tables:
        parts.append(
            """SELECT chain, base_token AS token, fetched_at AS observed_at,
                      arg_max(coalesce(market_cap_usd, fdv_usd), liquidity_usd) AS mcap,
                      sum(liquidity_usd) AS liq, 'dexscreener' AS src
               FROM dxs_pair_snapshot WHERE fetched_at <= $cutoff GROUP BY ALL"""
        )
    if "gt_pool_snapshot" in tables:
        parts.append(
            """SELECT chain, base_token, fetched_at,
                      arg_max(coalesce(market_cap_usd, fdv_usd), reserve_usd),
                      max(reserve_usd), 'geckoterminal'
               FROM (SELECT DISTINCT ON (chain, pool_address, fetched_at) *
                     FROM gt_pool_snapshot WHERE fetched_at <= $cutoff)
               GROUP BY ALL"""
        )
    if not parts:
        return []
    return con.execute(" UNION ALL ".join(parts), {"cutoff": cutoff}).fetchall()


def build(lake: Lake, pit: PITStore, rule: UniverseRule | None = None,
          cutoff: datetime | None = None) -> int:
    """Publish entries for tokens that newly qualify using data fetched up to ``cutoff``."""
    rule = rule or UniverseRule()
    cutoff = cutoff or utcnow()
    first: dict[tuple[str, str], tuple] = {}
    for chain, tok, at, mcap, liq, src in _observations(lake, cutoff):
        if chain not in ACTIVE or not tok or tok in QUOTE_ASSETS.get(chain, set()):
            continue
        if (mcap or 0) >= rule.min_market_cap_usd and (liq or 0) >= rule.min_liquidity_usd:
            key = (chain, tok)
            if key not in first or at < first[key][0]:
                first[key] = (at, mcap, liq, src)

    already = {row[1] for row in _published(pit, rule)}  # row[1] = entity
    readings = [
        Reading(
            entity=f"{chain}:{tok}", as_of=at.date(), value=1.0, state="member",
            detail={"market_cap_usd": mcap, "liquidity_usd": liq, "source": src,
                    "observed_at": at.isoformat()},
        )
        for (chain, tok), (at, mcap, liq, src) in sorted(first.items())
        if f"{chain}:{tok}" not in already
    ]
    if not readings:
        return 0
    return pit.publish(METRIC, readings, formula_version=rule.version, input_cutoff=cutoff)


def _published(pit: PITStore, rule: UniverseRule, known_at: datetime | None = None):
    if METRIC not in pit.lake.tables():
        return []
    return pit.read(METRIC, known_at=known_at, formula_version=rule.version).fetchall()


def members(pit: PITStore, day: date, *, known_at: datetime | None = None,
            rule: UniverseRule | None = None) -> set[str]:
    """Universe on ``day``: every entry dated on or before it, on active chains.
    Nothing ever leaves; entries on a deactivated chain stay stored but are not read."""
    return {
        row[1]
        for row in _published(pit, rule or UniverseRule(), known_at)
        if row[2] <= day and row[1].split(":", 1)[0] in ACTIVE
    }


def entry_detail(row) -> dict:
    return json.loads(row[9]) if row[9] else {}
