# Trade-level data sources (replacing Dune)

Decided 2026-11-17. Dune has no free API plan, so SPEC §5.1 and §10 now use the sources below. Credentials live outside the repository: proxy-injected network secrets for header-based keys, and files under `~/.config/trench/` (mode 600) for the Google service account and the Alchemy key during development. The scheduled production job will read them from GitHub Actions secrets.

| Source | Chains | What it gives | Status |
|---|---|---|---|
| Google BigQuery public dataset `bigquery-public-data.crypto_solana_mainnet_us` | Solana | Raw `Blocks`, `Transactions`, `Instructions`, `Token Transfers`, `Tokens`, `Accounts`. Current to within minutes (latest block 2026-11-17 22:04 UTC when checked). | Working (service account `claude@genesis-485720`). |
| Helius RPC and enhanced transactions API | Solana | Per-address transaction history; swaps already decoded (wallet, mints, amounts, venue). | Working. Key injected as `X-Api-Key`. Free plan: 1M credits a month. |
| Robinhood Chain public RPC `rpc.mainnet.chain.robinhood.com` | Robinhood Chain | `eth_getLogs` over a full day (842K blocks) for one pool in 0.7 s, no key. | Working. Primary Robinhood trade source. |
| Alchemy | Solana, Robinhood Chain, Base, Ethereum | General RPC. The free plan limits `eth_getLogs` to a 10-block range, which is about one second of Robinhood blocks, so it is a fallback only. | Working, all networks enabled. |
| Public RPCs (publicnode, mainnet.base.org) | Base, Ethereum | `eth_getLogs` for Swap events on universe pools. | Allowed; not yet wired. |
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

## First Solana extract (2026-11-16, 12:00–13:00 UTC)

- 119 tracked mints (Solana universe tokens plus registered tokens with at least $25K liquidity).
- 17,979 transactions and 47,917 transfers, for 1.01 GB scanned. A full day is therefore about 24 GB, or about 720 GB a month, which fits the 1 TB free tier with roughly 280 GB a month left for backfill.
- 71% of selected transactions include a native SOL leg, as expected for pump.fun-style trades. None of the selected transactions contains a transfer without a mint.
- Known blind spot: a transaction whose only tracked-token leg is a plain `Transfer` (no mint field) is not selected. Its size will be measured against Helius decoded swaps.
- The `Transactions` table (pre/post token balances with owners) would remove that blind spot but costs about 479 GB a day for the needed columns, so it is not usable on the free tier.

## Finding: BigQuery Token Transfers misses DEX swap legs (2026-11-17)

Test: 20 recent swaps on the most active PumpSwap pool (token `ELR9i6Z7…`, classic Token program) were pulled from Helius, which showed 51 pool-to-wallet legs (buys) and 18 wallet-to-pool legs (sells). The same 20 signatures were then looked up in BigQuery `Token Transfers`. BigQuery had 17 of the 20 transactions but **none** of the 69 transfers of the token itself.

Consistent with this, the 1-hour extract reconstructed 12,649 "sells" and only 1,077 "buys", and almost no transfers signed by a pool (program-derived) authority. The table appears to omit transfers made by cross-program invocation (inside DEX programs), which is how almost every swap moves tokens. Native SOL transfers also carry no amount, and the `log_messages` column is sparsely populated (34 pump.fun transactions in 10 minutes, against thousands in reality).

Also measured: 61 of the first 100 tracked Solana mints use Token-2022.

**Decision:** BigQuery is not used as the Solana swap source. The extract code, the owner resolver and the swap reconstruction stay in the repository, because the reconstruction logic applies equally to transfers obtained over RPC. Total BigQuery usage for all probes so far is about 21 GB of the 1 TB free monthly quota, and the monthly cap in code remains in force.

## Free trade sources that remain

| Source | Coverage | Limit |
|---|---|---|
| GeckoTerminal `/pools/{pool}/trades` | All chains. Each trade has the signer wallet, side, token amounts and USD value. | Last 300 trades per pool per call; forward-only, no history. With polling, complete for pools with fewer than about 300 trades per polling cycle, which covers most microcaps. |
| Robinhood public RPC `eth_getLogs` | Robinhood, complete, with history | none found yet |
| Public EVM RPCs `eth_getLogs` | Base, Ethereum, complete, with history | provider block-range limits |
| Helius RPC and enhanced API | Solana, complete and exact | 1M credits a month on the free plan, roughly 30K transactions a day: enough for targeted work (deployer funding, specific coins, validation), not for every universe token. |
