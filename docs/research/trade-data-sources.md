# Trade-level data sources (replacing Dune)

Decided 2026-11-17. Dune has no free API plan, so SPEC §5.1 and §10 now use the sources below. Credentials live outside the repository: proxy-injected network secrets for header-based keys, and files under `~/.config/trench/` (mode 600) for the Google service account and the Alchemy key during development. The scheduled production job will read them from GitHub Actions secrets.

| Source | Chains | What it gives | Status |
|---|---|---|---|
| Google BigQuery public dataset `bigquery-public-data.crypto_solana_mainnet_us` | Solana | Raw `Blocks`, `Transactions`, `Instructions`, `Token Transfers`, `Tokens`, `Accounts`. Current to within minutes (latest block 2026-11-17 22:04 UTC when checked). | Working (service account `claude@genesis-485720`). |
| Helius RPC and enhanced transactions API | Solana | Per-address transaction history; swaps already decoded (wallet, mints, amounts, venue). | Working. Key injected as `X-Api-Key`. Free plan: 1M credits a month. |
| Alchemy | Solana, Robinhood Chain (and Base, Ethereum, BNB if enabled) | RPC, including `eth_getLogs` for pool Swap events on Robinhood Chain. | Key valid; networks must be enabled on the Alchemy app. |
| Public RPCs (publicnode, mainnet.base.org) | Base, Ethereum, BNB | `eth_getLogs` for Swap events on universe pools. | Allowed; not yet wired. |
| GeckoTerminal `/pools/{pool}/trades` | All five | Last 300 trades per pool with wallet, side and USD size. | Allowed; not yet wired. |

## BigQuery cost profile (measured)

| Table | Size | Rows | Partitioning |
|---|---|---|---|
| Token Transfers | 46.7 TB | 155.5B | daily on `block_timestamp`, partition filter required |
| Transactions | 1,019.5 TB | 592.3B | daily |
| Instructions | 1,004.7 TB | 1,224.4B | daily |

One day of `Token Transfers` scans about 18.8 GB (dry run for 2026-11-16). The free tier is 1 TB a month, so:

- Daily ingestion of the previous day's token transfers costs about 570 GB a month, which fits the free tier.
- The remaining ~430 GB a month backfills about 22 days of history per month. A full year of backfill (~7 TB) would take most of a year on the free tier, or about $45 at $6.25/TB with billing enabled. Enabling billing is a paid decision for Arthur.
- `Transactions` and `Instructions` are about 20 times larger per day and are not usable on the free tier except for narrow, targeted reads.

Swaps are reconstructed from token transfers: within one transaction, the trading wallet sends one mint and receives another. Helius's decoded swaps serve as the check on that reconstruction for a sample of transactions.

The decoded Solana DEX datasets announced by Google and Token Terminal are not in this public dataset. Locating them is an open task.
