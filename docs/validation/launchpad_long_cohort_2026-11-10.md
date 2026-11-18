# Launchpad Scorecard: first cohort, Long.xyz (Robinhood Chain)

Launches in a 842,000-block window (about one day) spanning 2026-11-10/11, followed for 7 days. Built from the chain: factory launch events, Uniswap V4 `Initialize` and `Swap` logs, and transaction senders for first-hour swaps. TEHscreener reports 178 and 147 Long launches on those two calendar days; the block window covers part of each, and will be pinned to exact UTC days in the production version.

| Measure (SPEC §6.3) | Result |
|---|---|
| Launches | 129, from 13 creator wallets |
| Launches with no swap at all in 7 days | 105 |
| L*: at least 10 unique non-creator buyers in the first 60 minutes | 2 |
| Grad: $100K market cap within 24 h | 0 of 2 (0 of all 129) |
| Surv7: market cap at least $50K at day 7 | 0 of 2 (0 of 129) |
| Runner: $1M peak within 7 days | 0 of 2 (0 of 129) |
| Rug: creator sold at least half its own first-hour buys within 60 min | 0 of 2 (1 of 129) |
| BuyRet: median 24 h return vs first-hour VWAP (L*) | −15.5% |
| Highest 7-day peak market cap | $72K |

Method notes and approximations (v0):
- Long pairs each token against a quote token, usually a tokenized stock (TTWO, NVDA, META and others). USD values use the quote tokens' current DexScreener prices; 2 of 13 quote tokens had no price and their launches have no USD milestones. Stock prices move little within a week relative to the $100K and $1M milestones, but the production version will use daily quote prices.
- Supply is 1e9 tokens for every launch (from the launch event); market cap = price × supply.
- Surv7 omits the liquidity ≥ $10K condition: V4 pool liquidity needs pool state reads, not yet implemented.
- "Rug" uses the creator's own first-hour buys as the base because the creator's initial allocation is not in the launch event.

Reading: on this day, Long.xyz launches were almost entirely spam by count (13 wallets, 105 launches that never traded), and none of the launches that drew real buyers reached $100K. This is the "launches are spam" problem from SPEC §4.1, measured per pad. The cross-pad score (LQS) needs the same measures for the other pads; PonsFamily is next.
