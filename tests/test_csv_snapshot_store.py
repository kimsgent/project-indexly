from indexly.observers.csv.csv_snapshot_store import (
    diff_snapshots_over_time,
    load_snapshot,
    query_snapshot_range,
    save_snapshot,
)


def _save_snapshot(source, timestamp, columns=None, rows=1):
    save_snapshot(
        str(source),
        hash_value=f"hash-{timestamp}",
        columns=columns or ["a", "b"],
        row_count=rows,
        col_count=len(columns or ["a", "b"]),
        summary={"rows": rows},
        cleaned_at=timestamp,
        snapshot_ts=timestamp,
    )


def test_load_snapshot_latest_returns_most_recent(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    _save_snapshot(source, "2024-01-01T00:00:00Z", rows=1)
    _save_snapshot(source, "2024-01-02T00:00:00Z", rows=2)

    snapshot = load_snapshot("sample.csv")

    assert snapshot["hash"] == "hash-2024-01-02T00:00:00Z"
    assert snapshot["columns"] == ["a", "b"]
    assert snapshot["row_count"] == 2
    assert snapshot["summary"] == {"rows": 2}


def test_load_snapshot_at_time_returns_prior_snapshot(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    _save_snapshot(source, "2024-01-01T00:00:00Z", rows=1)
    _save_snapshot(source, "2024-01-03T00:00:00Z", rows=3)

    snapshot = load_snapshot("sample.csv", at_time="2024-01-02T00:00:00Z")

    assert snapshot["snapshot_ts"] == "2024-01-01T00:00:00Z"
    assert snapshot["row_count"] == 1


def test_load_snapshot_nonexistent_returns_none():
    assert load_snapshot("missing.csv") is None


def test_query_and_diff_snapshots_over_time(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

    _save_snapshot(source, "2024-01-01T00:00:00Z", columns=["a"], rows=1)
    _save_snapshot(source, "2024-01-02T00:00:00Z", columns=["a", "b"], rows=4)

    snapshots = query_snapshot_range("sample.csv")
    diff = diff_snapshots_over_time(
        "sample.csv",
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
    )

    assert [snapshot["snapshot_ts"] for snapshot in snapshots] == [
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
    ]
    assert diff["added_columns"] == ["b"]
    assert diff["row_count_delta"] == 3
