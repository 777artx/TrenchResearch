# Launchpad Scorecard: cohort of 2026-11-11 (Robinhood Chain), formula 0

Launches between 2026-11-11 00:00 and 2026-11-12 00:00 UTC, each followed for 7 days. The Long.xyz launch count (147) matches TEHscreener's figure for the day exactly.

| Measure | Long.xyz | PonsFamily |
|---|---|---|
| Launches | 147 | 859 |
| Distinct creator wallets | 20 | 764 |
| Spam share (launches without 10 real buyers in the first hour) | 98% | 71% |
| L* (real launches) | 3 | 248 |
| Reached $100K within 24 h (of L*) | 0 | 8 |
| Above $50K at day 7 (of L*) | 0 | 5 (understated, see below) |
| Reached $1M within 7 days (of L*) | 0 | 1 (understated, see below) |
| Creator sold at least half its first-hour buys within 60 min (of L*) | 0 | 140 (56%) |
| Median buyer return at 24 h vs first-hour VWAP (L*) | −10.6% | −26.7% |

## What the numbers say

- Long.xyz's volume of launches is almost entirely a few wallets: 147 launches from 20 creators, 3 with real early demand, none reaching $100K.
- PonsFamily launches are mostly one-off creators (764 wallets), and 29% attract real early buyers, but more than half of those see the creator dump within the hour, and the median early buyer is down 27% a day later.

## Why the LQS published for this day is not meaningful yet

The published LQS (Long.xyz 80, PonsFamily 70) should not be read as Long.xyz being the better pad:

1. With two pads, a percentile rank can only be 0 or 100 per component, so LQS is a coin flip between pads.
2. The beta-binomial prior is fitted on pooled pad history. With only Long.xyz's 3 real launches, its shrunk rates sit almost on the prior, which is dominated by PonsFamily (for example Long.xyz's shrunk rug rate is 59% although 0 of its 3 real launches were rugged).

The scorecard view will therefore show raw counts and rates with their sample sizes until at least four pads and four weekly cohorts exist. All readings carry `validated: false`.

## Gaps to close

- 55 PonsFamily tokens left their bonding curve within 7 days (17 of them L*). For 31 of the 55, GeckoTerminal returned no data (rate limiting), so their post-curve survival and peak are missing and Surv7 and Runner are understated. The fix is to fetch these candles in the daily job at a slower pace with retries.
- Flap (Robinhood) and thestonks.exchange (Base) are not yet included.
- Long.xyz quote-token prices are current DexScreener prices, not daily.
