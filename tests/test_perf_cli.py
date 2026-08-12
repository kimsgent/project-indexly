import io
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from indexly.perf import cli
from indexly.perf.actions import ActionResult
from indexly.perf.model import ActionOutcome
from indexly.perf.state import read_validated_record


def _seed_perf_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE VIRTUAL TABLE file_index USING fts5(
            path,
            content,
            clean_content,
            modified,
            hash,
            tag,
            tokenize='porter',
            prefix='2 3 4'
        )
        """)
    conn.execute(
        "CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row')"
    )
    conn.execute(
        """
        INSERT INTO file_index(path, content, clean_content, modified, hash, tag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "private-name.txt",
            "alpha beta",
            "alpha beta",
            "2026-07-27",
            "digest",
            "tag",
        ),
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
    monkeypatch.setattr(
        cli.sqlite3,
        "connect",
        lambda *args, **kwargs: pytest.fail("plan-only mode opened SQLite"),
    )
    output = io.StringIO()

    result = cli.run_perf_command(["--opti", "--json"], stream=output)
    document = json.loads(output.getvalue())

    assert result == 0
    assert document["mutating"] is False
    assert document["enabled_actions"] == []
    assert {item["action"] for item in document["recommendations"]} == {
        "fts-merge",
        "planner-optimize",
    }
    assert document["apply_eligibility"] == "requires_current_database_preflight"
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
    assert "current validated primary report" in error.getvalue()
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


@dataclass(frozen=True)
class _RecommendedAction:
    disposition: str = "recommended"
    eligible: bool = True
    reason: str = "action-specific evidence supports this action"


class _EligiblePlan:
    def for_action(self, action):
        assert action in {"planner-optimize", "fts-merge"}
        return _RecommendedAction()


class _TTYStringIO(io.StringIO):
    def isatty(self):
        return True


def _prepare_current_report(
    runtime: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    assert (
        cli.run_perf_command(
            ["--show", "--db", str(db_path), "--json"],
            stream=io.StringIO(),
        )
        == 0
    )


def _fake_action_result(tmp_path: Path) -> ActionResult:
    return ActionResult(
        outcome=ActionOutcome(
            action="planner-optimize",
            timestamp="2026-07-27T23:00:00Z",
            result="applied",
            duration_seconds=0.01,
            numeric={"planner_actions_before": 1, "planner_actions_after": 0},
        ),
        backup_path=(
            tmp_path
            / "backups"
            / "indexly-perf-snapshot-12345678123456781234567812345678.sqlite3"
        ),
    )


def test_json_apply_requires_yes_without_prompt_or_mutation(tmp_path):
    output = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(tmp_path),
            "--json",
        ],
        stream=output,
    )

    assert result == 2
    assert json.loads(output.getvalue())["schema"] == "indexly.performance-error/v1"


def test_exact_confirmation_accepts_only_action_name():
    error = io.StringIO()

    assert (
        cli._confirm_action(
            "planner-optimize",
            input_stream=_TTYStringIO("planner-optimize\n"),
            error_stream=error,
        )
        is True
    )
    assert (
        cli._confirm_action(
            "planner-optimize",
            input_stream=_TTYStringIO("yes\n"),
            error_stream=io.StringIO(),
        )
        is False
    )


def test_plan_fails_closed_on_invalid_existing_report(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    state_dir = runtime / "perf"
    state_dir.mkdir(parents=True)
    (state_dir / "performance-v1.json").write_text("invalid", encoding="utf-8")
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    output = io.StringIO()

    result = cli.run_perf_command(["--opti", "--json"], stream=output)

    assert result == 2
    assert json.loads(output.getvalue())["schema"] == "indexly.performance-error/v1"


def test_apply_requires_exact_tty_confirmation_before_action(
    tmp_path,
    monkeypatch,
):
    import indexly.perf.actions as actions
    import indexly.perf.evidence as evidence

    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    monkeypatch.setattr(evidence, "plan_optimizations", lambda *a, **k: _EligiblePlan())
    called = False

    def unexpected_action(*args, **kwargs):
        nonlocal called
        called = True
        return _fake_action_result(tmp_path)

    monkeypatch.setattr(actions, "execute_action", unexpected_action)
    error = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(tmp_path / "backups"),
            "--db",
            str(db_path),
        ],
        input_stream=_TTYStringIO("yes\n"),
        error_stream=error,
    )

    assert result == 2
    assert "confirmation did not exactly match" in error.getvalue()
    assert called is False


