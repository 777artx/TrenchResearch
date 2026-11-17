"""Prices, liquidity and pools from GeckoTerminal and DexScreener.

One run does four things:

1. **Discover** candidate tokens: GeckoTerminal top, new and trending pools on
   every covered chain, plus the latest TEHscreener top-token lists.
2. **Register** tokens we have not seen before in ``token_registry``. The registry
   only grows: dead coins stay, so the universe keeps them (SPEC §5.2).
3. **Snapshot** every registered token on DexScreener (``dxs_pair_snapshot``).
   Neither source publishes liquidity or market-cap history, so these snapshots
   are our point-in-time record of both from the first run onward.
4. **Backfill daily OHLCV** from GeckoTerminal for each token's most liquid pool
   (``gt_pool_ohlcv_day``), within a request budget, newest-uncovered first.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from trench import chains
from trench.http import HttpClient, NotFound, UpstreamError
from trench.lake import Lake
from trench.rawstore import RawStore
from trench.sources import dexscreener as dxs
from trench.sources import geckoterminal as gt
from trench.timeutil import utcnow

log = logging.getLogger(__name__)


@dataclass
class MarketsConfig:
    gt_top_pages: int = 3
    gt_new_pages: int = 3
    ohlcv_budget: int = 150  # GeckoTerminal OHLCV requests per run (15/min)
    ohlcv_min_liquidity_usd: float = 25_000.0
    chains: tuple[str, ...] = tuple(chains.CHAINS)


@dataclass
class MarketsReport:
    run_id: str
    requests: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors: list[str] = field(default_factory=list)
    new_tokens: int = 0
    rows: dict[str, int] = field(default_factory=dict)


def _table_exists(lake: Lake, table: str) -> bool:
    return table in lake.tables()


def run(
    lake: Lake,
    raw: RawStore,
    cfg: MarketsConfig | None = None,
    *,
    gt_client: HttpClient | None = None,
    dxs_client: HttpClient | None = None,
) -> MarketsReport:
    cfg = cfg or MarketsConfig()
    started = utcnow()
    run_id = f"mkt_{started:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    rep = MarketsReport(run_id=run_id)
    own = gt_client is None, dxs_client is None
    gt_client = gt_client or HttpClient(
        source=gt.SOURCE, base_url=gt.BASE_URL, raw_store=raw,
        max_per_minute=gt.MAX_PER_MINUTE, headers=gt.HEADERS, backoff_base=gt.BACKOFF_BASE,
    )
    dxs_client = dxs_client or HttpClient(
        source=dxs.SOURCE, base_url=dxs.BASE_URL, raw_store=raw, max_per_minute=dxs.MAX_PER_MINUTE
    )

    def get(client: HttpClient, endpoint: str, params: dict | None = None):
        rep.requests[client.source] += 1
        try:
            return client.get_json(endpoint, params)
        except (NotFound, UpstreamError) as exc:
            rep.errors.append(str(exc)[:200])
            return None

    def write(table: str, rows: list[dict]) -> None:
        if rows:
            lake.write(table, rows, run_id=run_id, fetched_at=utcnow())
        rep.rows[table] = len(rows)

    try:
        # 1. Discovery ---------------------------------------------------------------
        pool_rows: list[dict] = []
        for cid in cfg.chains:
            net = chains.CHAINS[cid].geckoterminal
            listings = (
                [("top", f"/networks/{net}/pools", {"page": p, "sort": "h24_volume_usd_desc"})
                 for p in range(1, cfg.gt_top_pages + 1)]
                + [("new", f"/networks/{net}/new_pools", {"page": p})
                   for p in range(1, cfg.gt_new_pages + 1)]
                + [("trending", f"/networks/{net}/trending_pools", {"page": 1})]
            )
            for listing, ep, params in listings:
                if f := get(gt_client, ep, params):
                    for r in gt.pool_rows(f.data, net, listing):
                        r["raw_sha256"] = f.raw.sha256
                        pool_rows.append(r)
        write("gt_pool_snapshot", pool_rows)

        candidates: dict[tuple[str, str], str] = {}
        for r in pool_rows:
            for tok in (r["base_token"], r["quote_token"]):
                if tok and tok not in chains.QUOTE_ASSETS[r["chain"]]:
                    candidates.setdefault((r["chain"], tok), f"geckoterminal:{r['listing']}")
        candidates.update(
            {k: v for k, v in _teh_candidates(lake).items() if k not in candidates}
        )

        # 2. Registry ----------------------------------------------------------------
        known: set[tuple[str, str]] = set()
        if _table_exists(lake, "token_registry"):
            known = set(lake.connect().execute(
                "SELECT DISTINCT chain, token FROM token_registry").fetchall())
        new = [
            {"chain": c, "token": t, "discovered_via": via}
            for (c, t), via in sorted(candidates.items())
            if (c, t) not in known and c in cfg.chains
        ]
        write("token_registry", new)
        rep.new_tokens = len(new)
        registry = sorted(known | {(r["chain"], r["token"]) for r in new})

        # 3. DexScreener snapshot ----------------------------------------------------
        by_chain: dict[str, list[str]] = defaultdict(list)
        for c, t in registry:
            if c in cfg.chains:
                by_chain[c].append(t)
        pairs: dict[tuple[str, str], dict] = {}
        for c, toks in by_chain.items():
            dchain = chains.CHAINS[c].dexscreener
            for i in range(0, len(toks), dxs.BATCH):
                batch = toks[i : i + dxs.BATCH]
                if f := get(dxs_client, f"/tokens/v1/{dchain}/{','.join(batch)}"):
                    for r in dxs.pair_rows(f.data):
                        r["raw_sha256"] = f.raw.sha256
                        pairs.setdefault((r["chain"], r["pair_address"]), r)
        write("dxs_pair_snapshot", list(pairs.values()))

        # 4. OHLCV backfill ----------------------------------------------------------
        write("gt_pool_ohlcv_day", _ohlcv(lake, cfg, pairs.values(), registry, gt_client, get))
    finally:
        if own[0]:
            gt_client.close()
        if own[1]:
            dxs_client.close()
    rep.requests = dict(rep.requests)
    return rep


def _teh_candidates(lake: Lake) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    tables = set(lake.tables())
    con = lake.connect()
    for table in ("teh_launchpad_top_tokens", "teh_bot_top_tokens"):
        if table not in tables:
            continue
        rows = con.execute(
            f"SELECT DISTINCT chain, token FROM {table} "
            f"WHERE run_id = (SELECT max(run_id) FROM {table})"
        ).fetchall()
        for teh_chain, tok in rows:
            c = chains.from_teh(teh_chain or "")
            if c and tok:
                t = chains.norm_address(c, tok)
                if t not in chains.QUOTE_ASSETS[c]:
                    out.setdefault((c, t), f"tehcscreener:{table}")
    return out


def _ohlcv(lake, cfg, pair_rows, registry, client, get) -> list[dict]:
    today = utcnow().date()
    # Most liquid pair per token, where the token is the pair's base token.
    best: dict[tuple[str, str], dict] = {}
    reg = set(registry)
    for p in pair_rows:
        key = (p["chain"], p["base_token"])
        if key not in reg or (p["liquidity_usd"] or 0) < cfg.ohlcv_min_liquidity_usd:
            continue
        if key not in best or (p["liquidity_usd"] or 0) > (best[key]["liquidity_usd"] or 0):
            best[key] = p

    last_day: dict[tuple[str, str, str], object] = {}
    if "gt_pool_ohlcv_day" in lake.tables():
        for c, pool, tok, d in lake.connect().execute(
            "SELECT chain, pool_address, token, max(day) FROM gt_pool_ohlcv_day GROUP BY ALL"
        ).fetchall():
            last_day[(c, pool, tok)] = d

    jobs = []
    for (c, tok), p in best.items():
        ld = last_day.get((c, p["pair_address"], tok))
        if ld is not None and ld >= today - timedelta(days=1):
            continue  # already complete through yesterday
        limit = gt.OHLCV_MAX_DAYS if ld is None else min(gt.OHLCV_MAX_DAYS, (today - ld).days + 2)
        # Never-fetched first, then most liquid first.
        jobs.append((ld is not None, -(p["liquidity_usd"] or 0), c, tok, p["pair_address"], limit))
    jobs.sort()

    rows: list[dict] = []
    for _, _, c, tok, pool, limit in jobs[: cfg.ohlcv_budget]:
        net = chains.CHAINS[c].geckoterminal
        f = get(client, f"/networks/{net}/pools/{pool}/ohlcv/day",
                {"limit": limit, "currency": "usd", "token": tok})
        if f:
            for r in gt.ohlcv_rows(f.data, c, pool, tok, before=today):
                r["raw_sha256"] = f.raw.sha256
                rows.append(r)
    log.info("ohlcv: %d jobs pending, %d fetched", len(jobs), min(len(jobs), cfg.ohlcv_budget))
    return rows
