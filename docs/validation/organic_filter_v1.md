# Organic filter v1 on EVM swaps (2026-11-17)

Rules are defined in `src/trench/organic.py`: atomic arbitrage, sandwiches, same-block round trips, high frequency (more than N swaps in any 60 seconds) and two-sided near-zero-inventory BOT/MM flow.

## First measurement: Robinhood Chain, 6 hours (2026-11-17), 44 universe pools, 19,770 swaps

Sensitivity to the high-frequency threshold N, which SPEC §5.5 leaves open:

| N (swaps per minute) | Organic share of swaps | Organic share of USD volume | Organic traders |
|---|---|---|---|
| 3 | 14.9% | 49.4% | 2,148 |
| 5 (chosen) | 20.7% | 56.5% | 2,411 |
| 10 | 30.6% | 68.7% | 2,687 |

USD values were available for 67% of swaps (quotes in ETH, WETH or USDG).

The five most active flagged wallets made 405 to 2,068 swaps each in six hours, each on a single token with buys between 46% and 54% of swaps: unambiguous bots. At N = 3, about 3,150 flagged swaps came from wallets with 10 or fewer swaps, which may include people whose trading app splits orders, so v1 uses N = 5. N will be calibrated against a labelled bot list before the organic indicators are validated.

**Takeaway:** on Robinhood Chain, roughly four in five swaps and over 40% of dollar volume in universe pools come from automated flow. Raw counts and raw volume overstate real activity by a large margin, which is the premise of SPEC §3.1.
