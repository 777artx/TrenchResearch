"""Command-line entry point: ``uv run trench --help``."""

from __future__ import annotations

import json
import logging

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


@app.command()
def daily() -> None:
    """The daily job. Phase 0: ingest every wired source."""
    ingest_tehcscreener()


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
def sql(query: str) -> None:
    """Run SQL against the lake views (all fetched versions)."""
    s = Settings.from_env()
    Lake(s.lake_dir).connect().sql(query).show(max_rows=50)
