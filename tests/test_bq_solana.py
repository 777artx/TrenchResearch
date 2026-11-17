from datetime import UTC, datetime

import pytest

from trench.sources import bq_solana


class _Job:
    def __init__(self, gb):
        self.total_bytes_processed = int(gb * 1e9)


class _FakeBQ:
    def __init__(self, gb):
        self.gb, self.real_queries = gb, 0

    def query(self, sql, job_config=None):
        if job_config is not None and job_config.dry_run:
            return _Job(self.gb)
        self.real_queries += 1
        raise AssertionError("real query must not run when over budget")


def test_budget_guard_refuses_before_running():
    bq = _FakeBQ(gb=480)
    t0, t1 = datetime(2026, 11, 16, tzinfo=UTC), datetime(2026, 11, 17, tzinfo=UTC)
    with pytest.raises(bq_solana.BudgetExceeded):
        bq_solana.extract_transfers(bq, t0, t1, ["Mint1"], max_gb=25)
    assert bq.real_queries == 0


def test_requires_mints():
    with pytest.raises(ValueError):
        bq_solana.extract_transfers(_FakeBQ(1), datetime.now(UTC), datetime.now(UTC), [])
