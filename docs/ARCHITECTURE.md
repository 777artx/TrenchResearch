# Architecture

## Stack and why

| Choice | Reason |
|---|---|
| Python 3.13, managed with `uv` | The workload is data engineering and statistics: ingestion, cost-basis accounting, percentile ranks, walk-forward backtests and calibrated models (scikit-learn). Python has the strongest libraries for all of it, and `uv` gives reproducible, fast environments. |
| Parquet files, queried with DuckDB | Write-once files make the append-only rule physical rather than a convention. DuckDB queries them in place with full SQL and window functions, needs no server, and scales comfortably to the billions of swap rows Phase 2 will need on one machine. Moving to object storage later is a path change, not a rewrite. |
| Typer CLI as the job runner | Phase 0 has one daily job. A command that cron, a systemd timer or a hosted scheduler can call keeps the choice of hosting open. |
| Static front end (planned, Phase 1) | Published values are produced once a day (hourly later for the Flow Desk). The site can be generated from the point-in-time store and served statically, which is fast, cheap and leaves nothing to compromise. Astro is the likely choice; it will be decided when the first page is built. |

## Data flow

```
upstream API ──► HttpClient ──► RawStore         data/raw/<source>/<date>/*.json.gz + manifest.jsonl
                 (rate limit,       │
                  retries)          ▼
                              normalizers (pure functions, tested on fixtures)
                                    │
                                    ▼
                              Lake               data/lake/<table>/fetched_date=<d>/<run_id>.parquet
                                    │            every row: fetched_at, run_id, raw_sha256
                                    ▼
                              indicators (Phase 1+) read with Lake.as_of(cutoff)
                                    │
                                    ▼
                              PITStore           data/lake/<metric>/...  value, formula_version,
                                                 input_cutoff, published_at, restatement_reason
                                    │
                                    ▼
                              site and track record read published values only
```

## Two clocks

Upstream data has two times: the day a row describes (`day`) and the moment we learned it (`fetched_at`). Sources revise history. TEHscreener recomputed its whole index on 2026-11-12, and onchain indexers backfill late blocks. We therefore never overwrite: each fetch adds a new version, and `Lake.as_of(table, keys, cutoff)` returns what was known at `cutoff`. Indicator code must read inputs through `as_of` with the indicator's input cutoff. This is how the "no look-ahead" rule is enforced at the data layer.

History fetched on our first run is a caveat: for days before that run we only know the value as it stood on that date, not as it was originally published. Backtests over that period carry revision risk, and the methodology page will say so.

## Published values

`PITStore.publish` refuses to overwrite. A correction requires a `restatement_reason` and is written as a new row, so both versions stay readable. A new formula version is published alongside the old one. `input_cutoff` may not be later than `published_at`.

## Tables (TEHscreener, prefix `teh_`)

| Table | Grain | Notes |
|---|---|---|
| `teh_launchpad_series` | chain, pad, day | volume, launches, protocol revenue |
| `teh_launchpad_daily` | chain, pad, day | adds trade transactions |
| `teh_launchpad_revenue` | chain, pad, day | protocol, creator (from Oct 2026), buyback |
| `teh_launchpad_top_tokens` | snapshot | daily top 50 by volume, `traded` and `launched` modes; accumulates from first run |
| `teh_bots_by_bot`, `teh_bots_by_chain` | bot or chain, day | terminal volume, transactions, fees |
| `teh_bot_chain_daily` | bot, chain, day | adds wallets per chain |
| `teh_bot_wallets_dedup` | bot, day | null where the source has no deduplicated count |
| `teh_bot_top_tokens` | snapshot | daily; only tokens that reached 25+ wallets |
| `teh_bot_perps_daily` | bot, day | Hyperliquid builder-code notional, excluded from terminal volume |
| `teh_chain_daily` | chain, day | from 2026-04-01; Solana, Base, Robinhood, HyperEVM, Arc, Elysium only |
| `teh_dex_daily` | chain, dex, day | includes PumpSwap, which is not in launchpad volume |
| `teh_rwa_daily` | chain, day | tokenized RWA volume and value |
| `teh_trench_*` | day | competitor index, kept for comparison only |
| `teh_status`, `teh_*_profile` | snapshot | upstream sync and profile metadata |

## Tables (markets)

| Table | Grain | Notes |
|---|---|---|
| `gt_pool_snapshot` | chain, pool, fetch | GeckoTerminal top, new and trending pools: reserve, market cap, FDV, 24h volume, unique buyers and sellers |
| `token_registry` | chain, token | grows only; first discovery and how it was found |
| `dxs_pair_snapshot` | chain, pair, fetch | DexScreener state of every pair of every registered token |
| `gt_pool_ohlcv_day` | chain, pool, token, day | daily USD candles for each token's most liquid pool; incomplete current day excluded |

## Published metrics

| Metric | Entity | Meaning |
|---|---|---|
| `universe_entry` (v1) | `chain:token` | date the token first met the universe rule; never removed. Membership on a date = all entries dated on or before it. |
