import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from indexly.perf import cli


def _seed_perf_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE VIRTUAL TABLE file_index USING fts5(
            path,
            content,
            clean_content,
            modified,
            hash,
            tokenize='unicode61',
            prefix='2 3 4'
        )
        """)
    conn.execute(
        "CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row')"
    )
    conn.execute(
        """
        INSERT INTO file_index(path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("private-name.txt", "alpha beta", "alpha beta", "2026-07-27", "digest"),
    )
    conn.commit()
    conn.close()


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["perf", "--read"], 0),
        (["--no-update-check", "perf", "--read"], 1),
        (["--version", "perf", "--read"], None),
        (["search", "perf"], None),
        (["--unknown", "perf", "--read"], None),
    ],
)
def test_perf_command_index_honors_top_level_precedence(argv, expected):
    assert cli.perf_command_index(argv) == expected


def test_read_missing_record_does_not_create_home_or_open_db(tmp_path, monkeypatch):
    runtime = tmp_path / "absent-runtime"
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    output = io.StringIO()

    result = cli.run_perf_command(
        ["--read", "--db", str(tmp_path / "missing.db"), "--json"],
        stream=output,
    )

    assert result == 2
    assert not runtime.exists()
    assert json.loads(output.getvalue())["schema"] == "indexly.performance-error/v1"


@pytest.mark.parametrize("module", ["indexly", "indexly.indexly"])
def test_fresh_process_read_routes_before_runtime_side_effects(tmp_path, module):
    runtime = tmp_path / "absent-runtime"
    environment = os.environ.copy()
    environment["INDEXLY_HOME"] = str(runtime)

    result = subprocess.run(
        [sys.executable, "-m", module, "perf", "--read", "--json"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["schema"] == "indexly.performance-error/v1"
    assert result.stderr == ""
    assert not runtime.exists()


def test_fresh_process_show_refuses_wal_without_sidecar_changes(tmp_path):
    runtime = tmp_path / "absent-runtime"
    db_path = tmp_path / "wal.db"
    writer = sqlite3.connect(db_path)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("CREATE TABLE sample(value TEXT)")
    writer.execute("INSERT INTO sample VALUES ('committed')")
    writer.commit()
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.iterdir()
        if path.name != db_path.name
    }
    environment = os.environ.copy()
    environment["INDEXLY_HOME"] = str(runtime)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "indexly",
            "perf",
            "--show",
            "--db",
            str(db_path),
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["schema"] == "indexly.performance-error/v1"
    assert {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.iterdir()
        if path.name != db_path.name
    } == before
    assert not runtime.exists()
    writer.close()


def test_opti_is_plan_only_and_creates_no_state(tmp_path, monkeypatch):
    runtime = tmp_path / "absent-runtime"
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    output = io.StringIO()

    result = cli.run_perf_command(["--opti", "--json"], stream=output)
    document = json.loads(output.getvalue())

    assert result == 0
    assert document["mutating"] is False
    assert document["enabled_actions"] == []
    assert document["status"]["grade"] is None
    assert not runtime.exists()


def test_show_refreshes_only_privacy_limited_perf_record(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    before = db_path.read_bytes()
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    output = io.StringIO()

    result = cli.run_perf_command(
        ["--show", "--db", str(db_path), "--json"],
        stream=output,
    )
    document = json.loads(output.getvalue())

    assert result == 0
    assert db_path.read_bytes() == before
    assert document["schema"] == "indexly.performance-report/v1"
    assert "identity_salt" not in document["record"]
    rendered = output.getvalue()
    assert str(db_path) not in rendered
    assert "private-name.txt" not in rendered
    assert sorted(path.name for path in (runtime / "perf").iterdir()) == [
        "performance-v1.json"
    ]


def test_text_show_renders_metrics_labels_units_and_baselines(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    output = io.StringIO()

    result = cli.run_perf_command(
        ["--show", "--db", str(db_path)],
        stream=output,
    )

    rendered = output.getvalue()
    assert result == 0
    assert "Metrics:" in rendered
    assert "main_db_bytes [Observed]:" in rendered
    assert "bytes" in rendered
    assert "Baselines:" in rendered
    assert "three comparable prior values" in rendered


def test_read_uses_recovered_record_without_rewriting(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    assert (
        cli.run_perf_command(
            ["--show", "--db", str(db_path), "--json"],
            stream=io.StringIO(),
        )
        == 0
    )
    state_dir = runtime / "perf"
    primary = state_dir / "performance-v1.json"
    previous = state_dir / "performance-v1.previous.json"
    previous.write_bytes(primary.read_bytes())
    primary.write_text("invalid", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in state_dir.iterdir()}
    output = io.StringIO()

    result = cli.run_perf_command(["--read", "--json"], stream=output)

    assert result == 0
    assert json.loads(output.getvalue())["recovered_from_previous"] is True
    assert {path.name: path.read_bytes() for path in state_dir.iterdir()} == before


def test_apply_fails_closed_before_backup_or_database_changes(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    backup_dir = tmp_path / "backups"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    before = db_path.read_bytes()
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    error = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(backup_dir),
            "--yes",
            "--db",
            str(db_path),
        ],
        error_stream=error,
    )

    assert result == 2
    assert "not enabled" in error.getvalue()
    assert db_path.read_bytes() == before
    assert not backup_dir.exists()
    assert not runtime.exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["--show", "--yes"],
        ["--read", "--apply"],
        ["--opti", "--yes"],
        ["--opti", "--action", "planner-optimize"],
        ["--opti", "--apply", "--backup-dir", "backup"],
        ["--opti", "--backup-dir", "backup"],
    ],
)
def test_guarded_action_flags_reject_incomplete_authorization(argv):
    error = io.StringIO()

    assert cli.run_perf_command(argv, error_stream=error) == 2
    assert "Performance diagnostics unavailable" in error.getvalue()


def test_fresh_process_json_argument_error_is_one_json_document(tmp_path):
    environment = os.environ.copy()
    environment["INDEXLY_HOME"] = str(tmp_path / "absent-runtime")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "indexly",
            "perf",
            "--show",
            "--yes",
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    document = json.loads(result.stdout)
    assert result.returncode == 2
    assert document["schema"] == "indexly.performance-error/v1"
    assert result.stderr == ""
