# Indicator reference

Every indicator in SPEC.md, explained: the question it answers, the data it uses, how it is measured, what it outputs, how it is tested, and where it stands (20 Nov 2026). Formulas are the MVP definitions from SPEC.md §6–7; where the running version (formula `0`) differs, the difference is stated.

**Rules that apply to every indicator**

- **Organic only.** Bots, arbitrage, sandwiches, wash trades and spam launches are removed before anything is computed (see "Organic filter").
- **No look-ahead.** A value for day *t* uses only data known before *t*. Each indicator has a test for this.
- **Point in time.** Every published value is stored with its formula version, input cutoff and publish time, and is never overwritten. Corrections are new rows with a stated reason.
- **Two confirming readings.** A state (hot/cold, a quadrant, a setup) changes only after two consecutive readings agree. No one-sided cooldowns.
- **Status.** Each indicator is a *Signal* (passed its backtest out of sample), *Description only* (failed it) or *Not yet validated* (too little history to test).

Terms used below: *percentile* = where today's value ranks against a past window (0 = lowest, 100 = highest); *z-score* = how many typical deviations today's value is from its usual level; *bps* = basis points, hundredths of a percent; *L\** = launches with at least 10 different non-creator buyers in their first hour.

---

## Part 1: Foundation (used by every indicator)

### 1. Organic filter
- **Question:** Which trades are real people trading, and which are machines?
- **Data:** Every swap with its wallet: Robinhood, Base and Ethereum from the chain (public RPCs); Solana from GMGN's trade feed and its wallet tags.
- **Measured as:** A swap is removed if any rule matches, in this order:
  1. *Atomic arbitrage:* the same wallet buys and sells the token inside one transaction.
  2. *Sandwich:* in one pool and block, a wallet trades just before and just after someone else, in opposite directions.
  3. *Same-block round trip:* the same wallet buys and sells the token in one block across separate transactions.
  4. *High frequency:* the wallet made more than 5 swaps within any 60 seconds that day.
  5. *Bot/market maker:* on a token and day, at least 10 swaps, each side at least 30% of them, and a net position under 10% of gross.
  On Solana, GMGN's `sandwich_bot` and `bundler` tags are also removed.
- **Output:** Every swap labelled organic or with its removal reason; the organic share by chain (see "Organic ratio").
- **Status:** Working. Robinhood and Base verified (buy/sell direction matches GeckoTerminal on 98.3% of shared swaps). The 5-per-minute threshold will be calibrated against a labelled bot list.

### 2. Cost basis engine
- **Question:** What did each holder pay for what they hold?
- **Data:** Organic and all swaps per wallet (EVM chains); GMGN holder records with each holder's cost (Solana).
- **Measured as:** First-in, first-out per wallet and token: each buy adds a lot (amount, price); each sell uses up the oldest lots first. Realised profit = sale value − cost of the lots used. Transfers between wallets of the same owner carry their cost; tokens received from strangers are valued at the market price on arrival.
- **Output:** Realised and unrealised profit per wallet; supply at each purchase price; the profit-taking ratio (mSOPR) for Sentiment.
- **Status:** v0 running. On EVM chains the cost is only known for tokens bought since collection began (days), so most sells have no known cost yet; on Solana GMGN supplies cost directly.

