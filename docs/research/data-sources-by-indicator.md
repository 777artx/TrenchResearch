# Existing data sources, indicator by indicator (2026-11-19)

Question from Arthur: for each indicator, where can existing data be pulled instead of built? Findings from a web survey on 2026-11-19. Free-tier limits change often and several sources disagree; every limit below must be confirmed on the provider's own page before we depend on it. Paid options need Arthur's approval (CLAUDE.md).

**General finding.** No provider publishes the indicators themselves in the form SPEC.md requires (organic, point-in-time, with base rates and a track record). What exists are ingredients: wallet labels, sniper and bundler flags, holder lists, decoded trades, perps funding. Where we use a provider's derived label (for example "smart money" or "sniper"), it becomes an input we store point in time and validate, not a replacement for our own definition.

## Already in use (free)

| Source | Gives us |
|---|---|
| tehcscreener.com | Launchpad, terminal, chain and DEX daily aggregates |
| DefiLlama (`api.llama.fi`, `coins.llama.fi`) | Chain DEX volume, ETH and SOL prices |
| GeckoTerminal | Pools, daily OHLCV (~6 months), last 300 trades per pool with wallet |
| DexScreener | Current pair price, liquidity, market cap |
| Robinhood public RPC, publicnode (Base, Ethereum) | Complete swap and launch history from logs |
| Helius (free plan) | Solana RPC and decoded transactions, ~1M credits a month |

## Indicator by indicator

| Indicator | Existing source that helps | Free? | Verdict |
|---|---|---|---|
| Trench Regime: Activity | DefiLlama, TEHscreener (in use); our organic EVM swaps | Yes | Keep building ourselves; inputs exist |
| Trench Regime: Sentiment (mSOPR, fresh wallets, runner rate) | Mobula wallet PnL endpoints for cost basis cross-checks; our cost-basis engine | Mobula free tier ~10K credits a month (official page) | Build ourselves; Mobula only for spot checks |
| Chain Rotation | DefiLlama (in use); Artemis/Token Terminal for chain metrics (not verified free) | Yes | Done (raw); organic version from our data |
| Launchpad Scorecard | Our on-chain pipeline; TEHscreener launch counts as cross-check; Solana Tracker / Mobula sniper and bundler flags | Solana Tracker free: 2,500 requests a month | Build ourselves; Solana pads need paid data |
| Retail Flow Desk (terminal segments) | TEHscreener terminal volumes and fees; terminal fee wallets identifiable on chain | Yes | Build ourselves from swaps + fee-wallet list |
| Cohort Flow (SMART, WHALE, INSIDER, NEW) | Birdeye "smart money" token list (now Solana + EVM); CabalSpy KOL / smart-money wallet lists; Nansen labels; Cielo | Birdeye free ~30K compute units a month (third-party figure); CabalSpy claims 10K credits free; Nansen API mostly paid | Use one free label list as a cross-check; SMART defined by our own PnL ranking (SPEC §5.3) |
| Coin page: Quality × Flow | Holder lists: Helius DAS (Solana), Mobula holders with sniper share; GoPlus token security (EVM: holders, owner, honeypot flags) | GoPlus described as free, no key for basic calls (verify) | Build ourselves; GoPlus + Helius as inputs |
| Bottom Probability | Our trades and cost basis; GeckoTerminal OHLCV | Yes | Build ourselves |
| Cost-basis map | Mobula wallet trade history; our swaps | Partly | Build ourselves (EVM now; Solana needs trade data) |
| Attention vs Flow | Chainbase Tops public tool: X mentions search, no key, 600 requests an hour (verify terms); LunarCrush (social endpoints paid); X API (paid); Apify cashtag scrapers (paid, unreliable) | Chainbase free | Prototype with Chainbase; a reliable feed needs a paid decision |
| Public track record | Ours (point-in-time store) | — | Build ourselves |
| Organic filter | Ours; Dune spellbook CEX and label seed files (open source on GitHub) for CEX/bridge/router labels | Yes (open source) | Add spellbook seed files as label inputs |

## Additional indicators (SPEC §6.8)

| Indicator | Existing source |
|---|---|
| Fresh-wallet inflow (new wallets funded from CEX) | Dune spellbook CEX address seeds (open source) + our transfer data |
| Trench PnL | Ours (launch cohorts) |
| Organic ratio per venue | Ours |
| Net capital inflow by chain | DefiLlama bridges and stablecoins endpoints (free) |
| Wallet migration matrix (EVM) | Ours (same-address across chains) |
| Urgency index (priority fees, tips) | Helius / Robinhood RPC block data; not available pre-aggregated for free |
| Sniper share | RugCheck API (Solana, insider networks; free read access per third-party docs), Solana Tracker risk object (sniper/insider/bundler fields), Mobula holder sniper fields, our launch-block buyers (EVM) |
| Serial-deployer concentration | Ours (already measured in the scorecard) |
| Pad token valuation (revenue, buybacks, P/Rev) | TEHscreener revenue and buyback fields; DefiLlama fees/revenue |
| Copy-trade echo ratio | Ours (needs labelled leader wallets: CabalSpy/Birdeye lists) |
| Attention half-life and lateness | Same as Attention vs Flow |
| PnL by terminal user base | Ours + terminal fee-wallet list |
| Dormant supply wake-up | Ours (transfers) |
| Holder rotation | Ours |
| Bottoming / capitulation / smart-flow breadth | Ours (aggregates of coin-level outputs) |
| Second-leg risk | Ours + holder lists |
| Dev re-entry / community takeover | Ours (creator-linked wallets) |
| Meme perp positioning | Hyperliquid info API (free, no key): funding, open interest |
| Cross-chain sentiment spread | Ours |
| Absorption ratio, whale profit cushion | Ours |

## The Solana gap

Free Solana trade feeds remain thin: PumpPortal's trade stream became paid per trade in 2026 (third-party report), PumpDev's WebSocket is free but live-only (needs an always-on host), Solana Tracker's free plan is 2,500 requests a month, Bitquery has only a 7-day trial. Full Solana trade history therefore still requires either an always-on collector or a paid plan.

## Not to use

- Sparsity: no public API; do not scrape (CLAUDE.md).
- GMGN: no public API found; scraping its site is not an approved data source.
