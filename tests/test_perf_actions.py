from __future__ import annotations

import shutil
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import indexly.perf.actions as actions
from indexly.perf import ProbeBudget, build_record, collect_live_snapshot


def _create_db(path: Path, *, documents: int = 24) -> None:
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE VIRTUAL TABLE file_index USING fts5(
            path, content, clean_content, modified, hash, tag,
            tokenize='porter', prefix='2 3 4'
        )
        """)
    connection.execute(
        "CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row')"
    )
    for index in range(documents):
        connection.execute(
            "INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"private/{index}.txt",
                f"alpha beta {index}",
                f"alpha beta {index}",
                "now",
                str(index),
                "tag",
            ),
        )
        connection.commit()
    connection.close()


def _create_noncanonical_db(path: Path, *, external_content: bool) -> None:
    connection = sqlite3.connect(path)
    if external_content:
        connection.execute("""
            CREATE TABLE source_documents(
                path, content, clean_content, modified, hash, tag
            )
            """)
        connection.execute("""
            CREATE VIRTUAL TABLE file_index USING fts5(
                path, content, clean_content, modified, hash, tag,
                tokenize='porter', prefix='2 3 4',
                content='source_documents'
            )
            """)
    else:
        connection.execute("""
            CREATE VIRTUAL TABLE file_index USING fts5(
                path, content, clean_content, modified, hash, tag
            )
            """)
    connection.execute(
        "CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row')"
    )
    connection.commit()
    connection.close()


def _current_report(db: Path):
    salt = b"r" * 32
    snapshot = collect_live_snapshot(
        db,
        identity_salt=salt,
        budget=ProbeBudget(per_probe_seconds=1, global_seconds=5),
    )
    return build_record(snapshot, None, identity_salt=salt.hex())


@pytest.mark.parametrize("action", ["planner-optimize", "fts-merge"])
def test_actions_create_verified_backup_and_numeric_audit(
    tmp_path: Path, action: str
) -> None:
    database_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    database_dir.mkdir()
    backup_dir.mkdir()
    database = database_dir / "index.db"
    _create_db(database)
    report = _current_report(database)

    result = actions.execute_action(
        action, db_path=database, backup_dir=backup_dir, report=report
    )

    assert result.outcome.action == action
    assert result.outcome.result in {"applied", "no_op"}
    assert result.backup_path.parent == backup_dir
    assert result.backup_path.name.startswith("indexly-perf-snapshot-")
    assert result.backup_path.stat().st_mode & 0o777 == 0o600
    assert all(type(value) is int for value in result.outcome.numeric.values())
    assert "before_page_count" in result.outcome.numeric
    assert "after_page_count" in result.outcome.numeric
    if action == "fts-merge":
        assert result.outcome.result == "applied"
        assert result.outcome.numeric["delta_total_changes"] > 0
    with sqlite3.connect(result.backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] == 24


def test_stale_or_wrong_database_report_fails_before_backup(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    other = live_dir / "other.db"
    _create_db(database)
    _create_db(other)
    report = _current_report(database)
    stale_session = replace(
        report.sessions[-1],
        timestamp=(datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
    )
    stale = replace(report, sessions=(stale_session,))

    with pytest.raises(actions.ActionPreconditionError, match="stale"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=stale,
        )
    with pytest.raises(actions.ActionPreconditionError, match="does not identify"):
        actions.execute_action(
            "planner-optimize",
            db_path=other,
            backup_dir=backup_dir,
            report=report,
        )

    assert list(backup_dir.iterdir()) == []


def test_wal_is_rejected_without_checkpoint_or_sidecar_change(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    writer = sqlite3.connect(database)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("INSERT INTO file_index(path) VALUES ('pending')")
    writer.commit()
    before = {
        item.name: item.read_bytes()
        for item in live_dir.iterdir()
        if item.name != database.name
    }

    with pytest.raises(actions.ActionPreconditionError, match="WAL"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert {
        item.name: item.read_bytes()
        for item in live_dir.iterdir()
        if item.name != database.name
    } == before
    assert list(backup_dir.iterdir()) == []
    writer.close()


def test_writer_contention_fails_before_backup(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    writer = sqlite3.connect(database, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")

    with pytest.raises(actions.ActionPreconditionError, match="busy"):
        actions.execute_action(
            "fts-merge",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert list(backup_dir.iterdir()) == []
    writer.rollback()
    writer.close()


def test_insufficient_space_fails_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    usage = shutil._ntuple_diskusage(total=1, used=1, free=0)
    monkeypatch.setattr(actions.shutil, "disk_usage", lambda _path: usage)

    with pytest.raises(actions.ActionPreconditionError, match="insufficient"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert list(backup_dir.iterdir()) == []


def test_old_sqlite_planner_action_fails_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    monkeypatch.setattr(actions.sqlite3, "sqlite_version_info", (3, 45, 3))

    with pytest.raises(actions.ActionPreconditionError, match="3.46"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert list(backup_dir.iterdir()) == []


def test_backup_verification_failure_removes_partial_and_preserves_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    before = database.read_bytes()
    original = actions._require_quick_check

    def fail_backup(connection: sqlite3.Connection, label: str) -> None:
        if label == "backup snapshot":
            raise actions.ActionBackupError("injected backup verification failure")
        original(connection, label)

    monkeypatch.setattr(actions, "_require_quick_check", fail_backup)

    with pytest.raises(actions.ActionBackupError, match="injected"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert database.read_bytes() == before
    assert list(backup_dir.iterdir()) == []


def test_backup_directory_fsync_failure_aborts_before_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    action_called = False

    def fail_fsync(_directory: Path) -> None:
        raise OSError("injected directory fsync failure")

    def record_action(_connection: sqlite3.Connection, _action: str) -> None:
        nonlocal action_called
        action_called = True

    monkeypatch.setattr(actions, "_fsync_directory", fail_fsync)
    monkeypatch.setattr(actions, "_run_action", record_action)

    with pytest.raises(actions.ActionBackupError, match="could not be created"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert not action_called
    assert list(backup_dir.iterdir()) == []


def test_backup_cleanup_failure_is_sanitized_and_reports_candidate_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "private-backup-location"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    original_unlink = Path.unlink

    def fail_fsync(_directory: Path) -> None:
        raise OSError("injected directory fsync failure")

    def fail_final_cleanup(candidate: Path, *args, **kwargs) -> None:
        if candidate.parent == backup_dir and candidate.name.startswith(
            "indexly-perf-snapshot-"
        ):
            raise PermissionError("injected private cleanup path")
        original_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(actions, "_fsync_directory", fail_fsync)
    monkeypatch.setattr(Path, "unlink", fail_final_cleanup)

    with pytest.raises(actions.ActionBackupError) as raised:
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    error = raised.value
    assert error.cleanup_incomplete
    assert error.backup_path is not None
    assert error.backup_path.name.startswith("indexly-perf-snapshot-")
    assert str(tmp_path) not in str(error)
    leftovers = list(backup_dir.iterdir())
    assert leftovers == [error.backup_path]
    original_unlink(leftovers[0])


def test_action_failure_rolls_back_and_retains_verified_recovery_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)

    def mutate_then_fail(connection: sqlite3.Connection, _action: str) -> None:
        connection.execute("DELETE FROM file_index")
        raise sqlite3.OperationalError("injected action failure")

    monkeypatch.setattr(actions, "_run_action", mutate_then_fail)

    with pytest.raises(actions.ActionExecutionError, match="rolled back"):
        actions.execute_action(
            "fts-merge",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] == 24
    backups = list(backup_dir.iterdir())
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_unsupported_action_and_missing_backup_fail_closed(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)

    with pytest.raises(actions.ActionPreconditionError, match="unsupported"):
        actions.execute_action(
            "vacuum", db_path=database, backup_dir=backup_dir, report=report
        )
    with pytest.raises(actions.ActionPreconditionError, match="already exist"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=tmp_path / "missing",
            report=report,
        )
    with pytest.raises(actions.ActionPreconditionError, match="must differ"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=live_dir,
            report=report,
        )
    backup_link = tmp_path / "backup-link"
    try:
        backup_link.symlink_to(backup_dir, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")
    with pytest.raises(actions.ActionPreconditionError, match="symbolic link"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_link,
            report=report,
        )


def test_action_requires_exact_measured_report_state(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    latest = report.sessions[-1]
    metrics = dict(latest.metrics)
    metrics.pop("document_count")
    incomplete = replace(
        report,
        sessions=(replace(latest, metrics=metrics),),
    )

    with pytest.raises(actions.ActionPreconditionError, match="document_count"):
        actions.execute_action(
            "fts-merge",
            db_path=database,
            backup_dir=backup_dir,
            report=incomplete,
        )

    assert list(backup_dir.iterdir()) == []


@pytest.mark.parametrize("external_content", [False, True])
@pytest.mark.parametrize("action", ["planner-optimize", "fts-merge"])
def test_noncanonical_fts_schema_is_never_action_eligible(
    tmp_path: Path,
    action: str,
    external_content: bool,
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_noncanonical_db(database, external_content=external_content)
    report = _current_report(database)

    assert report.sessions[-1].metrics["fts_schema_action_ready"].value == 0
    with pytest.raises(actions.ActionPreconditionError, match="canonical"):
        actions.execute_action(
            action,
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert list(backup_dir.iterdir()) == []


def test_same_shape_in_place_write_invalidates_report_change_counter(
    tmp_path: Path,
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    before_size = database.stat().st_size
    before_pages = report.sessions[-1].metrics["page_count"].value
    before_counter = report.sessions[-1].metrics["database_change_counter"].value

    with sqlite3.connect(database) as connection:
        connection.execute("""
            UPDATE file_index
            SET content = 'gamma beta 0', clean_content = 'gamma beta 0'
            WHERE rowid = 1
            """)
        connection.commit()

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA page_count").fetchone()[0] == before_pages
    assert database.stat().st_size == before_size
    assert actions._database_change_counter(database) != before_counter

    with pytest.raises(actions.ActionPreconditionError, match="change counter"):
        actions.execute_action(
            "planner-optimize",
            db_path=database,
            backup_dir=backup_dir,
            report=report,
        )

    assert list(backup_dir.iterdir()) == []


def test_mode_rw_open_never_creates_a_missing_database(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(actions.ActionPreconditionError, match="could not be opened"):
        actions._connect(missing)

    assert not missing.exists()


def test_fts_action_is_one_positive_bounded_merge_without_forbidden_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    backup_dir = tmp_path / "backups"
    live_dir.mkdir()
    backup_dir.mkdir()
    database = live_dir / "index.db"
    _create_db(database)
    report = _current_report(database)
    statements: list[str] = []
    original = actions._run_action

    def traced(connection: sqlite3.Connection, action: str) -> None:
        connection.set_trace_callback(statements.append)
        try:
            original(connection, action)
        finally:
            connection.set_trace_callback(None)

    monkeypatch.setattr(actions, "_run_action", traced)

    result = actions.execute_action(
        "fts-merge",
        db_path=database,
        backup_dir=backup_dir,
        report=report,
    )

    normalized = [" ".join(statement.casefold().split()) for statement in statements]
    merge = [statement for statement in normalized if "'merge'" in statement]
    assert len(merge) == 1
    assert "500" in merge[0]
    assert result.outcome.numeric["delta_total_changes"] >= 2
    assert not any(
        forbidden in statement
        for statement in normalized
        for forbidden in (
            "vacuum",
            "'optimize'",
            "'rebuild'",
            "journal_mode",
            "wal_checkpoint",
        )
    )
    assert not list(backup_dir.glob("*.partial"))