def test_applied_action_persists_audit_and_publishes_post_show_comparison(
    tmp_path,
    monkeypatch,
):
    import indexly.perf.actions as actions
    import indexly.perf.evidence as evidence

    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    monkeypatch.setattr(evidence, "plan_optimizations", lambda *a, **k: _EligiblePlan())
    result_value = _fake_action_result(tmp_path)
    monkeypatch.setattr(actions, "execute_action", lambda *a, **k: result_value)
    output = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(tmp_path / "backups"),
            "--yes",
            "--db",
            str(db_path),
            "--json",
        ],
        stream=output,
    )

    document = json.loads(output.getvalue())
    loaded = read_validated_record(runtime / "perf")
    assert result == 0
    assert document["mutation_applied"] is True
    assert document["postcheck"]["status"] == "passed"
    assert isinstance(document["postcheck"]["comparison"], dict)
    assert str(tmp_path) not in output.getvalue()
    assert document["backup_filename"] == result_value.backup_path.name
    assert loaded.record is not None
    assert loaded.record.action_outcomes[-1] == result_value.outcome


def test_planner_action_end_to_end_from_live_indexly_evidence(
    tmp_path,
    monkeypatch,
):
    runtime = tmp_path / "runtime"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE file_tags(path TEXT PRIMARY KEY, tags TEXT)")
        connection.execute("INSERT INTO file_tags(path, tags) VALUES('one', 'tag')")
        connection.commit()
    monkeypatch.setattr(cli, "resolve_base_dir", lambda: runtime)
    assert (
        cli.run_perf_command(
            ["--show", "--db", str(db_path), "--json"],
            stream=io.StringIO(),
        )
        == 0
    )
    output = io.StringIO()

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
            "--json",
        ],
        stream=output,
    )

    document = json.loads(output.getvalue())
    assert result == 0
    assert document["action_outcome"]["action"] == "planner-optimize"
    assert document["action_outcome"]["result"] == "applied"
    assert document["mutation_applied"] is True
    assert document["postcheck"]["status"] == "passed"
    assert str(tmp_path) not in output.getvalue()
    backups = list(backup_dir.glob("indexly-perf-snapshot-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM file_tags").fetchone()[0] == 1


def test_postcheck_failure_reports_applied_and_retains_numeric_audit(
    tmp_path,
    monkeypatch,
):
    import indexly.perf.actions as actions
    import indexly.perf.evidence as evidence

    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    monkeypatch.setattr(evidence, "plan_optimizations", lambda *a, **k: _EligiblePlan())
    result_value = _fake_action_result(tmp_path)
    monkeypatch.setattr(actions, "execute_action", lambda *a, **k: result_value)
    monkeypatch.setattr(
        cli,
        "prepare_live_record",
        lambda *a, **k: (_ for _ in ()).throw(
            cli.ReadOnlyProbeUnavailable("postcheck unavailable")
        ),
    )
    output = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(tmp_path / "backups"),
            "--yes",
            "--db",
            str(db_path),
            "--json",
        ],
        stream=output,
    )

    document = json.loads(output.getvalue())
    loaded = read_validated_record(runtime / "perf")
    assert result == 3
    assert document["mutation_applied"] is True
    assert document["backup_retained"] is True
    assert document["audit_persisted"] is True
    assert document["postcheck"]["status"] == "failed"
    assert loaded.record is not None
    assert loaded.record.action_outcomes[-1] == result_value.outcome


