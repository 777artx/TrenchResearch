from datetime import UTC, date, datetime, timedelta

import pytest

from trench.lake import Lake
from trench.pit import PITStore, PublishError, Reading

T0 = datetime(2026, 11, 10, 6, tzinfo=UTC)
T1 = T0 + timedelta(days=2)


def test_lake_is_write_once_per_run(tmp_path):
    lake = Lake(tmp_path)
    lake.write("t", [{"day": date(2026, 1, 1), "v": 1.0}], run_id="r1", fetched_at=T0)
    with pytest.raises(FileExistsError):
        lake.write("t", [{"day": date(2026, 1, 1), "v": 2.0}], run_id="r1", fetched_at=T0)


def test_as_of_sees_only_what_was_known(tmp_path):
    """Upstream revises day D between two fetches; a backtest at T0 must see the old value."""
    lake = Lake(tmp_path)
    d = date(2026, 11, 1)
    lake.write("score", [{"day": d, "v": 45.0}], run_id="a", fetched_at=T0)
    lake.write(
        "score",
        [{"day": d, "v": 30.0}, {"day": d + timedelta(1), "v": 31.0}],
        run_id="b",
        fetched_at=T1,
    )

    before = lake.as_of("score", ["day"], as_of=T0 + timedelta(hours=1)).fetchall()
    assert [(r[0], r[1]) for r in before] == [(d, 45.0)]
    latest = dict((r[0], r[1]) for r in lake.as_of("score", ["day"]).fetchall())
    assert latest == {d: 30.0, d + timedelta(1): 31.0}
    # every version stays readable
    assert lake.connect().execute("SELECT count(*) FROM score").fetchone()[0] == 3


def test_identifiers_are_validated(tmp_path):
    with pytest.raises(ValueError):
        Lake(tmp_path).write("bad; drop", [{"a": 1}], run_id="r", fetched_at=T0)


def test_pit_rejects_lookahead_and_naive_times(tmp_path):
    pit = PITStore(tmp_path)
    r = [Reading("chain=solana", date(2026, 11, 9), 50.0)]
    with pytest.raises(PublishError):
        pit.publish("activity", r, formula_version="1", input_cutoff=T1, published_at=T0)
    with pytest.raises(PublishError):
        pit.publish("activity", r, formula_version="1", input_cutoff=T0.replace(tzinfo=None))


def test_pit_append_only_with_explicit_restatement(tmp_path):
    pit = PITStore(tmp_path)
    d = date(2026, 11, 9)
    pit.publish(
        "activity",
        [Reading("chain=solana", d, 50.0, state="hot")],
        formula_version="1",
        input_cutoff=T0,
        published_at=T0,
    )
    with pytest.raises(PublishError):
        pit.publish(
            "activity",
            [Reading("chain=solana", d, 40.0)],
            formula_version="1",
            input_cutoff=T0,
            published_at=T1,
        )

    pit.publish(
        "activity",
        [Reading("chain=solana", d, 40.0)],
        formula_version="1",
        input_cutoff=T0,
        published_at=T1,
        restatement_reason="bad price feed on 11-09",
    )
    # A new formula version is published alongside, never over, the old one.
    pit.publish(
        "activity",
        [Reading("chain=solana", d, 55.0)],
        formula_version="2",
        input_cutoff=T0,
        published_at=T1,
    )

    as_known_at_T0 = pit.read("activity", known_at=T0, formula_version="1").fetchall()
    assert len(as_known_at_T0) == 1 and as_known_at_T0[0][3] == 50.0
    now_v1 = pit.read("activity", formula_version="1").fetchall()
    assert now_v1[0][3] == 40.0 and now_v1[0][8] == "bad price feed on 11-09"
    assert len(pit.read("activity").fetchall()) == 2  # one per formula version
    assert pit.lake.connect().execute("SELECT count(*) FROM activity").fetchone()[0] == 3


def test_changed_rows_keeps_new_and_revised_only(tmp_path):
    from trench.lake import changed_rows

    lake = Lake(tmp_path)
    d1, d2, d3 = date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)
    lake.write("s", [{"day": d1, "v": 1.0, "raw_sha256": "a"}, {"day": d2, "v": 2.0,
                                                                 "raw_sha256": "a"}],
               run_id="r1", fetched_at=T0)
    rows = [{"day": d1, "v": 1.0, "raw_sha256": "b"},   # unchanged (only lineage differs)
            {"day": d2, "v": 2.5, "raw_sha256": "b"},   # revised upstream
            {"day": d3, "v": 3.0, "raw_sha256": "b"}]   # new
    keep = changed_rows(lake, "s", rows, ["day"])
    assert [r["day"] for r in keep] == [d2, d3]
    lake.write("s", keep, run_id="r2", fetched_at=T1)
    # As of T0 the revision is invisible; afterwards it is the latest version.
    old = {r[0]: r[1] for r in lake.as_of("s", ["day"], as_of=T0).fetchall()}
    assert old[d2] == 2.0
    new = {r[0]: r[1] for r in lake.as_of("s", ["day"]).fetchall()}
    assert new == {d1: 1.0, d2: 2.5, d3: 3.0}
