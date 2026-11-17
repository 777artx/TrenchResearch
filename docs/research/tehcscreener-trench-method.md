# TEHscreener Trench Index: recorded method (SPEC §11, items 1 and 2)

Fetched on 2026-11-17 from `https://tehcscreener.com/api/v1/trench` and the API docs page. The raw response is cached at `tests/fixtures/tehcscreener/trench.json` (the 2026-11-17 response, kept as a test fixture). The latest sync (`/status`) was 2026-11-17 04:11 UTC, with the latest scored day 2026-11-16.

## Method block as published

| Field | Value |
|---|---|
| `window_days` (short window) | 90 |
| `window_days_long` (long window) | 365 |
| `blend` | short 0.6, long 0.4 |
| `cooldown` | 0.65 |
| `weights` | pad_volume 0.20, tokens_launched 0.10, pad_revenue 0.15, bot_volume 0.30, bot_fees 0.25 |
| `bands` | ded 0–19, cold 20–39, active 40–59, hot 60–79, euphoric 80–100 |

The documentation describes `cooldown` as "score drops decay by this factor per day; rises apply same-day." A day is scored only when launchpad, launchpad revenue and terminal data are all present, and once 30 such days exist. Each component's percentile is the 0.6/0.4 blend of its 90-day and 365-day percentile ranks.

## Checks against the published history

The history runs from 2024-02-20 to 2026-11-16 (1,001 consecutive days, no gaps). The latest reading is 23 ("cold").

- **The weighted sum reproduces the latest score.** On 2026-11-16 the component percentiles were 24, 35, 29, 24 and 14, which give 0.20·24 + 0.10·35 + 0.15·29 + 0.30·24 + 0.25·14 = 23.35, matching the published 23. That day was not a drop, so the cooldown did not bind.
- **The cooldown is visibly one-sided.** Across the history the largest one-day rise is +49 points and the largest one-day drop is −18. There are 597 down days, 308 up days and 95 flat days. The smallest ratio of a day's score to the previous day's is 0.684, so no day has fallen below 0.65 times the prior score. This is consistent with a rule of the form `score_t = max(raw_t, 0.65 × score_(t−1))`, but the endpoint does not publish raw scores, so the exact rule cannot be confirmed from this response alone. We tried reconstructing raw scores from `/launchpads/series` and `/bots`. The reconstruction gives 22.9 for 2026-11-16 (published: 23), but across the history it misses by about 6 points on average under every cooldown rule tested, because the percentile convention and the exact set of tracked terminals are not documented. The exact rule stays unconfirmed. It does not affect our build, since we do not reuse the index.

## Implications for our build

These figures confirm the weaknesses listed in SPEC §4.1. A floor of 65% of the prior score means a collapse from 80 to 20 takes at least four days to register, which is exactly the delayed risk-off reading our Trench Regime avoids with symmetric two-day confirmation.

## Open item 2: pump.fun and PumpSwap (resolved)

The API docs state that "a launchpad's own AMM (e.g. pump.fun's PumpSwap) is reported here [under `/dexes`], never in `/launchpads`." DEX revenue never enters launchpad numbers. pump.fun's launchpad volume therefore excludes PumpSwap, and the post-graduation volume split in SPEC §6.3 must pull PumpSwap from `/dexes/solana/pumpswap` or Dune.

## Open item 1: commercial terms (still open)

The docs say only: "The API is free to use. If you publish statistics or charts, credit tehcscreener.com as the source." Commercial reuse is neither granted nor excluded. Arthur should confirm it with the operator in writing before launch.

## Coverage note found during ingestion

`/chains` covers only Solana, Base, Robinhood, HyperEVM, Arc and Elysium, from 2026-04-01. It has no Ethereum or BNB Chain chain-wide stats, so the Chain Rotation Monitor (SPEC §6.2) must source those two chains from DefiLlama or Dune. Terminal data (`/bots`) does include Ethereum and BNB.
