from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import indexly.perf.probe as perf_probe
from indexly.perf import (
    MetricSample,
    PerformanceStatus,
    ProbeBudget,
    ReadOnlyProbeUnavailable,
    ProbeSnapshot,
    RecordValidationError,
    build_record,
    collect_live_snapshot,
    mad,
    median,
    nearest_rank_p95,
    read_conservative_status,
    read_validated_record,
    size_bucket,
    write_validated_record,
)
from indexly.perf.model import DERIVED
from indexly.perf.state import MAX_RECORD_BYTES, decode_record, encode_record


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE VIRTUAL TABLE file_index USING fts5(
            path, content, clean_content, modified, hash, tag,
            tokenize='porter', prefix='2 3 4'
        )
        """)
    conn.execute(
        "CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row')"
    )
    conn.execute(
        "INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)",
        ("private/path.txt", "alpha beta", "alpha beta", "now", "hash", "tag"),
    )
    conn.commit()
    conn.close()


def _snapshot(
    value: float,
    *,
    timestamp: str = "2026-07-27T12:00:00Z",
    duration: float = 0.1,
) -> ProbeSnapshot:
    return ProbeSnapshot(
        timestamp=timestamp,
        database_identity="a" * 64,
        schema_fingerprint="b" * 64,
        indexly_version="2.1.6",
        sqlite_version=sqlite3.sqlite_version,
        journal_mode="delete",
        page_size=4096,
        size_bucket="0-128 MiB",
        metrics={"fts_readiness_p95_ms": MetricSample(DERIVED, "milliseconds", value)},
        duration_seconds=duration,
    )


def test_robust_formulas_and_size_boundaries() -> None:
    assert median([3, 1, 2, 4]) == 2.5
    assert mad([1, 2, 3, 100]) == 1.0
    assert nearest_rank_p95(range(1, 10)) == 9
    assert size_bucket(128 * 1024 * 1024 - 1) == "0-128 MiB"
    assert size_bucket(128 * 1024 * 1024) == "128-512 MiB"
    assert size_bucket(10 * 1024**3) == ">10 GiB"
    with pytest.raises(ValueError):
        median([])
    with pytest.raises(ValueError):
        mad([float("nan")])


def test_collect_snapshot_is_read_only_bounded_and_private(tmp_path: Path) -> None:
    db = tmp_path / "sensitive-name.db"
    _create_db(db)
    before = db.stat().st_mtime_ns

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(per_probe_seconds=1, global_seconds=5),
    )

    assert db.stat().st_mtime_ns == before
    assert snapshot.metrics["document_count"].value == 1
    assert snapshot.metrics["fts_readiness_p50_ms"].value is not None
    assert snapshot.metrics["database_change_counter"].status == "measured"
    assert type(snapshot.metrics["database_change_counter"].value) is int
    assert snapshot.metrics["fts_schema_action_ready"].value == 1
    assert snapshot.database_identity != str(db)
    rendered = json.dumps(snapshot.to_dict())
    assert "sensitive-name" not in rendered
    assert "private/path" not in rendered
    assert "alpha" not in rendered


def test_throughput_log_reader_rejects_oversized_lines_within_bound(
    tmp_path: Path,
) -> None:
    db = tmp_path / "index.db"
    _create_db(db)
    log = tmp_path / "index.ndjson"
    log.write_bytes(b"x" * (64 * 1024 + 1) + b"\n")

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(per_probe_seconds=1, global_seconds=5),
        log_paths=(log,),
    )

    throughput = snapshot.metrics["indexing_throughput_documents_per_second"]
    assert throughput.value is None
    assert throughput.status == "not_measured_unavailable"


def test_throughput_uses_newest_bounded_summary_records(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    _create_db(db)
    log = tmp_path / "index.ndjson"
    older = [
        json.dumps(
            {
                "event": "INDEX_SUMMARY",
                "indexed_count": 1,
                "duration_seconds": 1,
            }
        )
        for _ in range(200)
    ]
    newer = [
        json.dumps(
            {
                "event": "INDEX_SUMMARY",
                "indexed_count": 100,
                "duration_seconds": 1,
            }
        )
        for _ in range(200)
    ]
    log.write_text("\n".join(older + newer) + "\n", encoding="utf-8")

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(per_probe_seconds=1, global_seconds=5),
        log_paths=(log,),
    )

    assert snapshot.metrics["indexing_throughput_documents_per_second"].value == 100


def test_nested_log_discovery_reads_current_partition(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    _create_db(db)
    log_root = tmp_path / "log"
    recent = log_root / "2026" / "07"
    recent.mkdir(parents=True)
    (recent / "2026-07-27_index_events.ndjson").write_text(
        json.dumps(
            {
                "event": "INDEX_SUMMARY",
                "indexed_count": 25,
                "duration_seconds": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(per_probe_seconds=1, global_seconds=5),
        log_roots=(log_root,),
    )

    assert snapshot.metrics["indexing_throughput_documents_per_second"].value == 25


def test_nested_log_discovery_has_explicit_directory_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "index.db"
    _create_db(db)
    log_root = tmp_path / "log"
    log_root.mkdir()
    for index in range(64):
        (log_root / f"extra-{index:02d}").mkdir()
    calls = 0
    original_scandir = perf_probe.os.scandir

    def counted_scandir(path):
        nonlocal calls
        calls += 1
        return original_scandir(path)

    monkeypatch.setattr(perf_probe.os, "scandir", counted_scandir)

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(per_probe_seconds=1, global_seconds=5),
        log_roots=(log_root,),
    )

    assert calls <= 32
    assert snapshot.metrics["indexing_throughput_documents_per_second"].value is None


def test_wal_probe_fails_before_creating_or_changing_sidecars(tmp_path: Path) -> None:
    db = tmp_path / "wal.db"
    writer = sqlite3.connect(db)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("CREATE TABLE sample(value TEXT)")
    writer.execute("INSERT INTO sample VALUES ('committed in wal')")
    writer.commit()
    sidecars_before = {
        path.name: path.read_bytes()
        for path in tmp_path.iterdir()
        if path.name != db.name
    }

    with pytest.raises(ReadOnlyProbeUnavailable, match="WAL-mode"):
        collect_live_snapshot(db, identity_salt=b"x" * 32)

    assert {
        path.name: path.read_bytes()
        for path in tmp_path.iterdir()
        if path.name != db.name
    } == sidecars_before
    writer.close()


def test_baseline_requires_history_and_sustained_degradation() -> None:
    salt = "11" * 32
    record = None
    for index, value in enumerate((10.0, 10.0, 10.0)):
        record = build_record(
            _snapshot(value, timestamp=f"2026-07-2{index + 1}T12:00:00Z"),
            record,
            identity_salt=salt,
        )
        assert record.status.grade is None
        assert record.status.evidence == "collecting_baseline"

    nominal = build_record(_snapshot(10.0, timestamp="2026-07-24T12:00:00Z"), record)
    assert nominal.status.grade == "Nominal"

    first_slow = build_record(
        _snapshot(14.0, timestamp="2026-07-25T12:00:00Z"), nominal
    )
    assert first_slow.status.grade == "Nominal"
    second_slow = build_record(
        _snapshot(14.0, timestamp="2026-07-26T12:00:00Z"), first_slow
    )
    assert second_slow.status.grade == "Elevated"


def test_critical_probe_and_snapshot_duration_are_constrained() -> None:
    record = None
    for index in range(3):
        record = build_record(
            _snapshot(10, timestamp=f"2026-07-2{index + 1}T12:00:00Z"),
            record,
            identity_salt="22" * 32,
        )
    critical = build_record(_snapshot(2001, timestamp="2026-07-24T12:00:00Z"), record)
    assert critical.status.grade == "Constrained"

    duration = build_record(
        _snapshot(10, timestamp="2026-07-24T12:00:00Z", duration=10.1),
        record,
    )
    assert duration.status.grade == "Constrained"


def test_missing_current_timed_evidence_is_inconclusive() -> None:
    record = None
    for index in range(3):
        record = build_record(
            _snapshot(10, timestamp=f"2026-07-2{index + 1}T12:00:00Z"),
            record,
            identity_salt="22" * 32,
        )
    unavailable = replace(
        _snapshot(10, timestamp="2026-07-24T12:00:00Z"),
        metrics={
            "fts_readiness_p95_ms": MetricSample(
                DERIVED, "milliseconds", None, "not_measured_budget"
            )
        },
    )
    result = build_record(unavailable, record)
    assert result.status.grade is None
    assert result.status.evidence == "inconclusive"


def test_sparse_metric_history_cannot_produce_a_grade() -> None:
    unavailable = MetricSample(
        DERIVED,
        "milliseconds",
        None,
        "not_measured_budget",
    )
    record = build_record(
        replace(_snapshot(10), metrics={"fts_readiness_p95_ms": unavailable}),
        identity_salt="66" * 32,
    )
    record = build_record(
        replace(
            _snapshot(10, timestamp="2026-07-28T12:00:00Z"),
            metrics={"fts_readiness_p95_ms": unavailable},
        ),
        record,
    )
    record = build_record(
        _snapshot(10, timestamp="2026-07-29T12:00:00Z"),
        record,
    )

    result = build_record(
        _snapshot(30, timestamp="2026-07-30T12:00:00Z"),
        record,
    )

    assert result.status.grade is None
    assert result.status.evidence == "inconclusive"
    assert result.baselines == {}


def test_growth_rate_requires_one_day_and_reports_both_directions() -> None:
    def allocated(value: int, timestamp: str) -> ProbeSnapshot:
        snapshot = _snapshot(10, timestamp=timestamp)
        metrics = dict(snapshot.metrics)
        metrics["allocated_db_bytes"] = MetricSample(DERIVED, "bytes", value)
        return replace(snapshot, metrics=metrics)

    record = build_record(
        allocated(200, "2026-07-27T00:00:00Z"),
        identity_salt="77" * 32,
    )
    early = build_record(
        allocated(100, "2026-07-27T12:00:00Z"),
        record,
    )
    assert "growth_rate_bytes_per_day" not in early.sessions[-1].metrics

    positive = build_record(
        allocated(300, "2026-07-28T12:00:00Z"),
        early,
    )
    assert positive.sessions[-1].metrics["growth_rate_bytes_per_day"].value == 200

    negative = build_record(
        allocated(100, "2026-07-29T12:00:00Z"),
        positive,
    )
    assert negative.sessions[-1].metrics["growth_rate_bytes_per_day"].value == -200


def test_growth_looks_back_past_frequent_subday_samples() -> None:
    def allocated(value: int, timestamp: str) -> ProbeSnapshot:
        snapshot = _snapshot(10, timestamp=timestamp)
        metrics = dict(snapshot.metrics)
        metrics["allocated_db_bytes"] = MetricSample(DERIVED, "bytes", value)
        return replace(snapshot, metrics=metrics)

    record = None
    for value, timestamp in (
        (100, "2026-07-27T00:00:00Z"),
        (125, "2026-07-27T12:00:00Z"),
        (150, "2026-07-28T00:00:00Z"),
        (175, "2026-07-28T12:00:00Z"),
        (200, "2026-07-29T00:00:00Z"),
    ):
        record = build_record(
            allocated(value, timestamp),
            record,
            identity_salt="88" * 32,
        )

    growth = record.sessions[-1].metrics["growth_rate_bytes_per_day"]
    assert growth.value == 50


def test_state_round_trip_previous_recovery_and_pure_missing_read(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "missing" / "perf"
    missing = read_validated_record(state_dir)
    assert missing.record is None
    assert not state_dir.exists()

    record = build_record(_snapshot(10), identity_salt="33" * 32)
    write_validated_record(state_dir, record)
    newer = replace(
        record,
        updated_at="2026-07-28T12:00:00Z",
        status=PerformanceStatus("Nominal", "current", "ok"),
    )
    write_validated_record(state_dir, newer)

    primary, _ = (
        state_dir / "performance-v1.json",
        state_dir / "performance-v1.previous.json",
    )
    primary.write_text("{damaged", encoding="utf-8")
    recovered = read_validated_record(state_dir)
    assert recovered.recovered
    assert recovered.source == "previous"
    assert recovered.record == record
    assert primary.read_text(encoding="utf-8") == "{damaged"


def test_record_validation_rejects_checksum_schema_numbers_and_size() -> None:
    record = build_record(_snapshot(10), identity_salt="44" * 32)
    payload = encode_record(record)
    assert decode_record(payload) == record

    envelope = json.loads(payload)
    envelope["record"]["unexpected"] = True
    tampered = json.dumps(envelope).encode()
    with pytest.raises(RecordValidationError):
        decode_record(tampered)
    with pytest.raises(RecordValidationError):
        decode_record(payload + b" " * MAX_RECORD_BYTES)

    duplicate = b'{"checksum":{},"checksum":{},"record":{}}'
    with pytest.raises(RecordValidationError, match="duplicate"):
        decode_record(duplicate)


def test_conservative_status_never_calls_missing_or_stale_evidence_healthy(
    tmp_path: Path,
) -> None:
    missing = read_conservative_status(tmp_path / "perf")
    assert missing.grade is None
    assert missing.evidence == "record_unavailable"

    stale = build_record(
        _snapshot(10, timestamp="2020-01-01T00:00:00Z"),
        identity_salt="55" * 32,
    )
    write_validated_record(tmp_path / "perf", stale)
    status = read_conservative_status(tmp_path / "perf")
    assert status.grade is None
    assert status.evidence == "baseline_stale"
