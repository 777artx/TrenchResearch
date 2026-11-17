# Trench Research

Onchain research for active memecoin and microcap traders on Solana, Base, Ethereum, BNB Chain and Robinhood Chain. Every headline output is a state with a base rate, not a raw number.

Research, not financial advice.

- `SPEC.md` is the source of truth for scope, indicator formulas, data sources and build order.
- `CLAUDE.md` holds the working rules for this repository.
- `docs/ARCHITECTURE.md` explains how data moves from upstream APIs to published values.

## Quick start

```bash
uv sync
uv run pytest
uv run trench ingest tehcscreener   # full refresh, about 120 requests, 90 seconds
uv run trench tables
uv run trench sql "SELECT day, score FROM teh_trench_history ORDER BY day DESC LIMIT 5"
```

Data is written under `./data` (override with `TRENCH_DATA_DIR`) and is never committed.

## Status

Phase 0 (foundation) is in progress.

- Done: point-in-time storage, raw response cache, rate-limited client, TEHscreener ingestion with full history, DexScreener and GeckoTerminal market data (discovery, token registry, pair snapshots, daily OHLCV), and the forward point-in-time universe (v1).
- Next: Dune trade-level ingestion for Solana, which also enables the universe backfill before 2026-11-17.

The daily job is `uv run trench daily`.

Aggregate data from TEHscreener is credited to tehcscreener.com.
