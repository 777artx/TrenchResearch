"""Write-once Parquet lake with knowledge-time ("as-of") reads.

Layout: ``lake/<table>/fetched_date=YYYY-MM-DD/<run_id>.parquet``.

Every row carries ``fetched_at`` (when we learned it) and ``run_id``. Files
are never overwritten or deleted, so an upstream that revises its history
(TEHscreener recomputed its index on 2026-11-12) shows up as new rows with a
later ``fetched_at`` rather than as a silent overwrite. Backtests read with
``as_of`` so they only see what was known at the time.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"invalid identifier: {name!r}")
    return name


class Lake:
    def __init__(self, root: Path):
        self.root = Path(root)

    # ---- writes -----------------------------------------------------------------
    def write(
        self,
        table: str,
        rows: Sequence[dict] | pa.Table,
        *,
        run_id: str,
        fetched_at: datetime,
        schema: pa.Schema | None = None,
    ) -> Path | None:
        _check_ident(table)
        tbl = (
            rows if isinstance(rows, pa.Table) else pa.Table.from_pylist(list(rows), schema=schema)
        )
        if tbl.num_rows == 0:
            return None
        n = tbl.num_rows
        tbl = tbl.append_column(
            "fetched_at", pa.array([fetched_at] * n, pa.timestamp("us", tz="UTC"))
        )
        tbl = tbl.append_column("run_id", pa.array([run_id] * n, pa.string()))
        part = self.root / table / f"fetched_date={fetched_at:%Y-%m-%d}"
        part.mkdir(parents=True, exist_ok=True)
        path = part / f"{run_id}.parquet"
        # Exclusive create: a run can write a table partition once, never twice.
        with open(path, "xb") as fh:
            pq.write_table(tbl, fh, compression="zstd")
        return path

    # ---- reads ------------------------------------------------------------------
    def tables(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            p.name for p in self.root.iterdir() if p.is_dir() and any(p.rglob("*.parquet"))
        )

    def connect(self, con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
        """DuckDB connection with one view per lake table (all versions, all fetches)."""
        con = con or duckdb.connect()
        con.execute("SET TimeZone='UTC'")
        for t in self.tables():
            glob = str(self.root / t / "**" / "*.parquet").replace("'", "''")
            con.execute(
                f"CREATE OR REPLACE VIEW {t} AS SELECT * EXCLUDE (fetched_date) FROM "
                f"read_parquet('{glob}', hive_partitioning=true, union_by_name=true)"
            )
        return con

    def as_of(
        self,
        table: str,
        keys: Sequence[str],
        as_of: datetime | None = None,
        con: duckdb.DuckDBPyConnection | None = None,
    ) -> duckdb.DuckDBPyRelation:
        """Latest known version of each key, using only rows fetched at or before ``as_of``."""
        _check_ident(table)
        for k in keys:
            _check_ident(k)
        con = self.connect(con)
        where = "WHERE fetched_at <= $as_of" if as_of is not None else ""
        part = ", ".join(keys)
        sql = (
            f"SELECT * FROM {table} {where} "
            f"QUALIFY row_number() OVER "
            f"(PARTITION BY {part} ORDER BY fetched_at DESC, run_id DESC) = 1"
        )
        params = {"as_of": as_of} if as_of is not None else {}
        return con.sql(sql, params=params)


def changed_rows(lake: Lake, table: str, rows: list[dict], keys: Sequence[str],
                 ignore: Sequence[str] = ("raw_sha256",)) -> list[dict]:
    """Rows that are new or differ from the latest stored version of their key.

    Sources such as TEHscreener and DefiLlama return their full history on every
    call. Storing only changed rows keeps the lake small without losing anything:
    an unchanged row's latest version is still the right answer for any later
    cutoff, and a revised row is stored as a new version, so revisions stay visible.
    """
    if not rows or table not in lake.tables():
        return list(rows)
    new = pa.Table.from_pylist([{**r, "_i": i} for i, r in enumerate(rows)])
    con = lake.connect()
    stored_cols = {c for (c,) in con.execute(
        f"SELECT column_name FROM (DESCRIBE {_check_ident(table)})").fetchall()}
    cols = [c for c in new.column_names if c not in (*ignore, "_i")]
    if any(c not in stored_cols for c in cols) or any(k not in cols for k in keys):
        return list(rows)  # schema grew or keys absent: store everything
    for k in keys:
        _check_ident(k)
    latest = lake.as_of(table, keys).fetch_arrow_table()  # own connection, fully read
    con.register("_latest", latest)
    con.register("_new", new)
    # IS NOT DISTINCT FROM treats NULL = NULL as equal.
    match = " AND ".join(f'n."{c}" IS NOT DISTINCT FROM l."{c}"' for c in cols)
    keep = {i for (i,) in con.execute(
        f"SELECT n._i FROM _new n WHERE NOT EXISTS (SELECT 1 FROM _latest l WHERE {match})"
    ).fetchall()}
    return [r for i, r in enumerate(rows) if i in keep]
