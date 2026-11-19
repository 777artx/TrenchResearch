# GMGN and Sparsity as data sources (2026-11-19)

Scraping approved by Arthur on 2026-11-19 (private tool). Rules: polite request rates, every raw response cached, results stored point in time like any other source.

## GMGN (gmgn.ai)

Plain HTTP requests get a Cloudflare 403. A headless Chromium session (the pre-installed Playwright) passes the check, and requests made from inside the page with `fetch` return JSON. Every request carries the web app's query parameters (`device_id, tab_id, fp_did, client_id, from_app, app_ver, tz_name, tz_offset, app_lang, os`); the collector copies them from the page's own first request.

| Endpoint (path) | Content | Use |
|---|---|---|
| `/vas/api/mul-region/token_trades_v2/sol/{token}` (`limit`, `cursor`) | 50 trades per page: maker wallet, base/quote amounts, `amount_usd`, `price_usd`, `event` (buy/sell), `tx_hash`, `maker_tags` / `maker_token_tags` (smart money, sniper, KOL and others), the maker's `realized_profit`, `unrealized_profit`, `history_bought_amount`, `priority_fee`, `tip_fee`, `gas_usd` | Solana trade-level data; cohort flow; urgency index; buyer PnL |
| `/vas/api/v1/token_holders/sol/{token}` (`limit`, `cursor`, `orderby`, `direction`) | 100 holders per page with balance, share of supply, `accu_cost` and `cost` (cost basis), `profit`, buy/sell/transfer history, `wallet_tag_v2`, `exchange` | Cost-basis map; holder quality; insider and exchange share |
| `/vas/api/v1/token_holder_stat/sol/{token}` | Holder counts by type | Breadth |
| `/api/v1/tokens/top_buyers/sol/{token}` | Earliest buyers and their status | Sniper share |
| `/api/v1/rank/sol/wallets/7d` (`orderby`, `direction`) | 100 wallets with PnL and realized profit over 1, 7 and 30 days, win-rate buckets, holding periods, net inflow, multi-chain balances (including Robinhood) | Seed list for the SMART cohort |
| `/defi/quotation/v1/smartmoney/sol/wallet/{wallet}` | One wallet's summary | Wallet profiles |
| `/api/v1/token_mcap_candles/sol/{token}` | Market-cap candles | Prices for Solana launches |
| `/vas/api/v1/callout_radar/list`, `/api/v1/notification/callout/content_rank` | KOL callouts | Attention vs flow (prototype) |

Measured on 2026-11-19: on a busy Solana token, 16 pages of trades (800 trades) reached back about 2 days. Total history depth per token is not yet known.

Caveats:
- GMGN's tags and PnL figures are GMGN's own definitions. They are stored as inputs, point in time, and validated against our own computations where we have them (EVM chains); they never replace SPEC definitions.
- Endpoint paths and parameters are internal and may change without notice. The collector must fail loudly, not silently.
- Running a headless browser costs CPU time; a GitHub Actions run needs about a minute to start it.

## Sparsity (sparsitydata.com)

The research tools (Holder Strength and others) are public pages, readable without an account. They will be collected daily as a competitor reference, so our indicators can be compared with theirs over time. Not yet mapped endpoint by endpoint.

## Status (2026-11-19)

Reaching GMGN requires a headless browser to get past its Cloudflare bot protection, which likely breaches GMGN's terms of service. Arthur accepted that risk explicitly on 2026-11-19, and the collector now runs in the daily job.

First live test (5 tokens, 3 trade pages each): 600 trade rows from 204 wallets, 400 holder rows with cost basis, 300 ranked wallets, no errors. 71% of trades came from tagged wallets; the most common tag was `sandwich_bot` (305 of 600), and terminal tags (`axiom`, `fomo`, `gmgn`) identify the app used, which is the venue segment the Retail Flow Desk needs.

Limit: on busy tokens three pages of trades reach back only about 20 minutes, so a daily run with up to 15 pages per token samples each day's trades rather than capturing all of them. Holder snapshots, cost basis and wallet ranks are complete as of the run.
