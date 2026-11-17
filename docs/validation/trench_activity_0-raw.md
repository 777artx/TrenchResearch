# Validation: Trench Regime Activity, formula 0-raw (2026-11-17)

**Verdict: fails its drop rule. Shown as description only, without signal framing.**

## Setup

- Components available with history:
  - V: DefiLlama total DEX volume divided by the base-asset price (SOL for Solana, ETH for Base, Ethereum and Robinhood).
  - P: TEHscreener daily active wallets, from 2026-04-01, Solana, Base and Robinhood only (not organic).
- Not yet available: Q (graduation × 7-day survival) and R (recent graduates above graduation price).
- Each component is ranked against the trailing 365 days before the day being scored, and used only after 180 days of history. Robinhood has fewer than 180 days and is not scored yet.
- Forward outcome: 14-day log return of the chain's base asset. This proxy has no survivorship bias; a memecoin basket needs a point-in-time universe with dead coins, which we do not have historically.
- Samples: every 7th day, 358 chain-weeks, 2023-07-24 to 2026-11-16. Intervals: 95% date-block bootstrap.

## Results

| Test | Result | 95% interval | Pass? |
|---|---|---|---|
| Extremes: forward 14-day return, Activity ≥ 80 minus ≤ 20 | +3.8% | −3.6% to +12.4% | No |
| Hot minus cold (confirmed state) | +0.2% | −4.8% to +4.5% | No |
| Rank IC, Activity vs forward 14-day return | +0.04 | −0.11 to +0.18 | No |
| Stability: median days per state | 4, 4, 5 days | — | No (needs ≥ 5) |

## Reading

On raw inputs, how busy a chain is does not predict the base asset's next two weeks, and the hot/cold state flips too often. The reading remains useful as description: on 2026-11-16 Base volume ranked at the 89th percentile of its year while active wallets ranked at the 17th, the "dollars high, wallets low" divergence that SPEC §6.1 asks the page to call out as bot-heavy activity.

The organic version (formula 1: organic buying entities, organic memecoin volume, launch outcomes) will be validated separately once it has enough history.
