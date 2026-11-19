"""Command-line entry point: ``uv run trench --help``."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from trench.config import Settings
from trench.lake import Lake
from trench.rawstore import RawStore

app = typer.Typer(no_args_is_help=True, add_completion=False)
ingest_app = typer.Typer(no_args_is_help=True, help="Fetch upstream data into the lake.")
app.add_typer(ingest_app, name="ingest")


@app.callback()
def _main(verbose: bool = typer.Option(False, "-v", "--verbose")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@ingest_app.command("tehcscreener")
def ingest_tehcscreener() -> None:
    """Full refresh of every TEHscreener endpoint (about 120 requests)."""
    from trench.ingest import tehcscreener

    s = Settings.from_env()
    report = tehcscreener.run(Lake(s.lake_dir), RawStore(s.raw_dir))
    typer.echo(json.dumps(report.__dict__, indent=2))


@ingest_app.command("markets")
def ingest_markets(
    ohlcv_budget: int = typer.Option(150, help="GeckoTerminal OHLCV requests this run."),
) -> None:
    """Discover tokens, snapshot DexScreener pairs, backfill GeckoTerminal daily OHLCV."""
    from trench.ingest import markets

    s = Settings.from_env()
    cfg = markets.MarketsConfig(ohlcv_budget=ohlcv_budget)
    report = markets.run(Lake(s.lake_dir), RawStore(s.raw_dir), cfg)
    out = dict(report.__dict__)
    out["errors"] = report.errors[:20] + ([f"... {len(report.errors) - 20} more"]
                                          if len(report.errors) > 20 else [])
    typer.echo(json.dumps(out, indent=2))


@ingest_app.command("defillama")
def ingest_defillama() -> None:
    """Daily DEX volume per active chain from DefiLlama (full history)."""
    from trench.ingest import defillama

    s = Settings.from_env()
    typer.echo(json.dumps(defillama.run(Lake(s.lake_dir), RawStore(s.raw_dir))))


@ingest_app.command("trades")
def ingest_trades(
    cycles: int = typer.Option(1, help="Polling cycles to run back to back."),
) -> None:
    """Poll GeckoTerminal recent trades for every universe pool (one request per pool)."""
    from trench.ingest import trades
    from trench.pit import PITStore

    s = Settings.from_env()
    lake, raw, pit = Lake(s.lake_dir), RawStore(s.raw_dir), PITStore(s.lake_dir / "published")
    for _ in range(cycles):
        r = trades.run_cycle(lake, raw, pit)
        typer.echo(json.dumps({**r.__dict__, "errors": r.errors[:5]}, default=str))


@ingest_app.command("evm-swaps")
def ingest_evm_swaps(
    chain: list[str] = typer.Option(["robinhood", "base", "ethereum"]),
    days_back: float = typer.Option(2.0, help="History on a pool's first sight."),
) -> None:
    """Swap logs for universe pools from public RPCs, with the trader of each swap."""
    from trench.ingest import evm_swaps
    from trench.pit import PITStore

    s = Settings.from_env()
    lake, pit = Lake(s.lake_dir), PITStore(s.lake_dir / "published")
    for c in chain:
        r = evm_swaps.run(lake, pit, c, days_back=days_back)
        typer.echo(json.dumps(r.__dict__, default=str))


@ingest_app.command("gmgn")
def ingest_gmgn() -> None:
    """Solana trades, holders and smart-wallet ranks from GMGN (headless browser)."""
    from trench.ingest import gmgn
    from trench.pit import PITStore

    s = Settings.from_env()
    rep = gmgn.run(Lake(s.lake_dir), RawStore(s.raw_dir), PITStore(s.lake_dir / "published"))
    typer.echo(json.dumps(rep))


@app.command("universe")
def universe_build() -> None:
    """Publish new universe entries from the snapshots fetched so far."""
    from trench import universe
    from trench.pit import PITStore

    s = Settings.from_env()
    n = universe.build(Lake(s.lake_dir), PITStore(s.lake_dir / "published"))
    typer.echo(f"published {n} new universe entries")


@app.command()
def daily() -> None:
    """The daily job. Each step runs even if an earlier one failed; the command exits
    non-zero at the end if any step failed, so the failure shows in GitHub Actions
    while everything collected is still saved."""
    import logging
    import traceback

    steps = [
        ("tehcscreener", ingest_tehcscreener),
        ("defillama", ingest_defillama),
        # markets reads TEHscreener's top tokens, so it runs after it
        ("markets", lambda: ingest_markets(ohlcv_budget=30)),
        ("universe", universe_build),
        # Ethereum first: the busiest chain (Robinhood) last, so it cannot starve the others.
        ("evm-swaps", lambda: ingest_evm_swaps(chain=["ethereum", "base", "robinhood"],
                                               days_back=2.0)),
        ("gmgn", ingest_gmgn),
        ("indicators", indicators),
        ("site", lambda: site(out="data/site/index.html")),
        ("usage", usage),
    ]
    failed = []
    for name, fn in steps:
        logging.getLogger("trench.daily").info("step %s", name)
        try:
            fn()
        except Exception:
            failed.append(name)
            traceback.print_exc()
    if failed:
        typer.echo(f"failed steps: {failed}", err=True)
        raise typer.Exit(1)


@app.command()
def tables() -> None:
    """List lake tables with row counts and the latest fetch."""
    s = Settings.from_env()
    lake = Lake(s.lake_dir)
    con = lake.connect()
    for t in lake.tables():
        n, last, runs = con.execute(
            f"SELECT count(*), max(fetched_at), count(DISTINCT run_id) FROM {t}"
        ).fetchone()
        typer.echo(f"{t:32s} rows={n:>9,d} runs={runs:>3d} last_fetch={last}")


@app.command()
def indicators() -> None:
    """Compute and publish every v0 indicator; write docs/indicators/STATUS.md."""
    from trench.indicators import run_v0
    from trench.pit import PITStore

    s = Settings.from_env()
    rows = run_v0.run(Lake(s.lake_dir), PITStore(s.lake_dir / "published"),
                      Path("docs/indicators/STATUS.md"))
    for g, n, st, r in rows:
        typer.echo(f"[{g}] {n} | {st} | {r}")


@app.command()
def site(out: str = typer.Option("site/index.html")) -> None:
    """Build the research site from published readings."""
    from trench import site as S
    from trench.pit import PITStore

    s = Settings.from_env()
    html_ = S.build(Lake(s.lake_dir), PITStore(s.lake_dir / "published"),
                    Path("docs/indicators/status.json"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(html_)
    typer.echo(f"wrote {out} ({len(html_):,} bytes)")


@app.command()
def usage() -> None:
    """This month's metered usage against our caps and the free allowances."""
    from trench.usage import Ledger

    for name, r in Ledger(Settings.from_env().data_dir).report().items():
        pct = 100 * r["used"] / r["allowance"]
        typer.echo(f"{name:8s} {r['used']:>12,.0f} / cap {r['cap']:>12,.0f} {r['unit']}"
                   f"  ({pct:.1f}% of free allowance)")
    from trench.ingest.solana_transfers import gb_used_this_month

    gb = gb_used_this_month(Lake(Settings.from_env().lake_dir))
    typer.echo(f"bigquery {gb:>12,.1f} / cap {800:>12,} GB (logged extracts only)")


@app.command()
def sql(query: str) -> None:
    """Run SQL against the lake views (all fetched versions) and published metrics."""
    s = Settings.from_env()
    con = Lake(s.lake_dir).connect()
    Lake(s.lake_dir / "published").connect(con).sql(query).show(max_rows=50)
