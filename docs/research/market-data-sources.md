# Market data sources: DexScreener and GeckoTerminal

Probed on 2026-11-17. Both are free, need no API key, and cover all five chains in scope, including Robinhood Chain (DexScreener `robinhood`, GeckoTerminal `robinhood`).

| | DexScreener | GeckoTerminal |
|---|---|---|
| Base URL | `https://api.dexscreener.com` | `https://api.geckoterminal.com/api/v2` |
| Rate limit | 300/min on token and pair endpoints; 60/min on profiles and boosts | about 30/min on the free tier |
| Chain ids | `solana`, `base`, `ethereum`, `bsc`, `robinhood` | `solana`, `base`, `eth`, `bsc`, `robinhood` |
| What we use | `/tokens/v1/{chain}/{up to 30 addresses}` for current pairs | `/networks/{net}/pools`, `new_pools`, `trending_pools` for discovery; `/pools/{pool}/ohlcv/day` for price history |
| History | None. Current state only. | Daily OHLCV for about the last 184 days (checked on SOL/USDC: 2026-05-18 to 2026-11-17). |
| Useful extras | Liquidity split by side, pair creation time | Unique buyers and sellers per window |

## Consequences for the build

1. **Liquidity and market cap have no free history.** Neither source publishes past liquidity or market cap. Our daily DexScreener and GeckoTerminal snapshots are therefore the point-in-time record of both from 2026-11-17 onward. The universe rule (market cap at least $1M and liquidity at least $50K) can only be evaluated from that date with these sources.
2. **Backfill before 2026-11-17 needs trade-level data.** Reconstructing past liquidity and market cap requires pool reserves and supply from Dune. That will be a separately versioned universe backfill, so the forward-observed universe is never mixed with a reconstructed one without a label.
3. **Price history is limited to six months for free.** GeckoTerminal daily candles reach back about 184 days. Older prices, which SPEC §6.1 asks for back to January 2024, also need Dune or a paid source. Any paid source needs Arthur's approval first.
4. **The current day's candle is incomplete** and is never stored.

## Robinhood Chain quote assets

The most frequent quote tokens in Robinhood pairs on 2026-11-17 were WETH (`0x0bd7…ad73`), native ETH (zero address) and the USDG stablecoin (`0x5fc5…1d168`). These are now tagged as quote assets. Tokenized stocks such as NVDA, TTWO and SPCX also appear as quote assets in some pairs. They belong to the RWA bucket and will be separated by the organic filters (SPEC §5.5), not by the quote-asset list.

## First run (2026-11-17)

The first live run registered 811 tokens (Solana 410, Robinhood 247, Ethereum 63, Base 46, BNB 45). DexScreener returned pairs for 587, and 110 pairs met the universe thresholds that day. GeckoTerminal rejected about 100 requests with 429 although the run averaged under 30 per minute: the limiter allowed bursts. The limiter now spaces calls evenly (now 15 per minute for GeckoTerminal; a second run at 20 per minute still drew 10 rejections out of 135) and backs off 10, 20, 40 and 80 seconds after a 429, since GeckoTerminal sends no Retry-After header. A paced test of 24 requests at 12 per minute had no rejections.