### 3. Wallet clustering and labels (internal only)
- **Question:** Which wallets belong to the same person, and what kind of wallet is each?
- **Measured as:** Wallets funded by the same source, in the same block, or swept to the same address are merged. Labels: *insider* (deployer and wallets it funded, launch-block buyers linked to it), *bot/market maker* (high-frequency, two-sided, near-zero inventory), *exchange* (known exchange addresses, from Dune's open-source label files), *pool/contract*, and *smart* (top 10% by 90-day realised profit after fees, with a minimum number of trades, using only data before the date being scored).
- **Status:** Partly in place: GMGN tags give insider (creator, dev team, sniper, bundler) and smart-wallet rankings on Solana. Our own funding-graph clustering is not built yet.

### 4. Universe
- **Question:** Which coins count?
- **Measured as:** Any token on a covered chain that has had a market cap of at least $1M and liquidity of at least $50K on some day enters on that day and never leaves (dead coins stay in history). Stablecoins, wrapped majors and tokenized stocks are tagged into their own buckets.
- **Status:** Running daily. 355 entries so far (BNB entries stored but not read).

---

## Part 2: Market level

### 5. Trench Regime: Activity
- **Question:** How busy is each chain, in real terms, against its own past year?
- **Inputs:**
  - *P* = unique organic buying wallets (launchpads and terminals)
  - *V* = organic DEX volume, divided by the chain's base-asset price (SOL or ETH) so a price rally does not look like more activity
  - *Q* = graduation rate × 7-day survival rate of launches (from the Launchpad Scorecard)
  - *R* = share of last week's graduated tokens trading above their graduation price
- **Measured as:** Each input's log value is ranked against the trailing 365 days (percentile 0–100). Activity = the average of the four percentiles. Trend = Activity today − Activity 7 days ago. State: *hot* at 50 or above, *cold* below, confirmed by two readings. Chains added mid-history are chain-linked so their arrival does not jump the totals. Published only after 180 days of history.
- **Output:** 0–100 score, hot/cold, 7-day trend, and a plain-language callout when inputs disagree (for example "dollars high, wallets low: activity is likely bot-heavy").
- **Running version (0-raw):** V = DefiLlama total DEX volume (not organic, includes stablecoins and majors); P = TEHscreener active wallets (not organic, from April 2026, no Ethereum); Q and R not yet available.
- **Test (drop rule):** Do extreme readings and regime quadrants separate the next 14 days' returns? **Failed** on the raw version (2023–2026: top fifth vs bottom fifth +3.8%, interval −3.6% to +12.4%; states lasted a median 4 days, below the 5-day minimum). **Description only.** The organic version is tested once it has history.

### 6. Trench Regime: Sentiment
- **Question:** Are participants taking profits or selling at a loss, and are they taking risk?
- **Inputs:**
  - *mSOPR* = Σ organic sale value ÷ Σ cost basis of the tokens sold (above 1: selling at a profit, greed; below 1: selling at a loss, fear)
  - *Urgency* = median priority fee or tip per swap
  - *FreshShare* = share of buys from wallets less than 7 days old
  - *ConsumerNF* = net buying from consumer apps
  - *RunnerRate* = share of last week's launches reaching $1M market cap
- **Measured as:** Each input ranked against its trailing 365 days; Sentiment = average percentile (MVP: mSOPR, FreshShare, RunnerRate).
- **Output:** 0–100, greed/fear.
- **Running version:** mSOPR per chain-day from FIFO cost basis on organic sells whose cost is fully known (Robinhood 1.008, Base 0.999). Percentiles need a year of history.
- **Test:** Same drop rule as Activity. **Not yet validated.**

### 7. Regime state
- **Question:** One-line state of each chain.
- **Measured as:** Activity (hot/cold) × Sentiment (greed/fear) → four states, changed only after two confirming days. Shown with its base rate ("chains in this state saw median basket return X over 14 days, n = N").
- **Alerts:** confirmed regime change; mSOPR crossing below 1; trade-count vs dollar divergence.
- **Status:** Waiting for Sentiment percentiles (about 180 days of organic mSOPR).

### 8. Chain Rotation Monitor
- **Question:** Which chains are gaining or losing their share of organic trading?
- **Inputs:** OV = organic DEX volume by chain (and by bucket: memecoin, majors, RWA); OW = unique organic trading wallets.
- **Measured as:**
  - Share S = a chain's volume ÷ all covered chains' volume.
  - RS-Ratio = 100 × (5-day moving average of S) ÷ (30-day average of S).
  - RS-Momentum = 100 × RS-Ratio today ÷ RS-Ratio 7 days ago.
  - Quadrant: Leading (both above 100), Weakening (ratio above, momentum below), Lagging (both below), Improving (ratio below, momentum above). Confirmed by two readings.
  - Wash check: volume per wallet more than 3 deviations above its 90-day median is flagged.
- **Output:** Quadrant per chain, share table, wallet trends.
- **Running version (0-raw):** DefiLlama total DEX volume.
- **Test:** Do share changes persist beyond one week, and do quadrants separate forward relative returns? **Failed** on the raw version (505 chain-weeks): shares mean-revert; Leading underperformed Lagging by 9.8% over 14 days. **Description only.** A contrarian reading is a hypothesis to test on the organic version.

### 9. Launchpad Scorecard
- **Question:** Which launchpads' launches actually work out for buyers?
- **Data:** Every launch from the launchpad's own contract, its pool or bonding curve, and every trade for 7 days (Robinhood: Long.xyz, PonsFamily; to add: Flap, thestonks on Base). Solana pads: daily totals only (TEHscreener).
- **Measured as**, per launchpad and daily cohort of launches:
  - L\* = launches with 10+ different non-creator buyers in the first 60 minutes (the spam filter)
  - Grad = reached $100K market cap within 24 h ÷ L\*
  - Surv7 = market cap ≥ $50K and liquidity ≥ $10K at day 7 ÷ L\*
  - Runner = peak market cap ≥ $1M within 7 days ÷ L\*
  - Rug = creator sold ≥ 50% of its supply within 60 minutes ÷ L\*
  - BuyRet = median of (price at 24 h ÷ average first-hour buy price − 1)
  - Take = protocol revenue ÷ organic volume
  - Rates are shrunk toward the cross-launchpad average (beta-binomial: (k + α) ÷ (n + α + β)), so a pad with 3 launches cannot look perfect by luck.
  - LQS = average cross-launchpad percentile of Grad, Surv7, Runner, 1 − Rug and BuyRet, on rolling 7-day cohorts.
- **Output:** Leaderboard by LQS, a funnel per pad (launched → real → $100K → alive at day 7 → $1M), volume share split between curve and post-graduation.
- **Running version (0):** daily UTC cohorts for Long.xyz and PonsFamily. Rug is measured against the creator's own first-hour buys; Surv7 omits the liquidity condition for V4 pools; Long.xyz quote prices are current, not daily.
- **Test:** Does LQS persist week to week, and does it predict the next cohort's outcomes? **Not yet validated:** needs 4+ pads and 4+ weekly cohorts. Not ranked until then.

---

## Part 3: Flow (who is trading)

### 10. Retail Flow Desk
- **Question:** Are retail traders buying what professionals are selling, or the other way round?
- **Segments by trading app:** consumer (fomo, pump.fun app), pro (Axiom, GMGN, Photon, Padre, Terminal, BullX), Telegram bots (Trojan, Maestro, Bonkbot, Basedbot).
- **Market level, daily:** ConsumerShare = consumer-app volume ÷ all terminal volume, with its z-score against 90 days; average ticket per segment = volume ÷ trades; TopTokenShare and concentration (HHI = sum of squared volume shares).
- **Token level, hourly (windows 1 h, 4 h, 24 h):** net flow per segment = buys − sells in USD; unique buyers in the last hour and acceleration = this hour's unique buyers ÷ the average of the prior 6 hours. Flags:
  - DISTRIBUTION: pros net selling, consumers net buying, pro selling at least 10% of volume
  - ACCUMULATION: pros net buying, consumers not buying
  - RETAIL CHASE: acceleration ≥ 3 and consumer apps ≥ 60% of buys
- **Output:** Market strip; live table of coins with age, market cap, liquidity, buyers and acceleration, flows by segment, flag and median buyer profit.
- **Running version (0):** market level from TEHscreener (consumer share 43.9%, normal for 90 days); token flags on Solana from GMGN's app tags on a daily trade sample (17 ACCUMULATION, 0 DISTRIBUTION). RETAIL CHASE needs hourly data.
- **Test:** Flagged coins vs matched control coins (same market cap, age and volume) must show a significant return difference after 2–4% costs in at least 3 out-of-sample months. **Not yet validated.**

### 11. Cohort Flow
- **Question:** Which kinds of wallets are buying or selling a coin?
- **Cohorts, fixed at the start of each window:** insider, smart, whale (≥ 0.5% of supply at window start), retail, new (zero balance at start), bot/market maker.
- **Measured as:** net flow = USD bought − sold through all pools and aggregators; normalised flow = net flow ÷ market cap at window start (bps); z-score of the normalised flow against the coin's own 90 days for that cohort. AccumScore = z(smart) + z(whale) − z(insider selling).
- **Output:** Coins ranked by AccumScore (never by raw dollars); index line = smart-flow breadth (share of coins with positive 7-day smart flow).
- **Running version (0):** Solana only, from GMGN trades; smart = wallets in GMGN's top-300 PnL rankings, whale = holders ≥ 0.5% of supply, insider/new/bot from GMGN tags; bps of market cap without z-scores (need 90 days). Smart-flow breadth today: 1 of 65 coins.
- **Test:** Does any cohort's flow rank-predict returns after costs, out of sample? **Not yet validated.**

### 12. Attention vs Flow
- **Question:** Is the hype backed by real buying?
- **Measured as:** Attention = unique authors mentioning the ticker or contract in the last 6 h, weighted by influence; AttZ = its z-score against the coin's own 7 days; FlowZ = z-score of smart + whale net flow. Flags: HYPE WITHOUT FLOW (AttZ ≥ 2, FlowZ ≤ 0: likely distribution), QUIET ACCUMULATION (AttZ ≤ 0.5, FlowZ ≥ 2), CONFIRMED (both ≥ 2).
- **Data:** A social feed is needed. Free options: GMGN's KOL callouts, Chainbase's X mentions search (prototype).
- **Status:** Waiting for data.

---

## Part 4: Coin level

### 13. Coin page: Quality × Flow
- **Question:** For one coin: is it in a good setup, and what would change that?
- **Holders used:** clustered, excluding insiders, bots, exchanges and pools.
- **Quality (slow-moving), each as a percentile against a frozen calibration set:**
  - StressHold = across recent drawdowns of 30%+, the share of supply that the same non-insider holders still held at the low vs at the peak (deeper drawdowns weigh more)
  - Tenure = supply-weighted median holding age
  - Breadth = change in the number of holders of at least 0.001% of supply (not a dollar threshold, so it does not move with price)
  - InsiderShare = supply held by insider clusters (lower is better)
  - ExitCover = liquidity within 5% price impact ÷ value held by the top 10 non-insider holders
  - Quality = average of the five
- **Flow (fast), each as a z-score:** smart net flow (7 d), net new holders (7 d), whale share change, dip absorption (organic buy ÷ sell volume on down days). Flow = average.
- **States:** Accumulation (high quality, flow positive), Distribution risk (high quality, flow negative), Speculative bid (low quality, flow positive), Avoid (low quality, flow negative).
- **One-screen card:** state, quality and rank, flow, days since change; why (top three drivers); risk (insider share, exit cover, current drawdown); levels (cost-basis resistance and support); odds (coins in this state: median 14-day return, chance of −50% in 30 days, n); flips (exact conditions that would change the state).
- **Running version (0):** Solana; Quality from insider share (GMGN creator/dev/sniper/bundler tags), top-10 concentration and exit cover (liquidity × 2.47% ÷ top-10 holdings, the constant-product depth within 5%), ranked against today's coins; Flow from Cohort Flow. StressHold, Tenure and Breadth need history. Today: 5 Accumulation, 23 Distribution risk, 7 Speculative bid, 27 Avoid.
- **Test:** Quality must lower the chance of a crash out of sample; Flow must have a rank correlation with returns after costs above zero. **Not yet validated.**

### 14. Cost-basis map
- **Question:** Where did holders buy, and where will they sell?
- **Measured as:** Supply held at each purchase price (from the cost basis engine); share of supply in profit; overhang = the supply-weighted cost of holders at a loss (resistance on the way up); support = levels where buyers absorbed selling before.
- **Running version (0):** Solana top-100 holders from GMGN: share in profit (median coin today: 31%) and loss-holders' average cost relative to price.
- **Status:** Not yet validated (descriptive).

### 15. Bottom Probability
- **Question:** For a coin that has crashed, how likely is a real bottom?
- **Eligible:** at least 50% below its 90-day high.
- **Target (triple barrier):** enter at the next day's open; success if price rises 50% before it falls to 25% below the drawdown low, within 30 days.
- **Features:** share of selling done at a loss of more than 50% vs cost; exhaustion (realised loss last 3 days ÷ peak 3-day realised loss); days since the low; retests of the low that held; range compression (7-day ÷ 30-day average true range); a higher low; organic and new-wallet flow z-scores; smart flow; insider supply remaining; exit cover; chain regime and rotation state.
- **Model:** logistic regression with isotonic calibration, trained on the point-in-time universe including dead coins (later: gradient boosting with monotonic constraints).
- **Output:** probability vs base rate, days in state, stop level, first cost-basis resistance, reward/risk, maximum size at 2% price impact. The headline state changes only after two days across the threshold.
- **Running version:** eligibility only (63 of 163 coins today). The model is not trained: it needs labelled drawdowns from a universe that includes dead coins.
- **Test:** out-of-sample AUC at least 0.55 and better than the base rate after costs. **Not yet validated.**

---

## Part 5: Trust

### 16. Public track record
- **Measured as:** every flag and state change (regime, rotation quadrant, coin setup, flow flags, bottom-probability crossings) logged when issued, with formula version and input cutoff, never edited. Outcomes computed automatically at 1, 7, 14 and 30 days after 2–4% round-trip costs.
- **Output:** per signal: count, hit rate, median and mean forward return, calibration (for probabilities), downloadable log.
- **Status:** storage ready; nothing logged until an indicator earns signal status.

### 17. Organic ratio
- **Measured as:** organic volume ÷ total volume, per chain and venue, by count and by dollars.
- **Today:** Robinhood 58% of swaps / 15% of dollars (a few very large automated round trips dominate dollars); Base 43% / 21%; Solana 69% of dollars not from sandwich bots or bundlers (GMGN tags).

---

## Part 6: Additional indicators (SPEC §6.8)

| Indicator | Question | How it is measured | Status |
|---|---|---|---|
| Fresh-wallet inflow | Is new money arriving? | Share of buyers less than 7 days old whose first funding came from an exchange (exchange address lists) | Not built |
| Trench PnL | Are launch buyers making money? | Median 24 h return of early buyers in last week's real launches | Running (Long −11%, PonsFamily −27%) |
| Organic ratio | How much is real? | See 17 | Running |
| Net capital inflow by chain | Is money entering or leaving each chain? | 7-day change in stablecoin supply (DefiLlama); later plus bridge and exchange flows | Running (stablecoins leaving all four chains) |
| Wallet migration matrix | Where are traders moving? | Same EVM address active on one chain last week and another this week | Not built |
| Urgency index | How hard are traders racing? | Median priority fee plus tip per organic swap | Running for Solana |
| Sniper share | Was supply grabbed at launch? | Share of supply bought in the first two blocks by creator-linked wallets | Not built (GMGN sniper tags available) |
| Serial-deployer concentration | Is a launchpad spam? | Share of launches made by the top 5 creator wallets | Running (Long 87%, PonsFamily 5%) |
| Launchpad token valuation | Is a pad's token cheap? | Annualised revenue, buyback yield, price ÷ revenue (TEHscreener, DefiLlama) | Not built |
| Copy-trade echo ratio | How much buying is copying? | Volume that follows a known leader wallet within seconds, ÷ total | Not built |
| Attention half-life and lateness | How fast does hype fade, and are you late? | Decay rate of mentions; time since attention peak | Needs social data |
| PnL by terminal user base | Which app's users make money? | Median realised profit per segment | Not built |
| Dormant supply wake-up | Are old holders moving? | Alert when supply idle for 30+ days moves | Not built |
| Holder rotation | Where are holders going? | What a coin's holders buy and sell elsewhere | Not built |
| Bottoming breadth | Is the market washing out? | Share of coins with rising bottom probability | Needs the model |
| Second-leg risk | Is there more selling to come? | Unsold insider and dormant supply ÷ liquidity | Not built |
| Dev re-entry / community takeover | Is the creator back, or has the community taken over? | Creator-linked wallets buying back after exiting; creator fully gone while new holders grow | Not built |
| Meme perp positioning | Are perps crowded? | Hyperliquid funding (annualised) and open interest, with funding's 30-day percentile | Running (25 contracts, $126M open interest, funding low) |
| Capitulation breadth | How many coins are being dumped at a loss? | Share of coins where loss-selling share is extreme | Not built |
| Cross-chain sentiment spread | Which chain is most greedy? | Sentiment of each chain minus the average | Needs Sentiment |
| Absorption ratio | Who buys when insiders and whales sell? | Share of that selling absorbed by new vs smart wallets | Not built |
| Whale profit cushion | How far can price fall before whales are underwater? | Whales' average cost vs price | Not built (GMGN holder cost available) |
| Smart-flow breadth | Is smart money buying broadly? | Share of coins with positive 7-day smart flow | Running (1 of 65) |

---

## How every indicator is validated

- **Universe:** point in time, dead coins included.
- **Method:** walk-forward, a new out-of-sample month at a time.
- **Costs:** 2–4% round trip for microcaps, plus slippage from liquidity.
- **Measures:** rank correlation with forward returns; top vs bottom fifth spreads; hit rate; event studies against matched control coins; calibration and Brier score for probabilities; AUC vs base rate; stability (states must last a median of at least 5 days).
- **Statistics:** non-overlapping or block-bootstrapped samples; errors corrected for overlap and for small groups (chains, pads).
- **Placebo:** competitor methods rerun on random simulated trades to show their artifacts.

| Indicator | Shown as description only if… |
|---|---|
| Trench Regime | extremes and states do not separate forward basket returns |
| Chain Rotation | share changes do not persist beyond a week and quadrants do not separate forward relative returns |
| Launchpad Scorecard | LQS has no week-to-week persistence and no link to the next cohort's outcomes |
| Flow flags | the flagged-vs-control return gap is not significant in 3+ out-of-sample months after costs |
| Quality | it does not lower crash probability out of sample |
| Flow | its rank correlation after costs is indistinguishable from zero |
| Bottom Probability | out-of-sample AUC below 0.55, or no edge over the base rate after costs |
| Cohort Flow | no cohort beats zero rank correlation out of sample |
