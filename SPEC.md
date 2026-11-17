# Trench Research Site — Product and Research Spec

Status: handoff from the research review (Nov 17, 2026). This document is the source of truth for scope, indicator definitions, data sources and build order. The synthesis phase starts here: turn this into a repo plan, data pipelines, a backtest harness and pages.

---

## 1. Purpose and audience

We are building an onchain research website for active traders in memecoins and microcaps across Solana, Base, Ethereum, BNB Chain and Robinhood Chain. It improves on two existing products, TEHscreener (tehcscreener.com) and Sparsity (sparsitydata.com), and adds new indicators.

"Better" means decision-useful. After looking at any indicator, a reader should know what to do differently. Every headline output is a state with a base rate, not a raw number.

## 2. Scope decisions (made by Arthur)

**In scope**
- The eight rebuilt sections in §6.
- Public signal track record (§7.1).
- Attention versus flow (§7.2).

**Later**
- Telegram alert bot.
- Launch safety check, as a separate product.
- Our own heat map (Sparsity's was skipped as low-value).

**Out**
- Catalyst feed.
- Wallet labels as a user-facing product. Wallet tracking is crowded and copy-trade alpha decays. Entity clustering and labels still exist as internal plumbing because most indicators depend on them (§5.3).

**Chains (updated 2026-11-17)**
- BNB Chain is deferred by Arthur. It is not ingested or shown until re-enabled. BNB data already stored stays in history.

**Data posture**
- Use free public APIs where they fit, starting with TEHscreener's API (§4.1).
- Robinhood Chain has adequate third-party data providers. Do not build a custom indexer for it; identify and use the providers.

## 3. Design principles (apply to every indicator)

1. **Organic over raw.** Exclude stable-to-stable and LST swaps, atomic arbitrage, sandwiches, wash round-trips, bot clusters and spam launches. Counts (trades, launches, transactions) are not activity; use dollars and unique entities.
2. **Outcomes over inputs.** Prefer what happened to participants (graduation, survival, buyer PnL) over how busy a venue was.
3. **Point-in-time.** Store every published value as it was published. Never silently recompute history. Version formulas and mark methodology changes on charts.
4. **No look-ahead.** Cohort membership, skill rankings and normalization windows use only data available before the time being scored.
5. **Comparable over time.** Percentiles against trailing windows or a frozen, versioned calibration set. Chain-link aggregates when venues or chains are added so coverage changes do not create jumps.
6. **Full universe.** Rule-based inclusion, automatic, with dead coins kept in history. No hand-curated universes.
7. **Symmetric smoothing only.** No one-sided cooldowns. Publish raw values; if smoothing is needed, apply it equally in both directions. State changes require two consecutive confirming readings.
8. **Every signal has a validation plan and a drop rule** (§8). If it fails out of sample, it is shown as description only, without signal framing.
9. **One screen.** Each view answers its question above the fold: state, why, risk, levels, base rate, what would flip it.

## 4. Competitor reference

### 4.1 TEHscreener (tehcscreener.com)

Public API, our main free aggregate source.
- Base URL: `https://tehcscreener.com/api/v1`. JSON over GET, no API key, open CORS. Updates once a day. Docs: `https://tehcscreener.com/api`.
- Rate limit: 120 requests/min per IP (429 above that).
- Windows: `1d`, `7d`, `30d`, `all`, counted back from the response's `through` date, not today.
- v1 is additive-only (fields added, never renamed or removed).
- Endpoints:
  - `/launchpads`, `/launchpads/series` (daily volume, launches, protocol revenue per chain and pad), `/launchpads/{chain}/{pad}` (profile, daily totals, top 50 tokens; `tokens=traded|launched`), `/launchpads/{chain}/{project}/revenue`.
  - `/bots` (terminal volume, transactions, fees; group by `bot` or `chain`), `/bots/{bot}`, `/bots/{bot}/perps` (Hyperliquid perps; notional, excluded from `/bots`).
  - `/chains`, `/chains/{chain}` (`dex_volume_usd`, `dex_trades`, `active_wallets`).
  - `/dexes`, `/dexes/series`, `/dexes/{chain}/{dex}`, `/dexes/{chain}/{dex}/revenue` (DEX revenue is kept out of launchpad numbers).
  - `/rwa` (tokenized RWAs by chain and day).
  - `/trench` (composite score, includes a `method` block).
  - `/status` (latest sync).
- Field caveats:
  - `top_tokens[].onchain_mcap_usd` only for closed-curve pads.
  - `creator_revenue_usd` is null before per-trade measurement (Oct 2026).
  - `buyback_usd` is null where not tracked.
  - Bot `top_tokens` only include tokens that reached 25+ wallets on some day.
  - `wallets_dedup` is null where the source has no deduplicated count, so wallet counts are not comparable across sources.
- Underlying data: Allium.
- Terms: if we publish statistics or charts from it, credit "tehcscreener.com" as the source. **Open item:** confirm their terms permit commercial reuse.

Trench Index method (from the API docs):
- Composite 0–100 of launchpad volume 20%, new launches 10%, launchpad revenue 15%, terminal volume 30%, terminal fees 25%.
- Each input is percentile-ranked against trailing 90-day and 365-day windows, then blended (`method.blend` = `{short, long}`, values not documented).
- A day is scored once 30 days of history exist.
- Cooldown: drops decay by a factor per day; rises apply the same day.
- Nov 12, 2026: launchpad revenue added; weights changed from 35/20/25/20; history recomputed.
- Recorded 2026-11-17 (see `docs/research/tehcscreener-trench-method.md`): `blend` = short 0.6 / long 0.4; cooldown factor 0.65; bands ded 0–19, cold 20–39, active 40–59, hot 60–79, euphoric 80–100.

Weaknesses found in review (do not repeat):
- About 90% of Trench Index weight is one factor (dollar volume; fees and revenue are volume times a rate).
- USD volume carries base-asset beta.
- One-sided cooldown delays risk-off readings.
- History was recomputed.
- Venue additions cause jumps.
- Launch counts are spam: launches stayed in a 40–60K/day band while launchpad volume fell about 80% from early-Sep peak.
- Volume share across launchpads mixes closed-curve and graduating designs.
- Transaction counts are not comparable across chains.
- Terminal volume has no direction.
- Resolved 2026-11-17: pump.fun's launchpad volume excludes PumpSwap. A launchpad's own AMM is reported under `/dexes`, never `/launchpads`.

### 4.2 Sparsity (sparsitydata.com)

- No public API found. The site is account-based (alerts, accounts, refunds). Do not scrape it.
- Its stated sources are Dune and Mobula for onchain data and DEX Screener for market caps. We can build equivalent inputs from the same sources.
- Holder Strength: 4 areas, 9 metrics. Conviction 50% (drawdowns survived, supply held, fullported holders), Demand 25% (holder growth, whale accumulation, dip absorption), Market health 12.5% (holder concentration, liquidity for size), Relative strength 12.5%. Metrics are scored against an unnamed fixed reference. Universe: $2M+ market cap, $100K+ liquidity, 14+ days of trading, hand-reviewed requests, 63 coins. Holders exclude pools, contracts, exchanges, burn, locked supply and automated trading wallets, but not insider clusters. Holders are counted at $100+.
- Bottoming Test: three signs read in strict order (sellers capitulated at a deep loss; the low holding; demand returning with a higher share of new wallets), only while well below the 30-day high. Daily. Cost basis from Dune main-pool trades.
- Fear & Greed by chain: Activity 60% (launchpad trades 35%, new launches 20%, bot fees 45%), Holders 40% (holder growth 50%, large wallets adding 50%), each read against the chain's own year. Holders component spliced in on Sep 27, 2026.
- Net Flows: USD bought minus sold in main pools; whales $100K+, sharks $10K–100K, dolphins $1K–10K, fish under $1K, sized by the larger of start or end of week holding; market makers not separated.

Weaknesses found in review (do not repeat):
- Conviction rewards insider and static supply.
- "Drawdowns survived" rewards volatility, and current holders pass it by definition.
- The $100 holder threshold makes holder growth a price signal.
- One event scored in opposite directions across areas: whale accumulation +21 vs concentration −14.
- Bottoming states flip almost daily: SCHIFFY changed on 12 of 13 days, V4 on 9 of 13.
- "Price above the low" is near-circular.
- Strict ordering turns missing data into a negative reading.
- Fear & Greed on Solana mixed trade counts at the 74th percentile with bot fees at the 6.6th.
- All-wallet net flow in a pool roughly restates the price change.
- Size groups describe the trade, not the trader.
- Flows are not normalized by market cap.

What Sparsity does well, worth keeping:
- "What moved" attribution panels.
- Quality checks before publishing.
- Fixed-reference scoring idea.
- Peer context.
- Transparent definitions.
- Breadth counts.

## 5. Shared data layer

### 5.1 Sources (verify current limits and terms when wiring up)

| Source | Use |
|---|---|
| TEHscreener API | Daily launchpad, terminal, chain, DEX aggregates; history backfill; cross-checks |
| ~~Dune~~ (no free API; replaced 2026-11-17) | — |
| Google BigQuery public Solana dataset, Helius, Alchemy, public EVM RPCs, GeckoTerminal trades | Trade-level and wallet-level data; the core source for organic filters, cost basis, cohorts (see `docs/research/trade-data-sources.md`) |
| DefiLlama | DEX volume, bridge flows, stablecoin supply by chain |
| DexScreener, GeckoTerminal | Prices, liquidity, pools, OHLCV |
| Hyperliquid info API | Meme perp funding and open interest |
| Mobula (free tier) | Token and wallet data (also a Sparsity source) |
| Robinhood Chain providers | Identify existing providers; no custom indexer |
| Paid, only if needed and approved | Allium, Helius, Codex, Birdeye, X API (attention) |

### 5.2 Universe
- Rule-based: every token on covered chains with market cap ≥ $1M and liquidity ≥ $50K on any day (thresholds configurable).
- Tokens enter automatically and are never removed from history.
- The universe as of each date is stored point-in-time.

### 5.3 Entity and label plumbing (internal, not a product)
- **Entity clustering:** wallets merged by funding graph (common funders, same-block funding, sweep patterns).
- **Labels:**
  - DEPLOYER/INSIDER: deployer and funding-linked clusters, launch-block snipers linked to the creator.
  - BOT/MM: high frequency, two-sided, near-zero net inventory.
  - CEX: exchange hot and deposit wallets.
  - POOL/CONTRACT.
  - SMART: top-decile 90d realized PnL after fees, minimum trade count, measured only on data before the scoring time.
- **Venue segment** by terminal fee wallet or router: CONSUMER (fomo, pump.fun app, other mobile and social), PRO (Axiom, GMGN, Photon, Terminal, Padre, …), TG-BOT (Trojan, Maestro, Bonkbot, Basedbot, …).

### 5.4 Cost basis engine
- Per-entity FIFO cost basis per token from swaps, with transfer handling (transfers carry basis between clustered wallets; unclustered transfers in reset basis to market price at receipt).
- Outputs:
  - Realized and unrealized PnL per entity.
  - Supply distribution by acquisition price.
  - Market-level profit/loss realization (mSOPR).

### 5.5 Organic filters
- Exclude stable↔stable, LST and wrapped pairs, atomic arbitrage (net zero position within a transaction), sandwiches, same-block round trips, wallets above N swaps per minute, and BOT/MM entities.
- Volume deflated by base-asset price where noted.
- Volume split into buckets: memecoin / majors / RWA.

### 5.6 Point-in-time store
- Every published metric is written append-only with: value, formula version, input data cutoff, publish timestamp.
- Charts read published values. Backtests read published values or recompute strictly as-of.

## 6. Indicator suite

Three layers: market regime, chain and venue, token. Formulas below are the MVP unless marked "institutional".

### 6.1 Trench Regime (replaces TEHscreener Trench Index and Sparsity Fear & Greed)

Two readings per chain and aggregated across chains.

**Activity** (how busy, in real terms):
```
P_t = unique organic buying entities (launchpads + terminals)
V_t = organic DEX volume, native units / base-asset price deflated
Q_t = graduation rate × 7d survival rate of launches (see 6.3)
R_t = share of last-7d graduated tokens trading above graduation price

s_i,t     = PctRank(log X_i,t ; trailing 365d) × 100
Activity_t = mean(s_P, s_V, s_Q, s_R)                  equal weights
Trend_t    = Activity_t − Activity_(t−7)
```
- Chain-link aggregates when venues are added:
  `I_t = I_(t−1) × Σ_(v∈common) x_v,t / Σ_(v∈common) x_v,t−1`.
- Publish only after 180 days of history. Backfill to Jan 2024 where data allows.

**Sentiment** (how much risk participants take):
```
mSOPR      = Σ organic sell value / Σ cost basis of tokens sold   (>1 greed, <1 fear)
Urgency    = median priority fee / tip per swap
FreshShare = share of buys from entities < 7 days old
ConsumerNF = net flow from CONSUMER segment
RunnerRate = share of last-7d launches reaching $1M market cap

Sentiment_t = mean of trailing-365d percentiles of the five inputs
```
- MVP: mSOPR, FreshShare, RunnerRate.
- **Regime:** Activity (hot/cold) × Sentiment (greed/fear), with a 2-day confirmation before the state changes.
- **Display:** state plus one-line base rate, component contribution bars, plain-language divergence callouts (for example, "trade counts high, dollars at year low: activity is bot-heavy").
- **Alerts:** confirmed regime change; mSOPR crossing below 1; count-vs-dollar divergence.

### 6.2 Chain Rotation Monitor (replaces Chain Stats)
```
OV_c,t  = organic DEX volume by chain, by bucket
OW_c,t  = unique organic trading entities
S_c,t   = OV_c,t / Σ_c OV_c,t
VPW_c,t = OV_c,t / OW_c,t           flag if > 3 MAD above own 90d median (wash)
Z_c,t   = (log OV_c,t − median_90d) / MAD_90d

RS-Ratio_c,t    = 100 × EMA_5(S_c,t) / mean(S_c, t−29…t)
RS-Momentum_c,t = 100 × RS-Ratio_c,t / RS-Ratio_c,t−7
Quadrants: Leading (>100, >100), Weakening (>100, <100),
           Lagging (<100, <100), Improving (<100, >100)
```
- Drop the raw transaction-count chart.
- Default to 100% stacked share. Use indexed or small-multiple lines for wallets.
- Include BNB and Ethereum alongside the other covered chains.

### 6.3 Launchpad Scorecard (improves Launchpad War)

Per pad *p* and daily launch cohort *d*:
```
L*     = launches with ≥10 unique non-creator buyers in the first 60 min
Grad   = reached $100K market cap within 24h / L*     (uniform milestone)
Surv7  = market cap ≥ $50K and liquidity ≥ $10K at day 7 / L*
Runner = peak market cap ≥ $1M within 7d / L*
Rug    = creator cluster sold ≥ 50% of its supply within 60 min / L*
BuyRet = median over tokens of (P_24h / VWAP_first60m − 1)
Take   = protocol revenue / organic volume

Rates shrunk to the cross-pad mean: (k + α) / (n + α + β), beta-binomial
prior fitted on pooled history; rolling 7-day cohorts.
LQS_p  = mean cross-pad percentile of {Grad, Surv7, Runner, 1−Rug, BuyRet}
```
- Keep the 100% volume share chart, using organic volume split into curve vs post-graduation.
- Show volume per launch and average trade size.
- Leaderboard sorted by LQS. Funnel per pad: launched → organic → graduated → survived 7d → $1M.
- Institutional: launch-block bundler and sniper detection, deployer history.

### 6.4 Retail Flow Desk (replaces Trading Terminals; industry charts move to a secondary tab)

Market level:
```
ConsumerShare_t = Vol_CONSUMER,t / Vol_ALL,t ;  CS_z = robust z vs 90d
AvgTicket_s,t   = Vol_s,t / Trades_s,t
TopTokenShare_t = Vol_top1,t / Vol_ALL,t
HHI_t           = Σ_i (Vol_i,t / Vol_ALL,t)²
```
Token level, hourly (windows 1h, 4h, 24h):
```
NF_s,i,w = buy USD − sell USD by segment s (CONSUMER / PRO / TG-BOT)
UB_i,1h  = unique terminal buyers last hour
Accel_i  = UB_i,1h / mean(UB_i,1h over prior 6h)

DISTRIBUTION : NF_PRO < 0 and NF_CONSUMER > 0, |NF_PRO| ≥ 10% of volume
ACCUMULATION : NF_PRO > 0 and NF_CONSUMER ≤ 0
RETAIL CHASE : Accel ≥ 3 and CONSUMER share of buys ≥ 60%
```
- Institutional: replace segment-based cohorts with identity cohorts from §6.7 (SMART, INSIDER, NEW).
- Main view: live "Retail flow now" table (age, market cap, liquidity, unique buyers and acceleration, flows by segment, flag, median buyer PnL).
- Replace the unlabeled top-token chart with a top-10 attention leaderboard plus the concentration line.

### 6.5 Coin page: Quality × Flow (improves Holder Strength)

All holder metrics are computed on entity-clustered holders, excluding INSIDER, BOT/MM, CEX and POOL.
```
QUALITY (slow)
StressHold   = depth-weighted mean over last K drawdowns ≥30% of
               (supply held by same non-insider entities at trough / at peak)
Tenure       = supply-weighted median holding age
Breadth      = Δ entities holding ≥ 0.001% of supply (price-neutral)
InsiderShare = supply in INSIDER clusters (lower is better)
ExitCover    = DEX depth within 5% impact / value of top-10 non-insider positions

FLOW (fast)
SmartNF   = 7d SMART net flow
NewHold   = 7d net new non-insider entities above threshold
WhaleΔ    = Δ supply share of top-20 non-insider entities
DipAbsorb = organic buy / sell volume on down days

Q = mean percentile of {StressHold, Tenure, Breadth, 1−InsiderShare, ExitCover}
F = mean z-score of {SmartNF, NewHold, WhaleΔ, DipAbsorb}
States: Accumulation (high Q, F>0), Distribution risk (high Q, F<0),
        Speculative bid (low Q, F>0), Avoid (low Q, F<0)
```
- Percentiles against a frozen, versioned calibration set.
- One-screen card:
  ```
  NAME · market cap · chain / launchpad
  SETUP: <state>   Quality NN (#rank)   Flow ±Nσ   (changed from X, N days ago)
  Why     top three drivers in one sentence
  Risk    insider share · exit cover · open drawdown
  Levels  cost-basis overhang (resistance) · support
  Odds    coins in this state: median 14d return, P(−50% in 30d), n
  Flips   explicit conditions that would change the state
  ```
- Below the fold:
  - One price chart shaded by state.
  - Metric table with value, score and 7d change; keep Sparsity-style "What moved" attribution.
  - Drawdown table; three peer rows.
- Remove duplicate charts, flat single-series charts and rank spaghetti charts.

### 6.6 Bottom Probability (replaces Bottoming Test)

For tokens ≥50% below their 90-day high.
- Label (triple barrier): enter at the next day's open. Upper barrier +50%, lower barrier 25% below the drawdown low, time barrier 30 days.
- Features:
  ```
  LossSellShare = sell vol at > 50% loss vs cost basis / sell vol during drawdown
  Exhaustion    = realized loss last 3d / peak 3d realized loss
  DaysSinceLow, Retests (touches within 10% of the low that held),
  RangeComp     = ATR_7 / ATR_30,  HigherLow
  OrgNF_z, NewWallet_z, SmartNF
  InsiderLeft, ExitCover
  Regime (from 6.1), chain rotation state (from 6.2)
  ```
- MVP: logistic regression with isotonic calibration on the point-in-time universe including dead coins.
- Institutional: gradient boosting with monotonic constraints and a regime interaction.
- Headline state changes only after the probability crosses the threshold for two consecutive days. Signals are shown as continuous values.
- Per-coin line: P(target before stop) vs base rate, days in state, stop level, first cost-basis resistance, reward/risk, max size at 2% impact.

### 6.7 Cohort Flow (improves Net Flows; data layer for 6.4–6.6)

Cohort membership is fixed at window start and computed on entities:
```
INSIDER, SMART, WHALE (≥ 0.5% of supply at start), RETAIL, NEW (zero balance at start), BOT/MM

NF_c,i,w  = USD bought − sold, all pools including aggregator routes
NFn_c,i,w = NF_c,i,w / market cap at window start   (bps)
Z_c,i,w   = NFn vs the token's own 90d history for that cohort
AccumScore_i = z(SMART) + z(WHALE) − z(INSIDER selling)
```
- Rank by AccumScore, never raw USD.
- Index line: SMART net buying breadth (share of coins with positive 7d SMART flow).

### 6.8 Additional indicators from the review (build after the MVP of each parent)
- **Fresh-wallet inflow:** share of buyers < 7d old funded from a CEX.
- **Trench PnL:** median PnL of wallets that bought last-7d launches.
- **Organic ratio:** organic / total volume per venue.
- **Net capital inflow by chain:** bridges + CEX + stablecoin supply.
- **Wallet migration matrix** (EVM same-address).
- **Urgency index:** priority fees and tips.
- **Sniper share:** % of supply bought in the first two blocks by creator-linked entities.
- **Serial-deployer concentration.**
- **Pad token valuation:** annualized revenue, buyback yield, P/Rev.
- **Copy-trade echo ratio.**
- **Attention half-life and lateness.**
- **PnL by terminal user base.**
- **Cost-basis map:** supply by acquisition price; share of supply in profit; overhang levels.
- **Dormant supply wake-up alert.**
- **Holder rotation:** where a coin's holders are buying and selling.
- **Bottoming breadth.**
- **Second-leg risk:** unsold insider and dormant supply / liquidity.
- **Dev re-entry / community takeover detector.**
- **Meme perp positioning:** Hyperliquid funding and open interest.
- **Capitulation breadth.**
- **Cross-chain sentiment spread.**
- **Absorption ratio:** who buys insider and whale selling, NEW vs SMART.
- **Whale profit cushion.**
- **Smart-flow breadth.**

## 7. Additions approved by Arthur

### 7.1 Public signal track record
- Every flag and state change (regime, rotation quadrant, coin setup state, flow flags, bottom probability crossings) is logged at issue time, append-only, with formula version and input cutoff.
- Outcomes computed automatically at 1d, 7d, 14d and 30d horizons, after an assumed cost of 2–4% round trip for microcaps.
- A public page per signal shows: count, hit rate, median and mean forward return, calibration (for probabilistic outputs), and a downloadable log.
- Never edit past entries.

### 7.2 Attention versus flow
```
Att_i,t  = unique authors mentioning the cashtag or contract (KOL-weighted), last 6h
AttZ_i   = z of Att vs the token's own 7d history
FlowZ_i  = z(SMART + WHALE net flow) from 6.7

HYPE WITHOUT FLOW : AttZ ≥ 2 and FlowZ ≤ 0       (likely distribution)
QUIET ACCUMULATION: AttZ ≤ 0.5 and FlowZ ≥ 2
CONFIRMED         : AttZ ≥ 2 and FlowZ ≥ 2
```
- Data: X API (cost decision needed) or a cheaper social-data provider.
- Validate like 6.4.

## 8. Validation harness (shared)

- **Universe:** point-in-time, dead coins included.
- **Splits:** walk-forward, monthly out-of-sample.
- **Costs:** 2–4% round trip for microcap token signals; slippage modeled from liquidity.
- **Metrics:**
  - Rank IC.
  - Quintile/decile spreads.
  - Hit rate.
  - Event studies against matched controls (same market cap, age and volume bucket).
  - Brier score and calibration curves for probabilities.
  - AUC vs base rate.
  - Signal stability: median days per state should be ≥ 5 for state outputs.
- **Statistics:** non-overlapping or block-bootstrapped samples; Newey-West errors for overlapping horizons; clustered errors for small cross-sections (chains, pads).
- **Placebo tests:** rerun competitor methods on simulated random trades to measure artifacts. Do this for size-based net flow grouping in particular.

**Drop rules**

| Indicator | Drop signal framing if |
|---|---|
| Trench Regime | Extremes and quadrants do not separate forward basket returns |
| Chain Rotation | Share changes show no persistence beyond 1 week and quadrants do not separate forward relative returns |
| Launchpad Scorecard | LQS week-to-week autocorrelation ≈ 0 and no link to next cohort outcomes |
| Flow flags | Flagged vs control return spread not significant in ≥ 3 out-of-sample months after costs |
| Quality | Does not reduce crash probability out of sample |
| Flow | Rank IC after costs indistinguishable from zero |
| Bottom Probability | Out-of-sample AUC < 0.55 or does not beat the base rate after costs |
| Cohort Flow | No cohort beats zero IC out of sample |

## 9. Pages

1. **Landing:** Trench Regime per chain (Activity × Sentiment matrix, state plus base rate), chain rotation graph, smart-flow breadth, links to the track record.
2. **Launchpads:** Scorecard leaderboard, funnels, share chart, pad detail.
3. **Flow Desk:** market strip (consumer share, concentration, unique traders) and live token flow table with flags.
4. **Coin page:** one-screen Quality × Flow card, Bottom Probability block when in drawdown, cohort flow panel, cost-basis map.
5. **Bottoms:** probability-vs-depth map (bubble size = liquidity) and table with stop, target, size.
6. **Track record:** per-signal performance and logs.
7. **Methodology:** versioned formulas, data sources, validation results, change log.
8. **Terminal industry** (secondary): terminal share, fees, take rate.

## 10. Build phases

- **Phase 0 — Foundation:**
  - Repo, storage (point-in-time, append-only), scheduler.
  - TEHscreener API ingestion and backfill.
  - Trade-level ingestion for Solana launchpads and DEXes first (BigQuery token transfers + Helius), then Base, BNB and Ethereum (RPC Swap logs) and Robinhood Chain (Alchemy RPC, GeckoTerminal trades). Dune was dropped on 2026-11-17: no free API.
  - Price and liquidity from DexScreener/GeckoTerminal.
  - Universe builder.
- **Phase 1 — Market layer MVP:**
  - Organic filters.
  - Trench Regime (Activity + Sentiment MVP inputs).
  - Chain Rotation Monitor.
  - Launchpad Scorecard (spam filter, per-launch ratios, Grad/Surv7/Runner).
- **Phase 2 — Token layer MVP:**
  - Entity clustering (deployer funding first).
  - Cost basis engine.
  - Cohort Flow.
  - Coin page Quality × Flow.
  - Bottom Probability MVP.
- **Phase 3 — Validation and trust:**
  - Validation harness.
  - Public track record.
  - Methodology pages.
  - Retail Flow Desk hourly.
  - Attention vs flow.
- **Later:**
  - Institutional versions (SMART cohorts everywhere, full MEV classification, intraday).
  - Telegram bot.
  - Launch safety product.
  - Our own heat map.

## 11. Open items

1. TEHscreener: confirm commercial-use terms. The docs say only "free to use; credit tehcscreener.com when publishing". (The `method` block was recorded on 2026-11-17.)
2. ~~TEHscreener: whether pump.fun launchpad volume includes PumpSwap.~~ Resolved 2026-11-17: it does not.
3. Robinhood Chain: choose data providers and confirm coverage of launchpads (PonsFamily, Long, Flap) and terminals.
4. Social data source and budget for attention vs flow.
5. Paid data approvals (Allium, Helius, Codex, Birdeye) only if free sources prove insufficient.
6. Site name and brand. Visual direction v0 is drafted in `docs/design/DESIGN.md` (Sparsity-like density and structure; institutional navy and slate palette; no gold) and awaits Arthur's review.