def test_rolled_back_action_reports_retained_backup_without_path_leak(
    tmp_path,
    monkeypatch,
):
    import indexly.perf.actions as actions
    import indexly.perf.evidence as evidence

    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    backup = (
        tmp_path
        / "backups"
        / "indexly-perf-snapshot-12345678123456781234567812345678.sqlite3"
    )
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    monkeypatch.setattr(evidence, "plan_optimizations", lambda *a, **k: _EligiblePlan())

    def rolled_back(*args, **kwargs):
        raise actions.ActionExecutionError(
            "injected rollback",
            mutation_applied=False,
            backup_retained=True,
            backup_path=backup,
        )

    monkeypatch.setattr(actions, "execute_action", rolled_back)
    output = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(tmp_path / "backups"),
            "--yes",
            "--db",
            str(db_path),
            "--json",
        ],
        stream=output,
    )

    document = json.loads(output.getvalue())
    assert result == 2
    assert document["mutation_applied"] is False
    assert document["rolled_back"] is True
    assert document["backup_retained"] is True
    assert document["backup_filename"] == backup.name
    assert str(tmp_path) not in output.getvalue()


def test_incomplete_backup_cleanup_reports_filename_without_path(
    tmp_path,
    monkeypatch,
):
    import indexly.perf.actions as actions
    import indexly.perf.evidence as evidence

    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    candidate = (
        tmp_path
        / "private-backups"
        / "indexly-perf-snapshot-12345678123456781234567812345678.sqlite3"
    )
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    monkeypatch.setattr(evidence, "plan_optimizations", lambda *a, **k: _EligiblePlan())

    def cleanup_failed(*args, **kwargs):
        raise actions.ActionBackupError(
            "verified SQLite backup could not be created; cleanup was incomplete",
            cleanup_incomplete=True,
            backup_path=candidate,
        )

    monkeypatch.setattr(actions, "execute_action", cleanup_failed)
    output = io.StringIO()

    result = cli.run_perf_command(
        [
            "--opti",
            "--action",
            "planner-optimize",
            "--apply",
            "--backup-dir",
            str(candidate.parent),
            "--yes",
            "--db",
            str(db_path),
            "--json",
        ],
        stream=output,
    )

    document = json.loads(output.getvalue())
    assert result == 2
    assert document["mutation_applied"] is False
    assert document["backup_verified"] is False
    assert document["cleanup_incomplete"] is True
    assert document["backup_filename"] == candidate.name
    assert str(tmp_path) not in output.getvalue()


def test_postcheck_rejects_search_generation_change(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    loaded = read_validated_record(runtime / "perf")
    assert loaded.record is not None
    before = loaded.record
    generation = cli._expected_generation(before)
    assert generation is not None
    latest = before.sessions[-1]
    metrics = dict(latest.metrics)
    metrics["search_index_generation"] = replace(
        metrics["search_index_generation"],
        value=generation + 1,
    )
    after = replace(
        before,
        sessions=before.sessions[:-1] + (replace(latest, metrics=metrics),),
    )

    with pytest.raises(cli.RecordValidationError, match="not comparable"):
        cli._validate_post_action_report(
            before,
            after,
            expected_generation=generation,
        )


def test_postcheck_rejects_size_bucket_change(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    db_path = tmp_path / "search.db"
    _seed_perf_db(db_path)
    _prepare_current_report(runtime, db_path, monkeypatch)
    loaded = read_validated_record(runtime / "perf")
    assert loaded.record is not None
    before = loaded.record
    generation = cli._expected_generation(before)
    assert generation is not None
    after = replace(
        before,
        size_bucket="128-512 MiB",
        sessions=before.sessions[:-1]
        + (replace(before.sessions[-1], size_bucket="128-512 MiB"),),
    )

    with pytest.raises(cli.RecordValidationError, match="not comparable"):
        cli._validate_post_action_report(
            before,
            after,
            expected_generation=generation,
        )
