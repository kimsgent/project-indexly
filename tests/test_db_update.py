from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexly import db_update
from indexly.db_update import (
    FTS5RebuildError,
    _rebuild_fts5_table,
    apply_migrations,
    check_schema,
    inspect_fts5_definition,
)
from indexly.migration_manager import run_migrations

MATCHING_SQL = """
    CREATE VIRTUAL TABLE "file_index" USING FTS5(
        "path", content, clean_content, modified, hash, tag,
        PREFIX = "2 3 4",
        TOKENIZE = "PORTER"
    )
"""


def _create_database(
    path: Path,
    *,
    prefix: str = "2 3",
    journal_mode: str | None = None,
) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    if journal_mode:
        conn.execute(f"PRAGMA journal_mode={journal_mode}")
    conn.execute(f"""
        CREATE VIRTUAL TABLE file_index USING fts5(
            path, content, clean_content, modified, hash, tag,
            tokenize='porter', prefix='{prefix}'
        )
        """)
    conn.execute(
        "CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row')"
    )
    conn.execute("""
        CREATE TABLE indexly_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
    conn.execute(
        "INSERT INTO indexly_state(key, value) VALUES (?, ?)",
        ("search_index_generation", "7"),
    )
    conn.commit()
    return conn


@pytest.mark.parametrize(
    ("sql", "state"),
    [
        (MATCHING_SQL, "match"),
        (MATCHING_SQL.replace('"PORTER"', '"unicode61"'), "drift"),
        (MATCHING_SQL.replace('"2 3 4"', '"2 3"'), "drift"),
        (MATCHING_SQL.replace("FTS5", "fts4"), "drift"),
        (MATCHING_SQL.replace("tag,", "tag, detail='column',"), "drift"),
        (MATCHING_SQL.replace('"path"', '"path" UNINDEXED'), "drift"),
        ("CREATE TABLE file_index(path TEXT)", "uninspectable"),
        (
            "CREATE VIRTUAL TABLE file_index USING fts5(path, tokenize='porter'",
            "uninspectable",
        ),
        (
            "CREATE VIRTUAL TABLE file_index USING fts5(path, mystery='x')",
            "uninspectable",
        ),
    ],
)
def test_structured_fts5_definition_classification(sql, state):
    assert inspect_fts5_definition(sql).state == state


def test_structured_inspection_accepts_repeated_prefix_options():
    sql = """
        CREATE VIRTUAL TABLE file_index USING fts5(
            path, content, clean_content, modified, hash, tag,
            prefix='4 2', prefix=3, tokenize='porter'
        )
    """

    inspection = inspect_fts5_definition(sql)

    assert inspection.state == "match"
    assert inspection.definition is not None
    assert inspection.definition.prefix == (2, 3, 4)


def test_check_schema_reports_semantic_drift_and_uninspectable(tmp_path):
    drift = _create_database(tmp_path / "drift.db")
    drift_diffs = check_schema(drift, verbose=False)
    drift.close()

    malformed = sqlite3.connect(tmp_path / "normal.db")
    malformed.execute("CREATE TABLE file_index(path TEXT)")
    malformed.commit()
    malformed_diffs = check_schema(malformed, verbose=False)
    malformed.close()

    assert any(
        message.startswith("FTS5 rebuild needed") for _, message, _ in drift_diffs
    )
    assert any(
        message.startswith("FTS5 definition uninspectable")
        for _, message, _ in malformed_diffs
    )


def test_uninspectable_definition_is_never_automatically_rebuilt(tmp_path):
    conn = sqlite3.connect(tmp_path / "uninspectable.db")
    conn.execute("CREATE TABLE file_index(path TEXT)")
    conn.commit()

    with pytest.raises(FTS5RebuildError, match="uninspectable"):
        apply_migrations(conn, auto_fix=True, allow_fts_rebuild=True)

    assert (
        conn.execute(
            "SELECT type FROM sqlite_master WHERE name='file_index'"
        ).fetchone()[0]
        == "table"
    )
    conn.close()


def test_migrate_check_uses_semantic_detector_without_mutating(tmp_path, capsys):
    db_path = tmp_path / "migrate-check.db"
    conn = _create_database(db_path)
    conn.close()

    run_migrations(str(db_path), dry_run=True)

    output = capsys.readouterr().out
    verify = sqlite3.connect(db_path)
    try:
        assert "Semantic FTS5 definition drift detected" in output
        assert "FTS5 rebuild not authorized" in output
        assert not verify.execute(
            "SELECT name FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone()
        assert (
            inspect_fts5_definition(
                verify.execute(
                    "SELECT sql FROM sqlite_master WHERE name='file_index'"
                ).fetchone()[0]
            ).state
            == "drift"
        )
    finally:
        verify.close()


def test_verified_rebuild_preserves_rows_vocab_match_and_bumps_generation(tmp_path):
    db_path = tmp_path / "index.db"
    conn = _create_database(db_path)
    original_rows = [
        ("/docs/a.txt", "alpha beta", "alpha beta", "1", "hash-a", "work"),
        ("/docs/b.txt", "gamma", "gamma", "2", "hash-b", "home"),
    ]
    conn.executemany(
        "INSERT INTO file_index(path, content, clean_content, modified, hash, tag) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        original_rows,
    )
    conn.commit()

    result = _rebuild_fts5_table(conn, "file_index")

    assert result.rows_preserved == 2
    assert result.generation == 8
    assert result.snapshot_path.exists()
    assert (
        conn.execute("SELECT * FROM file_index ORDER BY rowid").fetchall()
        == original_rows
    )
    assert (
        inspect_fts5_definition(
            conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='file_index'"
            ).fetchone()[0]
        ).state
        == "match"
    )
    assert (
        conn.execute(
            "SELECT path FROM file_index WHERE file_index MATCH 'alpha'"
        ).fetchone()[0]
        == "/docs/a.txt"
    )
    assert conn.execute("SELECT COUNT(*) FROM file_index_vocab").fetchone()[0] > 0
    assert (
        conn.execute(
            "SELECT value FROM indexly_state WHERE key='search_index_generation'"
        ).fetchone()[0]
        == "8"
    )
    conn.close()


def test_snapshot_contains_committed_wal_content(tmp_path):
    db_path = tmp_path / "wal.db"
    conn = _create_database(db_path, journal_mode="WAL")
    conn.execute(
        "INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)",
        ("/wal.txt", "wal payload", "wal payload", "1", "wal-hash", "tag"),
    )
    conn.commit()

    result = _rebuild_fts5_table(conn, "file_index")
    snapshot = sqlite3.connect(result.snapshot_path)
    try:
        assert snapshot.execute("SELECT path, content FROM file_index").fetchall() == [
            ("/wal.txt", "wal payload")
        ]
    finally:
        snapshot.close()
        conn.close()


def test_workspace_estimate_uses_logical_wal_database_size(tmp_path):
    db_path = tmp_path / "wal-workspace.db"
    conn = _create_database(db_path, journal_mode="WAL")
    conn.execute("CREATE TABLE payload(value BLOB)")
    conn.execute("INSERT INTO payload VALUES (?)", (b"x" * (2 * 1024 * 1024),))
    conn.commit()

    logical_bytes = (
        conn.execute("PRAGMA page_count").fetchone()[0]
        * conn.execute("PRAGMA page_size").fetchone()[0]
    )
    required = db_update._required_workspace_bytes(conn, db_path)

    assert logical_bytes > db_path.stat().st_size
    assert required >= logical_bytes * 3
    conn.close()


def test_verification_failure_rolls_back_original_and_generation(tmp_path, monkeypatch):
    db_path = tmp_path / "rollback.db"
    conn = _create_database(db_path)
    row = ("/original.txt", "alpha", "alpha", "1", "hash", "tag")
    conn.execute("INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)", row)
    conn.commit()

    def fail_verification(*_args, **_kwargs):
        raise FTS5RebuildError("injected verification failure")

    monkeypatch.setattr(db_update, "_verify_vocab_and_match", fail_verification)

    with pytest.raises(FTS5RebuildError, match="injected verification failure") as exc:
        _rebuild_fts5_table(conn, "file_index")

    assert exc.value.snapshot_path is not None
    assert exc.value.snapshot_path.exists()
    assert conn.execute("SELECT * FROM file_index").fetchone() == row
    assert (
        conn.execute(
            "SELECT value FROM indexly_state WHERE key='search_index_generation'"
        ).fetchone()[0]
        == "7"
    )
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE name LIKE 'file_index_replacement_%'"
    ).fetchall()
    conn.close()


def test_insufficient_space_fails_before_snapshot_or_mutation(tmp_path, monkeypatch):
    db_path = tmp_path / "no-space.db"
    conn = _create_database(db_path)
    conn.execute(
        "INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)",
        ("/a", "alpha", "alpha", "1", "h", "t"),
    )
    conn.commit()
    monkeypatch.setattr(
        db_update.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=100, free=0),
    )

    with pytest.raises(FTS5RebuildError, match="insufficient free space"):
        _rebuild_fts5_table(conn, "file_index")

    assert not (tmp_path / "backups").exists()
    assert conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] == 1
    conn.close()


def test_writer_lock_failure_leaves_database_unchanged(tmp_path):
    db_path = tmp_path / "locked.db"
    setup = _create_database(db_path)
    setup.execute(
        "INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)",
        ("/a", "alpha", "alpha", "1", "h", "t"),
    )
    setup.commit()
    setup.close()

    lock = sqlite3.connect(db_path)
    lock.execute("BEGIN IMMEDIATE")
    repair = sqlite3.connect(db_path, timeout=0.01)
    try:
        with pytest.raises(FTS5RebuildError, match="exclusive-writer lock"):
            _rebuild_fts5_table(repair, "file_index")
        assert repair.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] == 1
        assert not (tmp_path / "backups").exists()
    finally:
        repair.close()
        lock.rollback()
        lock.close()


def test_rebuild_digest_uses_bounded_fetchmany_on_large_fixture(tmp_path, monkeypatch):
    db_path = tmp_path / "large.db"
    conn = _create_database(db_path)
    rows = [
        (
            f"/docs/{index}.txt",
            f"term {index}",
            f"term {index}",
            str(index),
            f"h{index}",
            "tag",
        )
        for index in range(2500)
    ]
    conn.executemany("INSERT INTO file_index VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    observed_batch_sizes: list[int] = []
    original_digest = db_update._logical_digest

    def bounded_digest(connection, table, columns, *, batch_size=512):
        observed_batch_sizes.append(batch_size)
        return original_digest(connection, table, columns, batch_size=batch_size)

    monkeypatch.setattr(db_update, "_logical_digest", bounded_digest)

    result = _rebuild_fts5_table(conn, "file_index")

    assert result.rows_preserved == len(rows)
    assert observed_batch_sizes
    assert max(observed_batch_sizes) == 512
    assert conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] == len(rows)
    conn.close()
