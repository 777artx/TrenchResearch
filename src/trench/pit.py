"""Point-in-time store for published metric values (SPEC §5.6).

Rules enforced here:

* Append-only. Values are written once per publish; nothing is updated or deleted.
* Every row records ``formula_version``, ``input_cutoff`` and ``published_at``.
* ``input_cutoff`` may not be later than ``published_at`` (no look-ahead at publish).
* Re-publishing a value that already exists for the same metric, entity, date and
  formula version is refused unless a ``restatement_reason`` is given. A restatement
  is a new row; the original stays readable, so history is never silently recomputed.
* A new formula version is published alongside the old one, not over it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa

from trench.lake import Lake, _check_ident
from trench.timeutil import utcnow

SCHEMA = pa.schema(
    [
        ("metric", pa.string()),
        ("entity", pa.string()),
        ("as_of", pa.date32()),
        ("value", pa.float64()),
        ("state", pa.string()),
        ("formula_version", pa.string()),
        ("input_cutoff", pa.timestamp("us", tz="UTC")),
        ("published_at", pa.timestamp("us", tz="UTC")),
        ("restatement_reason", pa.string()),
        ("detail", pa.string()),
    ]
)


class PublishError(Exception):
    pass


@dataclass(frozen=True)
class Reading:
    entity: str
    as_of: date
    value: float | None
    state: str | None = None
    detail: dict = field(default_factory=dict)


class PITStore:
    def __init__(self, root: Path):
        self.lake = Lake(Path(root))

    def publish(
        self,
        metric: str,
        readings: Sequence[Reading],
        *,
        formula_version: str,
        input_cutoff: datetime,
        restatement_reason: str | None = None,
        published_at: datetime | None = None,
    ) -> int:
        _check_ident(metric)
        published_at = published_at or utcnow()
        if input_cutoff.tzinfo is None or published_at.tzinfo is None:
            raise PublishError("input_cutoff and published_at must be timezone-aware UTC")
        if input_cutoff > published_at:
            raise PublishError("input_cutoff is after published_at: that is look-ahead")
        if not readings:
            return 0
        keys = [(r.entity, r.as_of) for r in readings]
        if len(set(keys)) != len(keys):
            raise PublishError("duplicate (entity, as_of) within one publish")

        if restatement_reason is None and metric in self.lake.tables():
            con = self.lake.connect()
            con.execute("CREATE TEMP TABLE k(entity VARCHAR, as_of DATE)")
            con.executemany("INSERT INTO k VALUES (?, ?)", keys)
            clash = con.execute(
                f"SELECT p.entity, p.as_of FROM {metric} p JOIN k USING (entity, as_of) "
                "WHERE p.formula_version = ? LIMIT 5",
                [formula_version],
            ).fetchall()
            if clash:
                raise PublishError(
                    f"{metric} v{formula_version} already published for {clash}; "
                    "pass restatement_reason to publish a correction"
                )

        rows = [
            {
                "metric": metric,
                "entity": r.entity,
                "as_of": r.as_of,
                "value": r.value,
                "state": r.state,
                "formula_version": formula_version,
                "input_cutoff": input_cutoff,
                "published_at": published_at,
                "restatement_reason": restatement_reason,
                "detail": json.dumps(r.detail, sort_keys=True, default=str) if r.detail else None,
            }
            for r in readings
        ]
        run_id = f"{published_at:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}"
        self.lake.write(metric, rows, run_id=run_id, fetched_at=published_at, schema=SCHEMA)
        return len(rows)

    def read(
        self,
        metric: str,
        *,
        known_at: datetime | None = None,
        formula_version: str | None = None,
    ) -> duckdb.DuckDBPyRelation:
        """Values as they were known at ``known_at`` (latest publish per entity and date)."""
        _check_ident(metric)
        con = self.lake.connect()
        conds, params = [], {}
        if known_at is not None:
            conds.append("published_at <= $known_at")
            params["known_at"] = known_at
        if formula_version is not None:
            conds.append("formula_version = $fv")
            params["fv"] = formula_version
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        part = "entity, as_of" if formula_version else "entity, as_of, formula_version"
        return con.sql(
            f"SELECT * EXCLUDE (fetched_at, run_id) FROM {metric} {where} "
            f"QUALIFY row_number() OVER (PARTITION BY {part} ORDER BY published_at DESC) = 1 "
            "ORDER BY entity, as_of",
            params=params,
        )
