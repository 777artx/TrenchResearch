"""Version-0 readings for every indicator that current data supports.

Each function returns ``(readings, summary)``: point-in-time readings to publish
(formula "0", ``validated: false``) and a one-line summary for the status list.
Indicators whose inputs do not exist yet return no readings and a summary that
says what is missing. Nothing here has passed a backtest; see docs/indicators.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta

import httpx
import numpy as np
import pandas as pd

from trench import organic, universe
from trench.ingest.evm_swaps import SWAPS_WITH_TIMES
from trench.lake import Lake
from trench.pit import PITStore, Reading
from trench.timeutil import utcnow

CONSUMER = {"fomo", "pumpapp", "gmgn_go"}
PRO = {"axiom", "gmgn", "photon", "padre", "terminal", "bullx", "proxima"}
TGBOT = {"trojan", "maestro", "bonkbot", "basedbot"}
MEME_PERPS = {"kPEPE", "WIF", "POPCAT", "kBONK", "FARTCOIN", "PNUT", "TRUMP", "MOODENG",
              "BRETT", "kSHIB", "DOGE", "MEW", "GOAT", "PENGU", "SPX", "PUMP", "kFLOKI",
              "TURBO", "MELANIA", "CHILLGUY", "AI16Z", "NEIRO", "BOME", "kNEIRO", "PEOPLE",
              "MOG", "kMOG", "GIGA", "USELESS", "TROLL"}


def _segment(tags: str | None) -> str | None:
    t = set((tags or "").split(","))
    if t & CONSUMER:
        return "CONSUMER"
    if t & PRO:
        return "PRO"
    if t & TGBOT:
        return "TG-BOT"
    return None


def _rd(entity, value, state=None, **detail):
    return Reading(entity=entity, as_of=utcnow().date(), value=None if value is None or
                   (isinstance(value, float) and np.isnan(value)) else float(value),
                   state=state, detail={**detail, "validated": False})


# ---------------------------------------------------------------- EVM swaps + cost basis
def evm_swaps_priced(lake: Lake, chain: str) -> pd.DataFrame:
    con = lake.connect()
    sw = con.execute(SWAPS_WITH_TIMES + " WHERE s.chain = ? AND b.block_timestamp IS NOT NULL",
                     [chain]).df()
    if sw.empty:
        return sw
    eth = dict(con.execute("SELECT day, price_usd FROM llama_price_daily "
                           "WHERE asset = 'ETH'").fetchall())
    last = eth[max(eth)]
    for d in set(pd.to_datetime(sw.block_timestamp, unit="s").dt.date):
        eth.setdefault(d, last)
    df = organic.classify(organic.prepare(sw, eth))
    df["amt"] = df.tok_delta.abs().astype(float)
    df["px"] = df.usd / df.amt
    df = df.sort_values(["token", "block_timestamp", "log_index"])
    df["px"] = df.groupby("token")["px"].transform(lambda s: s.ffill().bfill())
    df["usd_f"] = df.usd.fillna(df.px * df.amt)
    return df


def fifo_cost_basis(df: pd.DataFrame) -> pd.DataFrame:
    """Per sell: value, FIFO cost of the part bought inside the window, and the
    share of the sell whose basis is known (tokens bought before the window or
    received by transfer have no basis here)."""
    lots: dict[tuple, deque] = defaultdict(deque)
    out = []
    for r in df.itertuples():
        key = (r.token, r.tx_from)
        if r.tok_delta > 0:
            lots[key].append([r.amt, r.px])
        elif r.tok_delta < 0 and r.amt > 0:
            need, cost, matched = r.amt, 0.0, 0.0
            q = lots[key]
            while need > 0 and q:
                lot = q[0]
                take = min(need, lot[0])
                cost += take * lot[1]
                matched += take
                lot[0] -= take
                need -= take
                if lot[0] <= 1e-12:
                    q.popleft()
            out.append({"token": r.token, "wallet": r.tx_from, "ts": r.block_timestamp,
                        "organic": r.organic, "value": matched * r.px, "cost": cost,
                        "known_share": matched / r.amt})
    return pd.DataFrame(out)


def sentiment_msopr(lake: Lake, chains=("robinhood", "base", "ethereum")):
    readings, parts = [], []
    for c in chains:
        df = evm_swaps_priced(lake, c)
        if df.empty:
            parts.append(f"{c}: no swaps yet")
            continue
        s = fifo_cost_basis(df)
        s = s[s.organic & (s.known_share > 0.99) & (s.cost > 0)]
        if s.empty:
            parts.append(f"{c}: no sells with known basis")
            continue
        m = s.value.sum() / s.cost.sum()
        hours = (df.block_timestamp.max() - df.block_timestamp.min()) / 3600
        readings.append(_rd(f"chain={c}", m, "greed" if m > 1 else "fear", sells=len(s),
                            window_hours=round(hours, 1), basis="FIFO within window"))
        parts.append(f"{c}: {m:.3f} ({'profit-taking' if m > 1 else 'selling at a loss'}, "
                     f"{len(s):,} organic sells, {hours:.0f} h window)")
    return readings, "; ".join(parts)


def organic_ratio(lake: Lake, chains=("robinhood", "base", "ethereum")):
    readings, parts = [], []
    for c in chains:
        df = evm_swaps_priced(lake, c)
        if df.empty:
            continue
        r_n, r_usd = df.organic.mean(), df.loc[df.organic, "usd_f"].sum() / df.usd_f.sum()
        readings.append(_rd(f"chain={c}", r_usd, None, swaps=len(df), organic_share_swaps=r_n))
        parts.append(f"{c}: {r_usd:.0%} of USD, {r_n:.0%} of swaps ({len(df):,} swaps)")
    sol = _gmgn_trades(lake)
    if not sol.empty:
        bot = sol.maker_tags.fillna("").str.contains("sandwich_bot|bundler")
        r = 1 - sol.loc[bot, "usd"].sum() / sol.usd.sum()
        readings.append(_rd("chain=solana", r, None, trades=len(sol), source="GMGN tags"))
        parts.append(f"solana (GMGN tags, sample): {r:.0%} of USD not from sandwich bots "
                     f"or bundlers")
    return readings, "; ".join(parts)


# ---------------------------------------------------------------- Solana via GMGN
def _gmgn_trades(lake: Lake) -> pd.DataFrame:
    if "gmgn_trades" not in lake.tables():
        return pd.DataFrame()
    df = lake.connect().execute(
        "SELECT * FROM gmgn_trades WHERE side IN ('buy','sell') "
        "QUALIFY row_number() OVER (PARTITION BY trade_id ORDER BY fetched_at DESC) = 1").df()
    df["signed"] = np.where(df.side == "buy", df.usd, -df.usd)
    return df


def _gmgn_holders(lake: Lake) -> pd.DataFrame:
    if "gmgn_holders" not in lake.tables():
        return pd.DataFrame()
    return lake.connect().execute(
        "SELECT * FROM gmgn_holders QUALIFY run_id = max(run_id) OVER (PARTITION BY token)").df()


def _mcaps(lake: Lake, chain: str) -> dict:
    return dict(lake.connect().execute(
        """SELECT base_token, arg_max(coalesce(market_cap_usd, fdv_usd), liquidity_usd)
           FROM dxs_pair_snapshot WHERE chain = ? AND run_id = (SELECT max(run_id)
           FROM dxs_pair_snapshot) GROUP BY 1""", [chain]).fetchall())


def _liquidity(lake: Lake, chain: str) -> dict:
    return dict(lake.connect().execute(
        """SELECT base_token, sum(liquidity_usd) FROM dxs_pair_snapshot WHERE chain = ?
           AND run_id = (SELECT max(run_id) FROM dxs_pair_snapshot) GROUP BY 1""",
        [chain]).fetchall())


def retail_flow_tokens(lake: Lake):
    tr = _gmgn_trades(lake)
    if tr.empty:
        return [], "no Solana trades yet"
    tr["seg"] = tr.maker_tags.map(_segment)
    readings, flags = [], defaultdict(int)
    for tok, g in tr.groupby("token"):
        vol = g.usd.sum()
        nf = {s: g.loc[g.seg == s, "signed"].sum() for s in ("CONSUMER", "PRO", "TG-BOT")}
        flag = None
        if nf["PRO"] < 0 < nf["CONSUMER"] and abs(nf["PRO"]) >= 0.1 * vol:
            flag = "DISTRIBUTION"
        elif nf["PRO"] > 0 >= nf["CONSUMER"]:
            flag = "ACCUMULATION"
        flags[flag or "none"] += 1
        readings.append(_rd(f"solana:{tok}", nf["PRO"], flag, nf_consumer=nf["CONSUMER"],
                            nf_pro=nf["PRO"], nf_tgbot=nf["TG-BOT"], volume_usd=vol,
                            trades=len(g), window_start=str(g.block_time.min()),
                            window_end=str(g.block_time.max())))
    return readings, (f"{len(readings)} Solana coins: {flags['DISTRIBUTION']} DISTRIBUTION, "
                      f"{flags['ACCUMULATION']} ACCUMULATION, {flags['none']} no flag "
                      "(trade sample; RETAIL CHASE needs hourly data)")


def retail_flow_market(lake: Lake):
    df = lake.as_of("teh_bots_by_bot", ["bot", "day"]).df()
    df["seg"] = df.bot.map(lambda b: "CONSUMER" if b in CONSUMER else "PRO" if b in PRO
                           else "TG-BOT" if b in TGBOT else None)
    daily = df.pivot_table(index="day", columns="seg", values="volume_usd", aggfunc="sum")
    daily = daily.sort_index().fillna(0)
    share = daily.get("CONSUMER", 0) / daily.sum(axis=1)
    hist = share.iloc[-91:-1]
    med = hist.median()
    mad = (hist - med).abs().median() * 1.4826
    z = (share.iloc[-1] - med) / mad if mad else float("nan")
    day = share.index[-1]
    tick = (df[df.day == day].groupby("seg").apply(lambda g: g.volume_usd.sum() / g.txns.sum())
            .to_dict())
    r = _rd("market", share.iloc[-1], None, consumer_share_z_90d=float(z), day=str(day),
            avg_ticket=tick)
    return [r], (f"consumer-app share of terminal volume {share.iloc[-1]:.1%} on {day} "
                 f"(robust z {z:+.1f} vs 90 days); average ticket "
                 + ", ".join(f"{k} ${v:,.0f}" for k, v in tick.items()))


def cohort_flow_solana(lake: Lake):
    tr, hold = _gmgn_trades(lake), _gmgn_holders(lake)
    if tr.empty:
        return [], "no Solana trades yet"
    smart = set()
    if "gmgn_wallet_rank" in lake.tables():
        smart = {w for (w,) in lake.connect().execute(
            "SELECT DISTINCT wallet FROM gmgn_wallet_rank "
            "WHERE run_id = (SELECT max(run_id) FROM gmgn_wallet_rank)").fetchall()}
    whales = defaultdict(set)
    for r in hold.itertuples():
        if (r.share or 0) >= 0.005 and not r.exchange:
            whales[r.token].add(r.wallet)
    mc = _mcaps(lake, "solana")
    readings, pos, n = [], 0, 0
    for tok, g in tr.groupby("token"):
        tags = g.maker_tags.fillna("") + "," + g.maker_token_tags.fillna("")
        coh = np.select(
            [tags.str.contains("sniper|bundler|dev"), g.wallet.isin(smart),
             g.wallet.isin(whales[tok]), tags.str.contains("fresh_wallet"),
             tags.str.contains("sandwich_bot")],
            ["INSIDER", "SMART", "WHALE", "NEW", "BOT/MM"], "RETAIL")
        nf = pd.Series(g.signed.values, index=coh).groupby(level=0).sum()
        cap = mc.get(tok)
        nfn = {k: (v / cap * 1e4 if cap else None) for k, v in nf.items()}  # bps of mcap
        ins_sell = max(0, -(nfn.get("INSIDER") or 0))
        score = (nfn.get("SMART") or 0) + (nfn.get("WHALE") or 0) - ins_sell
        n += 1
        pos += (nf.get("SMART", 0) > 0)
        readings.append(_rd(f"solana:{tok}", score, None, nf_usd=nf.to_dict(), nf_bps=nfn,
                            mcap=cap, trades=len(g)))
    return readings, (f"{n} Solana coins scored; smart-flow breadth {pos}/{n} coins with "
                      "positive smart-wallet net buying (bps of market cap; z-scores need "
                      "90 days of history)")


def cost_basis_map(lake: Lake):
    hold = _gmgn_holders(lake)
    if hold.empty:
        return [], "no holder snapshots yet"
    readings, inprof = [], []
    for tok, g in hold.groupby("token"):
        g = g[g.balance.fillna(0) > 0]
        priced = g[g.avg_cost.notna() & (g.avg_cost > 0) & g.usd_value.notna()]
        if priced.empty:
            continue
        px = (priced.usd_value / priced.balance).median()
        in_profit = priced.loc[priced.avg_cost < px, "balance"].sum() / priced.balance.sum()
        losers = priced[priced.avg_cost > px]
        overhang = (float(np.average(losers.avg_cost, weights=losers.balance))
                    if len(losers) else None)
        inprof.append(in_profit)
        readings.append(_rd(f"solana:{tok}", in_profit, None, price=float(px),
                            overhang_price=overhang, holders_priced=len(priced)))
    return readings, (f"{len(readings)} Solana coins; median share of top-holder supply in "
                      f"profit {np.median(inprof):.0%}" if inprof else "no priced holders")


def quality_flow(lake: Lake, cohort_readings, cbm_readings):
    hold = _gmgn_holders(lake)
    if hold.empty:
        return [], "no holder snapshots yet"
    liq = _liquidity(lake, "solana")
    flow = {r.entity: r.value for r in cohort_readings}
    prof = {r.entity: r.value for r in cbm_readings}
    rows = []
    for tok, g in hold.groupby("token"):
        g = g[(g.balance.fillna(0) > 0) & g.exchange.isna()]
        tags = g.tags.fillna("") + "," + g.wallet_tag.fillna("")
        insider = g.loc[tags.str.contains("sniper|bundler|dev|insider"), "share"].sum()
        top10 = g.nlargest(10, "share")
        top_val = top10.usd_value.sum()
        # Depth within 5% price impact of a constant-product pool is about 2.47% of
        # total liquidity on the sell side; exit cover = that depth / top-10 holdings.
        exitcover = (liq.get(tok) or 0) * 0.0247 / top_val if top_val else None
        rows.append({"e": f"solana:{tok}", "insider": insider, "top10": top10.share.sum(),
                     "exitcover": exitcover, "profit": prof.get(f"solana:{tok}")})
    t = pd.DataFrame(rows)
    pct = pd.DataFrame({"a": 1 - t.insider.rank(pct=True), "b": 1 - t.top10.rank(pct=True),
                        "c": t.exitcover.rank(pct=True)})
    t["Q"] = pct.mean(axis=1) * 100
    t["F"] = t.e.map(flow)
    readings, counts = [], defaultdict(int)
    for r in t.itertuples():
        hiq, f = r.Q >= 50, (r.F or 0)
        state = ("Accumulation" if hiq and f > 0 else "Distribution risk" if hiq
                 else "Speculative bid" if f > 0 else "Avoid")
        counts[state] += 1
        readings.append(_rd(r.e, r.Q, state, flow=r.F, insider_share=r.insider,
                            top10_share=r.top10, exit_cover=r.exitcover,
                            components="insider share, top-10 concentration, exit cover; "
                                       "StressHold, Tenure, Breadth pending history",
                            calibration="today's Solana universe (provisional)"))
    return readings, (f"{len(readings)} Solana coins: " +
                      ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
                      " (partial components)")


# ---------------------------------------------------------------- drawdowns (bottoms)
def drawdowns(lake: Lake, pit: PITStore):
    con = lake.connect()
    members = universe.members(pit, utcnow().date())
    df = con.execute("""SELECT chain, token, day, close, high FROM gt_pool_ohlcv_day
        QUALIFY row_number() OVER (PARTITION BY chain, token, day ORDER BY fetched_at DESC) = 1"""
                     ).df()
    df["e"] = df.chain + ":" + df.token
    df = df[df.e.isin(members)]
    readings, deep = [], 0
    for e, g in df.sort_values("day").groupby("e"):
        last = g.day.max()
        win = g[g.day > last - pd.Timedelta(days=90)] if hasattr(last, "to_pydatetime") else \
            g[pd.to_datetime(g.day) > pd.to_datetime(last) - pd.Timedelta(days=90)]
        hi, close = win.high.max(), g.close.iloc[-1]
        dd = close / hi - 1 if hi else None
        if dd is not None and dd <= -0.5:
            deep += 1
            readings.append(_rd(e, dd, "eligible", high_90d=float(hi), close=float(close),
                                last_day=str(last)))
    n = df.e.nunique()
    return readings, deep, n


# ---------------------------------------------------------------- external free sources
def meme_perps():
    with httpx.Client(timeout=60) as c:
        meta, ctx = c.post("https://api.hyperliquid.xyz/info",
                           json={"type": "metaAndAssetCtxs"}).json()
        start = int((utcnow() - timedelta(days=30)).timestamp() * 1000)
        readings, rows = [], []
        for a, x in zip(meta["universe"], ctx, strict=True):
            if a["name"] not in MEME_PERPS:
                continue
            f_now = float(x["funding"]) * 24 * 365
            oi = float(x["openInterest"]) * float(x["markPx"])
            hist = c.post("https://api.hyperliquid.xyz/info", json={
                "type": "fundingHistory", "coin": a["name"], "startTime": start}).json()
            fr = np.array([float(h["fundingRate"]) for h in hist]) * 24 * 365
            pct = float((fr < f_now).mean() * 100) if len(fr) else None
            readings.append(_rd(f"perp={a['name']}", f_now, None, open_interest_usd=oi,
                                funding_pct_30d=pct))
            rows.append((a["name"], f_now, oi, pct))
    rows.sort(key=lambda r: -r[2])
    oi_tot = sum(r[2] for r in rows)
    w = sum(r[1] * r[2] for r in rows) / oi_tot if oi_tot else 0
    return readings, (f"{len(rows)} meme perps, ${oi_tot / 1e6:,.0f}M open interest, "
                      f"OI-weighted funding {w:+.1%}/yr; top: " +
                      ", ".join(f"{n} {f:+.0%} (p{p:.0f})" for n, f, _, p in rows[:4]))


def capital_inflow():
    readings, parts = [], []
    with httpx.Client(timeout=60) as c:
        for chain, name in (("solana", "Solana"), ("base", "Base"), ("ethereum", "Ethereum"),
                            ("robinhood", "Robinhood")):
            d = c.get(f"https://stablecoins.llama.fi/stablecoincharts/{name}").json()
            tot = [sum(x["totalCirculatingUSD"].values()) for x in d]
            if len(tot) < 8:
                continue
            ch7 = tot[-1] / tot[-8] - 1
            readings.append(_rd(f"chain={chain}", tot[-1] - tot[-8], None,
                                stablecoins_usd=tot[-1], change_7d=ch7))
            parts.append(f"{chain} {ch7:+.1%} (${(tot[-1] - tot[-8]) / 1e6:+,.0f}M)")
    return readings, "stablecoin supply 7-day change: " + ", ".join(parts)


def launchpad_extras(lake: Lake):
    if "lp_launch_outcomes" not in lake.tables():
        return [], [], "no launch cohorts yet"
    df = lake.connect().execute("SELECT * FROM lp_launch_outcomes QUALIFY row_number() OVER "
                                "(PARTITION BY pad, token ORDER BY fetched_at DESC) = 1").df()
    serial, pnl, parts = [], [], []
    for pad, g in df.groupby("pad"):
        top5 = g.creator.value_counts().head(5).sum() / len(g)
        serial.append(_rd(f"pad={pad}", top5, None, launches=len(g),
                          creators=int(g.creator.nunique())))
        ls = g[g.lstar.astype(bool)]
        if len(ls):
            pnl.append(_rd(f"pad={pad}", float(ls.buyret.median()), None, n=len(ls)))
        parts.append(f"{pad}: top-5 creators made {top5:.0%} of launches; median early-buyer "
                     f"24 h return {ls.buyret.median():+.0%}" if len(ls) else f"{pad}: {top5:.0%}")
    return serial, pnl, "; ".join(parts)


def urgency_solana(lake: Lake):
    tr = _gmgn_trades(lake)
    if tr.empty or "priority_fee" not in tr:
        return [], "no Solana trades yet"
    fee = (tr.priority_fee.fillna(0) + tr.tip_fee.fillna(0))
    m = float(fee.median())
    return [_rd("chain=solana", m, None, unit="SOL per trade", trades=len(tr))], \
        f"median priority fee + tip {m:.5f} SOL per Solana trade ({len(tr):,} trades sampled)"
