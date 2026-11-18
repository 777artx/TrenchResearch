# Organic filter v1 on EVM swaps (2026-11-17)

Rules are defined in `src/trench/organic.py`: atomic arbitrage, sandwiches, same-block round trips, high frequency (more than N swaps in any 60 seconds) and two-sided near-zero-inventory BOT/MM flow.

## First measurement: Robinhood Chain, 6 hours (2026-11-17 16:50–22:50 UTC), 44 universe pools, 19,770 swaps

> **Correction (2026-11-18).** The first version of this report said about 80% of swaps and over 40% of dollar volume were automated. That was wrong. Robinhood's public RPC returns `blockTimestamp = 0x0` in its logs, so every swap carried the same time, and the high-frequency rule flagged every wallet with more than five swaps in the whole six hours. Timestamps now come from the blocks themselves (`evm_block_ts`), a zero timestamp is treated as missing, and the filter refuses swaps without a real time. The figures below replace the earlier ones.

Block times are exact for anchor blocks every 2,000 blocks and linearly interpolated in between. Against exact times for 40 random blocks, the interpolation error was median 0 s and at most 10 s.

Sensitivity to the high-frequency threshold N, which SPEC §5.5 leaves open:

| N (swaps per minute) | Organic share of swaps | Organic share of USD volume | Organic traders |
|---|---|---|---|
| 3 | 47.1% | 78.8% | 2,814 of 2,947 |
| 5 (chosen) | 54.1% | 82.9% | 2,884 of 2,947 |
| 10 | 58.5% | 84.3% | 2,905 of 2,947 |

At N = 5: organic 10,691 swaps; high frequency 7,731; BOT/MM 897; atomic arbitrage 449; same-block round trips 2. USD values were available for 67% of swaps (quotes in ETH, WETH or USDG).

**Takeaway:** on Robinhood Chain universe pools, automated flow makes up close to half of all swaps but only about a sixth of dollar volume. Raw trade counts overstate activity roughly twofold; raw dollar volume overstates it by about a fifth. A small number of wallets account for most automated swaps: the most active made 405 to 2,068 swaps each in six hours, each on a single token, with buys close to half their swaps.

## Swap decoding check against GeckoTerminal

On 416 Robinhood swaps present in both our RPC-decoded data and GeckoTerminal's trade feed (same transaction and token), the buy/sell direction agrees on 98.3%: 99.4% for Uniswap V4 and 93.7% for V3-style pools. Remaining disagreements are expected in transactions holding several swaps of the same token (arbitrage), where the two sources can pick different legs; those transactions are flagged as `atomic_arb` by the filter in any case.
