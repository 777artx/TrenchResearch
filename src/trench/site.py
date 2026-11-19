"""Static research site built from published (point-in-time) readings.

``trench site`` writes one self-contained HTML page. Every figure comes from the
point-in-time store or the lake; nothing is typed in by hand. Each section carries
its indicator's status (description only / not validated / signal).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from trench.lake import Lake
from trench.pit import PITStore
from trench.timeutil import utcnow


def E(x) -> str:  # noqa: N802
    """HTML-escape any value; missing values (None, NaN) render as a dash."""
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return html.escape(str(x))

BADGE = {
    "signal": ("Signal", "#E3EEE8", "#1F5C43"),
    "desc": ("Description only", "#F1E6E0", "#8A3E1C"),
    "nv": ("Not yet validated", "#E7ECF3", "#1F4E79"),
    "pending": ("Waiting for data", "#EEF0F3", "#475569"),
}


def badge(kind: str) -> str:
    t, bg, fg = BADGE[kind]
    return (f'<span class="badge" style="background:{bg};color:{fg}">{t}</span>')


def _latest(pit: PITStore, metric: str) -> pd.DataFrame:
    if metric not in pit.lake.tables():
        return pd.DataFrame()
    df = pit.read(metric).df()
    if df.empty:
        return df
    df = df[df.as_of == df.as_of.max()].copy()
    df["d"] = df.detail.map(lambda x: json.loads(x) if x else {})
    return df


def _symbols(lake: Lake) -> dict:
    rows = lake.connect().execute(
        """SELECT chain, base_token, arg_max(base_symbol, liquidity_usd),
                  arg_max(coalesce(market_cap_usd, fdv_usd), liquidity_usd), sum(liquidity_usd)
           FROM dxs_pair_snapshot WHERE run_id = (SELECT max(run_id) FROM dxs_pair_snapshot)
           GROUP BY 1, 2""").fetchall()
    return {f"{c}:{t}": (s, m, liq) for c, t, s, m, liq in rows}


# Bucket rule (SPEC §5.5: memecoin / majors / RWA). Majors: wrapped or staked major
# assets. RWA: tokenized stocks, which on Solana use the xStocks naming (ticker + "x").
MAJORS = {"WETH", "ETH", "WBTC", "CBBTC", "BTC", "SOL", "WSOL", "JITOSOL", "MSOL", "BNSOL",
          "JUPSOL", "INF", "USDC", "USDT", "PYUSD", "USD1", "USDG", "EURC"}


def bucket(symbol: str | None) -> str:
    s = (symbol or "").strip()
    if s.upper() in MAJORS:
        return "major"
    if len(s) >= 3 and s.endswith("x") and s[:-1].isupper():
        return "rwa"
    return "meme"


def usd(x, digits=1) -> str:
    if x is None or pd.isna(x):
        return "—"
    a = abs(x)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"${x / div:,.{digits}f}{suf}"
    return f"${x:,.0f}"


def pct(x, digits=0, sign=False) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x * 100:{'+' if sign else ''}.{digits}f}%"


def section(id_, title, kind, body, note="") -> str:
    n = f'<p class="note">{note}</p>' if note else ""
    return (f'<section id="{id_}"><div class="sh"><h2>{E(title)}</h2>{badge(kind)}</div>'
            f'{body}{n}</section>')


def table(headers, rows, right=()) -> str:
    th = "".join(f'<th class="{"r" if i in right else ""}">{E(h)}</th>'
                 for i, h in enumerate(headers))
    trs = "".join("<tr>" + "".join(f'<td class="{"r num" if i in right else ""}">{c}</td>'
                                   for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def build(lake: Lake, pit: PITStore, status_path: Path) -> str:
    sym = _symbols(lake)
    now = utcnow()
    parts = []

    # Market: activity + sentiment
    act = _latest(pit, "trench_activity")
    sen = {r.entity: r for r in _latest(pit, "sentiment_msopr").itertuples()}
    cards = []
    for r in act.sort_values("value", ascending=False).itertuples():
        ch = r.entity.split("=")[1]
        d = r.d
        div = ""
        if d.get("s_V") and d.get("s_P") and d["s_V"] - d["s_P"] >= 40:
            div = "<p>Dollars are high while wallets are low: activity is likely bot-heavy.</p>"
        s = sen.get(f"chain={ch}")
        sline = (f'<div class="kv"><span>Sentiment (mSOPR)</span><span class="num">'
                 f'{s.value:.3f}</span></div>' if s is not None else "")
        cards.append(f'''<article class="card"><div class="ct"><h3>{E(ch.title())}</h3>
          <span class="muted num">{d.get("trend", 0):+.1f} vs 7d</span></div>
          <div class="big"><span class="num">{r.value:.0f}</span>
          <span class="st {r.state}">{E((r.state or "").title())}</span></div>
          <div class="kv"><span>Volume (in SOL/ETH), percentile</span><span class="num">
          {d.get("s_V") or 0:.0f}</span></div>
          <div class="kv"><span>Active wallets, percentile</span><span class="num">
          {"—" if d.get("s_P") is None else f'{d["s_P"]:.0f}'}</span></div>{sline}{div}</article>''')
    parts.append(section(
        "market", f"Activity by chain (as of {act.as_of.max():%d %b %Y})", "desc",
        f'<div class="grid">{"".join(cards)}</div>',
        "Description only: high and low readings were not followed by different 14-day "
        "returns (2023–2026), and the state changed every four days on median. Sentiment "
        "is the ratio of sale value to purchase cost on organic sells: above 1 means holders "
        "are selling at a profit. Robinhood Chain is ranked once it has 180 days of history."))

    rot = _latest(pit, "chain_rotation")
    parts.append(section("rotation", "Chain rotation", "desc", table(
        ["Chain", "Share of DEX volume", "Relative strength", "Momentum", "Quadrant"],
        [[E(r.entity.split("=")[1].title()), pct(r.d.get("share"), 1),
          f'{r.d.get("rs_ratio", 0):.1f}', f'{r.d.get("rs_momentum", 0):.1f}',
          E((r.state or "").title())] for r in rot.sort_values("value",
                                                               ascending=False).itertuples()],
        right=(1, 2, 3)),
        "Description only: across 505 chain-weeks, chains labelled Leading lost share over the "
        "next two weeks relative to Lagging chains. Share has reverted, not trended."))

    cap = _latest(pit, "capital_inflow")
    perps = _latest(pit, "meme_perps")
    org = _latest(pit, "organic_ratio")
    parts.append(section("money", "Money moving in or out", "nv", table(
        ["Chain", "Stablecoins on chain", "7-day change"],
        [[E(r.entity.split("=")[1].title()), usd(r.d.get("stablecoins_usd"), 2),
          f'{pct(r.d.get("change_7d"), 1, True)} ({usd(r.value)})'] for r in cap.itertuples()],
        right=(1, 2)) + "<h3 class='sub'>Meme perpetuals on Hyperliquid</h3>" + table(
        ["Contract", "Open interest", "Funding, annualised", "Funding vs last 30 days"],
        [[E(r.entity.split("=")[1]), usd(r.d.get("open_interest_usd")), pct(r.value, 1, True),
          "—" if r.d.get("funding_pct_30d") is None else f'{r.d["funding_pct_30d"]:.0f}th pct']
         for r in perps.sort_values("value").itertuples()
         if r.d.get("open_interest_usd", 0) >= 1e6][:12], right=(1, 2, 3)) +
        "<h3 class='sub'>How much activity is real</h3>" + table(
        ["Chain", "Organic share of USD", "Organic share of swaps", "Swaps measured"],
        [[E(r.entity.split("=")[1].title()), pct(r.value),
          pct(r.d.get("organic_share_swaps")), f'{r.d.get("swaps") or r.d.get("trades") or 0:,}']
         for r in org.itertuples()], right=(1, 2, 3)),
        "A few very large automated round trips can dominate dollar volume, which is why the "
        "share of swaps and the share of dollars differ."))

    # Flow
    rfm = _latest(pit, "retail_flow_market")
    m = rfm.iloc[0] if len(rfm) else None
    flow_body = ""
    if m is not None:
        tick = m.d.get("avg_ticket", {})
        flow_body = (f'<div class="stats"><div><span class="num big2">{pct(m.value, 1)}</span>'
                     f'<span>of trading-terminal volume came from consumer apps '
                     f'({m.d.get("day", "")[:10]})</span></div><div><span class="num big2">'
                     f'{m.d.get("consumer_share_z_90d", 0):+.1f}σ</span><span>versus the '
                     f'last 90 days</span></div><div><span class="num big2">'
                     + " / ".join(f"${v:,.0f}" for v in tick.values()) +
                     f'</span><span>average ticket: {" / ".join(E(k) for k in tick)}</span>'
                     '</div></div>')
    parts.append(section("flow", "Retail flow", "nv", flow_body,
                         "Consumer apps are fomo and the pump.fun app; pro terminals are Axiom, "
                         "GMGN, Photon, Padre and similar; Telegram bots are Trojan, Maestro, "
                         "Bonkbot and Basedbot. Source: tehcscreener.com."))

    # Coins (Solana)
    qf = _latest(pit, "quality_flow")
    cbm = {r.entity: r for r in _latest(pit, "cost_basis_map").itertuples()}
    rft = {r.entity: r for r in _latest(pit, "retail_flow_tokens").itertuples()}
    cof = {r.entity: r for r in _latest(pit, "cohort_flow").itertuples()}
    rows, excluded = [], []
    for r in qf.itertuples():
        c = cbm.get(r.entity)
        if c is None or c.d.get("price") is None or 0.97 <= c.d["price"] <= 1.03:
            continue
        s, mc, liq = sym.get(r.entity, ("?", None, None))
        if bucket(s) != "meme":
            excluded.append(f"{s} ({bucket(s)})")
            continue
        f = rft.get(r.entity)
        co = cof.get(r.entity)
        smart = (co.d.get("nf_bps") or {}).get("SMART") if co is not None else None
        rows.append((mc or 0, [E(s or "?"), usd(mc), f'<span class="st {r.state.split()[0].lower()}">'
                               f'{E(r.state)}</span>', f"{r.value:.0f}", pct(c.value),
                     pct(c.d.get("overhang_vs_price"), 0, True),
                     E(f.state or "—") if f is not None else "—",
                     "—" if smart is None else f"{smart:+.1f}",
                     pct(r.d.get("insider_share")), pct(r.d.get("top10_share"))]))
    rows = [r for _, r in sorted(rows, key=lambda x: -x[0])]
    parts.append(section("coins", f"Solana coins ({len(rows)})", "nv", table(
        ["Coin", "Market cap", "Setup", "Quality", "Supply in profit", "Loss-holders' cost vs price",
         "Retail flag", "Smart flow (bps)", "Insider share", "Top-10 share"], rows,
        right=(1, 3, 4, 5, 7, 8, 9)),
        "Setup combines Quality (low insider share, low concentration, exit cover) with Flow "
        "(net buying by smart wallets and whales). Quality is ranked against today's coins, a "
        "provisional calibration set; StressHold, Tenure and Breadth join as history builds. "
        "Supply in profit and the cost of holders at a loss come from the top 100 holders' cost "
        "basis; a large positive gap marks supply likely to sell into a recovery. Source: GMGN. "
        + (f"Not memecoins, shown elsewhere: {E(', '.join(excluded))}." if excluded else "")))

    bot = _latest(pit, "bottom_eligible")
    brows = []
    for r in bot.sort_values("value").itertuples():
        s, mc, liq = sym.get(r.entity, ("?", None, None))
        brows.append([E(s or "?"), E(r.entity.split(":")[0].title()), pct(r.value, 0, True),
                      usd(liq), usd(mc)])
    parts.append(section("bottoms", f"Coins at least 50% below their 90-day high ({len(brows)})",
                         "pending", table(["Coin", "Chain", "From 90-day high", "Liquidity",
                                           "Market cap"], brows[:40], right=(2, 3, 4)),
                         "These coins are eligible for Bottom Probability. The probability "
                         "itself is not shown until the model is trained and calibrated."))

    # Launchpads
    lp = lake.connect().execute(
        "SELECT * FROM lp_launch_outcomes QUALIFY row_number() OVER (PARTITION BY pad, token "
        "ORDER BY fetched_at DESC) = 1").df() if "lp_launch_outcomes" in lake.tables() else None
    lrows = []
    if lp is not None and len(lp):
        for (pad, day), g in lp.groupby(["pad", "cohort_day"]):
            ls = g[g.lstar.astype(bool)]
            top5 = g.creator.value_counts().head(5).sum() / len(g)
            lrows.append([E(pad), f"{pd.Timestamp(day):%d %b}", f"{len(g):,}",
                          pct(1 - len(ls) / len(g)), f"{top5:.0%}", f"{len(ls)}",
                          f'{int(ls.grad.sum())}', f'{int(ls.surv7.sum())}',
                          f'{int(ls.runner.sum())}',
                          f'{int(ls.rug.sum())}', pct(ls.buyret.median(), 0, True)])
    parts.append(section("launchpads", "Launchpads: what happens to buyers", "nv", table(
        ["Launchpad", "Cohort", "Launches", "Spam", "Top-5 creators", "Real launches",
         "$100K in 24h", "Alive at day 7", "$1M", "Creator sold early", "Buyer 24h return"],
        lrows, right=tuple(range(2, 11))),
        "Not ranked until four launchpads and four weekly cohorts exist. A real launch has at "
        "least ten wallets other than the creator buying in its first hour."))

    # Status
    st = json.loads(status_path.read_text()) if status_path.exists() else []
    kind = lambda s: ("desc" if s.startswith("Description") else "pending" if  # noqa: E731
                      s.startswith("Pending") else "signal" if s == "Signal" else "nv")
    parts.append(section("status", "Every indicator and its status", "nv", table(
        ["Group", "Indicator", "Status", "Current reading"],
        [[E(x["group"]), E(x["name"]), badge(kind(x["status"])), E(x["reading"])] for x in st])))

    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in (
        ("market", "Market"), ("money", "Money"), ("flow", "Flow"), ("coins", "Coins"),
        ("bottoms", "Bottoms"), ("launchpads", "Launchpads"), ("status", "Status")))
    return PAGE.format(nav=nav, updated=f"{now:%d %b %Y, %H:%M} UTC", body="".join(parts))


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trench Research</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap" rel="stylesheet">
<style>
:root{{--ink:#0B1F3A;--blue:#1F4E79;--slate:#334155;--muted:#556477;--rule:#E2E8F0;--paper:#F7F8FA}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--slate);font:15px/1.55 'IBM Plex Sans',system-ui,sans-serif}}
header{{background:var(--ink);color:#fff;position:sticky;top:0;z-index:2}}
.hw{{max-width:1240px;margin:0 auto;padding:12px 24px;display:flex;flex-wrap:wrap;gap:10px 28px;align-items:center;justify-content:space-between}}
.logo{{font:600 20px 'Source Serif 4',Georgia,serif}}nav{{display:flex;flex-wrap:wrap;gap:4px 20px;font-size:14px}}
nav a{{color:#C7D2E0;text-decoration:none}}nav a:hover{{color:#fff}}.upd{{font:12px 'IBM Plex Mono',monospace;color:#C7D2E0}}
main{{max-width:1240px;margin:0 auto;padding:32px 24px 56px;display:flex;flex-direction:column;gap:40px}}
h1{{margin:0;font:600 36px/1.15 'Source Serif 4',Georgia,serif;color:var(--ink)}}
.lead{{max-width:820px;font-size:16px;margin:10px 0 0}}
.sh{{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline;justify-content:space-between;margin-bottom:14px}}
h2{{margin:0;font:600 24px 'Source Serif 4',Georgia,serif;color:var(--ink)}}h3.sub{{margin:22px 0 10px;font-size:16px;color:var(--ink)}}
.badge{{padding:2px 8px;border-radius:3px;font-size:12px;font-weight:600;white-space:nowrap}}
.note{{max-width:900px;font-size:13.5px;color:#475569;margin:12px 0 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}
.card{{background:#fff;border:1px solid var(--rule);border-radius:6px;padding:18px;display:flex;flex-direction:column;gap:8px}}
.card h3{{margin:0;font-size:16px;color:var(--ink)}}.ct{{display:flex;justify-content:space-between;align-items:baseline}}
.card p{{margin:4px 0 0;font-size:13.5px}}.big{{display:flex;gap:10px;align-items:baseline}}.big .num{{font-size:38px;color:var(--ink)}}
.kv{{display:flex;justify-content:space-between;font-size:13px}}.num{{font-family:'IBM Plex Mono',monospace}}
.muted{{color:var(--muted);font-size:12px}}.st{{font-weight:600;font-size:13px}}
.st.hot,.st.accumulation,.st.leading{{color:#2E7D5B}}.st.cold{{color:var(--blue)}}.st.avoid{{color:#A23B3B}}
.st.distribution{{color:#B5562A}}.st.speculative{{color:var(--blue)}}
.tw{{background:#fff;border:1px solid var(--rule);border-radius:6px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}th{{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);font-weight:600;padding:10px 14px;border-bottom:1px solid var(--rule);white-space:nowrap}}
td{{padding:9px 14px;border-bottom:1px solid #EEF2F6;vertical-align:top}}td.r,th.r{{text-align:right}}td.num{{white-space:nowrap}}
.stats{{display:flex;flex-wrap:wrap;gap:16px}}.stats>div{{flex:1 1 240px;background:#fff;border:1px solid var(--rule);border-radius:6px;padding:18px;display:flex;flex-direction:column;gap:4px}}
.big2{{font-size:30px;color:var(--ink)}}
footer{{border-top:1px solid var(--rule);background:#fff}}.fw{{max-width:1240px;margin:0 auto;padding:20px 24px;display:flex;flex-wrap:wrap;gap:8px 28px;justify-content:space-between;font-size:13px;color:var(--muted)}}
</style></head><body>
<header><div class="hw"><div class="logo">Trench Research</div><nav>{nav}</nav><div class="upd">Updated {updated}</div></div></header>
<main><div><h1>Today in the trenches</h1>
<p class="lead">Every reading below is computed from on-chain and market data and stored as it was published. A badge on each section says whether it has earned signal status. None has yet: readings marked "not yet validated" have too little history to test, and "description only" readings failed their backtest.</p></div>
{body}</main>
<footer><div class="fw"><strong style="color:#334155">Research, not financial advice.</strong><span>Sources: tehcscreener.com, DefiLlama, GeckoTerminal, DexScreener, GMGN, Hyperliquid and public RPCs. Private research tool.</span></div></footer>
</body></html>"""
