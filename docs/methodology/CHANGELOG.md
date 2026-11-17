# Methodology change log

Every change to a published formula, input, universe rule or data source is recorded here with its date and reason, and is marked on affected charts. Entries are never edited after the fact.

| Date | Change | Reason |
|---|---|---|
| 2026-11-17 | Project started. No indicators published yet. | — |
| 2026-11-17 | Universe rule v1: entry on first observed day with market cap ≥ $1M and liquidity ≥ $50K (sum over pairs where the token is base); quote assets excluded; entries never removed. Observed from our own snapshots from 2026-11-17. | SPEC §5.2. No free source publishes liquidity history, so the pre-2026-11-17 backfill will be a separate, labelled version built from Dune. |
| 2026-11-17 | Trade-level source changed from Dune to BigQuery public Solana data, Helius, Alchemy, public EVM RPCs and GeckoTerminal trades. | Dune has no free API plan. No indicator is published yet, so no history is affected. |
| 2026-11-17 | BNB Chain deferred: no longer ingested, and excluded from the universe and all reads. 45 BNB universe entries published earlier the same day stay stored (append-only) but are not read. | Scope decision by Arthur. |
| 2026-11-17 | Robinhood Chain swaps come from the official public RPC (`rpc.mainnet.chain.robinhood.com`), which returned a full day of logs for one pool in under a second. Alchemy is the fallback. | Alchemy's free plan limits `eth_getLogs` to 10 blocks, and Robinhood produces about 10 blocks a second. |
| 2026-11-17 | Chain Rotation Monitor formula `0-raw` (DefiLlama total DEX volume) computed and backtested 2023-09 to 2026-11. Fails its drop rule: shares mean-revert, and Leading underperforms Lagging over 14 days. Stored as description only; not displayed. See `docs/validation/chain_rotation_0-raw.md`. | First indicator through the shared harness. |
