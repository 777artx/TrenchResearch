# Indicator status (2026-11-19 22:42 UTC)

Every reading is research, not financial advice. "Not validated" means the indicator has no backtest yet; nothing here has signal status.

| Group | Indicator | Status | Current reading |
|---|---|---|---|
| Market | Trench Regime: Activity | Description only (failed backtest) | base 53 hot, ethereum 80 hot, solana 49 cold |
| Market | Trench Regime: Sentiment (mSOPR) | Computing, not validated | robinhood: 1.008 (profit-taking, 1,610 organic sells, 72 h window); base: 0.999 (selling at a loss, 387 organic sells, 5 h window); ethereum: no swaps yet |
| Market | Regime state (Activity × Sentiment) | Pending data | Sentiment has no 365-day percentile history yet; first state needs ~180 days of organic mSOPR |
| Market | Chain Rotation | Description only (failed backtest) | base leading, ethereum lagging, robinhood improving, solana improving |
| Market | Launchpad Scorecard | Computing, not validated | see launchpad cohort reports; Long.xyz and PonsFamily, cohort 2026-11-11 |
| Flow | Retail Flow Desk (market) | Computing, not validated | consumer-app share of terminal volume 43.9% on 2026-11-18 00:00:00 (robust z -0.1 vs 90 days); average ticket CONSUMER $45, PRO $49, TG-BOT $68 |
| Flow | Retail Flow Desk (token flags) | Computing, not validated | 65 Solana coins: 0 DISTRIBUTION, 17 ACCUMULATION, 48 no flag (trade sample; RETAIL CHASE needs hourly data) |
| Flow | Cohort Flow | Computing, not validated | 65 Solana coins scored; smart-flow breadth 1/65 coins with positive smart-wallet net buying (bps of market cap; z-scores need 90 days of history) |
| Flow | Attention vs Flow | Pending data | needs a social feed; GMGN callouts are not yet collected daily |
| Coin | Cost-basis map | Computing, not validated | 62 Solana coins; median share of top-holder supply in profit 31% |
| Coin | Quality × Flow setup | Computing, not validated | 62 Solana coins: Accumulation 5, Avoid 27, Distribution risk 23, Speculative bid 7 (partial components) |
| Coin | Bottom Probability (eligibility) | Computing, not validated | 63 of 163 universe coins with price history are at least 50% below their 90-day high (eligible); the probability model needs labelled drawdown history and is not trained |
| Trust | Public track record | Pending data | storage and logging ready; no indicator has signal status, so no live signals are logged yet |
| Trust | Organic ratio | Computing, not validated | robinhood: 15% of USD, 58% of swaps (28,455 swaps); base: 21% of USD, 43% of swaps (7,347 swaps); solana (GMGN tags, sample): 69% of USD not from sandwich bots or bundlers |
| Extra | Meme perp positioning | Computing, not validated | 25 meme perps, $128M open interest, OI-weighted funding +3.4%/yr; top: PUMP +9% (p25), DOGE -4% (p11), kPEPE +7% (p21), FARTCOIN +11% (p18) |
| Extra | Net capital inflow by chain | Computing, not validated | stablecoin supply 7-day change: solana -8.2% ($-1,170M), base -3.0% ($-161M), ethereum -1.4% ($-1,865M), robinhood -2.3% ($-24M) |
| Extra | Serial-deployer concentration + Trench PnL | Computing, not validated | long.xyz: top-5 creators made 87% of launches; median early-buyer 24 h return -11%; ponsfamily.com: top-5 creators made 5% of launches; median early-buyer 24 h return -27% |
| Extra | Urgency index (Solana) | Computing, not validated | median priority fee + tip 0.00001 SOL per Solana trade (27,007 trades sampled) |
| Extra | Smart-flow breadth | Pending data | included in Cohort Flow line above |
