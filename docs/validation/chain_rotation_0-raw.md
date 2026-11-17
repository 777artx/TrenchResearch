# Validation: Chain Rotation Monitor, formula 0-raw (2026-11-17)

**Verdict: fails its drop rule. Shown as description only, without signal framing.**

## Setup

- Input: DefiLlama daily total DEX volume for Solana, Base, Ethereum and Robinhood Chain (all pairs, no organic filtering). This is formula `0-raw`, for validation and internal use; it is never displayed, because user-facing values require organic inputs.
- Period: 2023-09-06 to 2026-11-16 (Base's history starts 2023-07-31; the indicator needs 37 days of lookback). Robinhood enters in July 2026 once it has a full lookback window, through chain-linking.
- Samples: every 7th day (non-overlapping weeks), 505 chain-weeks.
- Intervals: 95% date-block bootstrap (blocks of 4 weekly dates, 2,000 resamples).
- The indicator has no fitted parameters, so the whole period is out of sample.

## Results

| Test | Result | 95% interval | Pass? |
|---|---|---|---|
| Persistence beyond one week: rank IC of share change over [t−7, t] vs [t+7, t+14] | −0.089 | −0.195 to +0.023 | No |
| Separation: forward 14-day change in log share, Leading minus Lagging | −0.098 | −0.193 to −0.035 | No (significant, wrong sign) |
| Stability: median days per confirmed state | 7, 7, 8, 7 days | — | Yes (≥ 5) |

Forward 14-day change in log share by confirmed state: Leading −3.1% (n = 155), Weakening −2.4% (97), Improving +2.1% (86), Lagging +6.7% (167).

## Reading

Chain shares of DEX volume mean-revert over two weeks: chains that have been gaining share tend to give some back, and chains that have been losing share tend to recover. The momentum framing of the quadrants ("rotate into Leading") is therefore wrong on this input.

A contrarian reading of the same quadrants is a hypothesis, not a finding: it was suggested by this data and must be tested on data not used here, specifically formula `1` (organic memecoin volume), before it can carry signal framing.

## Caveats

- Raw DEX volume is dominated by stablecoin and major-token trading, not memecoins.
- Forward price returns of chain memecoin baskets were not tested, because our price history (six months, current universe only) would bias the test toward survivors.
