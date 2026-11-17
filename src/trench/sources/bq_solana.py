"""Solana token transfers from Google's public BigQuery dataset.

``bigquery-public-data.crypto_solana_mainnet_us.Token Transfers`` holds every SPL
and native SOL transfer, partitioned by day on ``block_timestamp``. One day costs
about 19 GB of scanning; the free tier is 1 TB a month. The much richer
``Transactions`` table costs ~480 GB a day and is not usable on the free tier.

Every query is dry-run first and refused if it would scan more than the budget.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyarrow as pa

TABLE = "bigquery-public-data.crypto_solana_mainnet_us.Token Transfers"
DEFAULT_KEY = Path.home() / ".config" / "trench" / "gcp-sa.json"

# All rows of every transaction in which at least one transfer moves a tracked mint.
# One scan of the window; the window function keeps the quote legs (SOL, USDC, and
# transfers without a mint) that belong to those transactions.
EXTRACT_SQL = f"""
SELECT block_slot, block_timestamp, tx_signature, source, destination, authority,
       value, decimals, mint, transfer_type
FROM `{TABLE}`
WHERE block_timestamp >= @start AND block_timestamp < @end
QUALIFY LOGICAL_OR(mint IN UNNEST(@mints)) OVER (PARTITION BY tx_signature)
"""


# Hard monthly cap, kept well under the 1 TB free tier so nothing is ever billed even
# if billing were enabled on the project. Counted from our own extract log.
MONTHLY_CAP_GB = 800.0


class BudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class ExtractResult:
    table: pa.Table
    bytes_processed: int
    bytes_billed: int
    job_id: str
    sql: str


def client(key_path: Path | None = None):
    from google.cloud import bigquery
    from google.oauth2 import service_account

    key = Path(key_path or os.environ.get("TRENCH_GCP_KEY", DEFAULT_KEY))
    creds = service_account.Credentials.from_service_account_file(str(key))
    return bigquery.Client(credentials=creds, project=creds.project_id)


def extract_transfers(
    bq, start: datetime, end: datetime, mints: list[str], *, max_gb: float = 25.0,
    used_this_month_gb: float = 0.0, monthly_cap_gb: float = MONTHLY_CAP_GB,
) -> ExtractResult:
    from google.cloud import bigquery

    if not mints:
        raise ValueError("no mints to extract")
    params = [
        bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
        bigquery.ScalarQueryParameter("end", "TIMESTAMP", end),
        bigquery.ArrayQueryParameter("mints", "STRING", sorted(set(mints))),
    ]
    dry = bq.query(
        EXTRACT_SQL,
        job_config=bigquery.QueryJobConfig(query_parameters=params, dry_run=True,
                                           use_query_cache=False),
    )
    gb = dry.total_bytes_processed / 1e9
    if gb > max_gb:
        raise BudgetExceeded(f"query would scan {gb:.1f} GB > per-query budget {max_gb} GB")
    if used_this_month_gb + gb > monthly_cap_gb:
        raise BudgetExceeded(
            f"query would bring this month to {used_this_month_gb + gb:.0f} GB "
            f"> monthly cap {monthly_cap_gb:.0f} GB"
        )
    job = bq.query(EXTRACT_SQL, job_config=bigquery.QueryJobConfig(query_parameters=params))
    tbl = job.result().to_arrow()
    return ExtractResult(tbl, job.total_bytes_processed or 0, job.total_bytes_billed or 0,
                         job.job_id, EXTRACT_SQL)
