# CLAUDE.md

## Project
An onchain research website for active memecoin and microcap traders on Solana, Base, Ethereum, BNB Chain and Robinhood Chain. It improves on TEHscreener and Sparsity and adds new indicators. The owner is Arthur.

**Read `SPEC.md` before doing anything.** It holds the scope decisions, every indicator formula, data sources, the validation harness, page plan, build phases and open items. If a request conflicts with SPEC.md, point out the conflict and ask before deviating.

## How to work
- Build in the phase order in SPEC.md §10. Do not start a later phase's features before the data they depend on exists.
- Treat SPEC.md formulas as MVP definitions. Improvements are welcome, but propose them with a reason, and record accepted changes in SPEC.md and the methodology change log.
- Every indicator ships with three things: its point-in-time storage, a backtest in the shared harness, and its drop rule. An indicator that fails its drop rule is shown as description only.

## Non-negotiable data rules
- **No look-ahead.** Cohorts, skill rankings, universes and normalization windows use only data available before the time being scored. Write a test for this on every indicator.
- **Point-in-time storage.** Published values are append-only, with formula version, input cutoff and publish timestamp. Never silently recompute history.
- **Organic filters first.** Remove arbitrage, MEV, wash trading, bots, spam launches and stable-to-stable swaps before computing anything user-facing.
- **Universe rules.** The universe is rule-based and keeps dead coins. No hand curation.
- **Smoothing.** No one-sided smoothing or cooldowns. State changes need two consecutive confirming readings.

## Data sources
- Free sources first: TEHscreener API (credit "tehcscreener.com" when publishing derived stats; confirm commercial terms), Dune, DefiLlama, DexScreener, GeckoTerminal, Hyperliquid info API, Mobula.
- Robinhood Chain has adequate third-party providers; do not build a custom indexer.
- Scraping is allowed, including Sparsity and GMGN (Arthur, 2026-11-19: the site is a private tool). Scrape politely: low request rates, cache every raw response, and prefer an official API where one exists.
- Spending stays at $0 (Arthur, 2026-11-19). Do not subscribe to any paid data provider or API plan; ask Arthur if a paid option becomes essential.
- Respect rate limits (TEHscreener: 120 requests/min). Cache raw responses.

## Scope guardrails
- Wallet labels and entity clustering are internal plumbing, not a user-facing product.
- Out of scope unless Arthur says otherwise:
  - Catalyst feed.
  - Launch safety product.
  - Heat map.
  - Telegram bot.

## Product and copy standards
- Every user-facing view answers its question on one screen: state, why, risk, levels, base rate, what would flip it.
- Copy is professional prose with complete sentences. No marketing hype and no fragmented sentences.
- Visual design should look genuinely considered. Avoid generic AI-looking palettes (default purple/blue gradients, neon accents). Choose a deliberate, restrained palette and typography, and justify the choice briefly.
- Every page states "research, not financial advice."

## Open items to resolve early
See SPEC.md §11. Fetch the TEHscreener `/api/v1/trench` method block and record the blend, cooldown factor and band thresholds as one of the first Phase 0 tasks.
