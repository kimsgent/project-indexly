import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexly.cli_utils import build_parser
from indexly.rename_watch.config import RenameWatchConfigError, load_settings
from indexly.rename_watch.identity import state_namespace
from indexly.rename_watch.journal import MoveJournal
from indexly.rename_watch import status as status_module


def _config(tmp_path, jobs=None):
    incoming = tmp_path / "incoming"
    incoming.mkdir(exist_ok=True)
    if jobs is None:
        jobs = [
            {
                "id": "inbox",
                "watch_path": "incoming",
                "destination_subfolder": "processed",
                "settle_seconds": 0.01,
                "scan_interval_seconds": 10,
            }
        ]
    path = tmp_path / "rename-watch.json"
    path.write_text(json.dumps({"version": 1, "jobs": jobs}), encoding="utf-8")
    return path


def _event(job, event, timestamp, operation_id=None, **values):
    record = {
        "timestamp": timestamp,
        "event": event,
        "job_id": job.job_id,
        "job_namespace": state_namespace(job.watch_path, job.job_id),
        "source_path": str(job.watch_path / values.pop("source", "report.txt")),
        "destination_path": str(
            job.destination_path / values.pop("destination", "report.txt")
        ),
        "pattern": job.pattern,
        "attempts": values.pop("attempts", 1),
    }
    if operation_id is not None:
        record["operation_id"] = operation_id
    record.update(values)
    return record


def _write_records(log_root, name, records, final_newline=True):
    log_root.mkdir(parents=True, exist_ok=True)
    payload = b"\n".join(json.dumps(record).encode("utf-8") for record in records)
    if final_newline:
        payload += b"\n"
    (log_root / name).write_bytes(payload)


def _tree_bytes(root):
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_status_schema_missing_runtime_state_is_read_only(tmp_path):
    config = _config(tmp_path)
    runtime = tmp_path / "runtime-does-not-exist"
    observed = datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc)

    result = status_module.build_status(
        str(config), base_dir=runtime, observed_at=observed
    )

    assert result == {
        "schema": "indexly.rename-watch.status",
        "version": 1,
        "observed_at": "2026-07-16T18:30:00+00:00",
        "config_path": str(config.resolve()),
        "degraded": False,
        "warnings": [],
        "log_scan": {
            "complete": True,
            "files_read": 0,
            "files_skipped": 0,
            "records_skipped": 0,
            "unknown_job_records": 0,
        },
        "jobs": [
            {
                "id": "inbox",
                "mode": "hybrid",
                "watch_path": str((tmp_path / "incoming").resolve()),
                "destination_path": str((tmp_path / "incoming/processed").resolve()),
                "watch_path_status": "available",
                "pending_queue_available": False,
                "pending_queue": None,
                "recovery_state": "available",
                "pending_recovery_operations": [],
                "last_successful_move": None,
                "retained_terminal_failure_count": 0,
                "recent_terminal_failures": [],
            }
        ],
    }
    assert not runtime.exists()
    assert not (tmp_path / "incoming/processed").exists()


def test_rotated_logs_are_naturally_ordered_deduplicated_and_bounded(tmp_path):
    config = _config(tmp_path)
    job = load_settings(str(config)).jobs[0]
    log_root = tmp_path / "logs"
    operation_id = str(uuid.uuid4())
    first = _event(
        job,
        "RENAME_WATCH_MOVED",
        "2026-07-16T10:00:00+00:00",
        operation_id,
        destination="older.txt",
    )
    second = _event(
        job,
        "RENAME_WATCH_MOVED",
        "2026-07-16T10:00:00+00:00",
        operation_id,
        destination="newer.txt",
    )
    failures = [
        _event(
            job,
            "RENAME_WATCH_FAILED",
            "2026-07-16T{0:02d}:00:00+00:00".format(hour),
            error_type="PermissionError",
            error="locked {0}".format(hour),
        )
        for hour in range(12)
    ]
    _write_records(log_root, "2_index_events.ndjson", [first] + failures[:6])
    _write_records(log_root, "10_index_events.ndjson", [second] + failures[6:])

    result = status_module.build_status(
        str(config), log_root=log_root, state_root=tmp_path / "state"
    )
    output = result["jobs"][0]

    assert result["log_scan"]["files_read"] == 2
    assert output["last_successful_move"]["destination_path"].endswith("newer.txt")
    assert output["retained_terminal_failure_count"] == 12
    assert len(output["recent_terminal_failures"]) == 10
    assert output["recent_terminal_failures"][0]["error"] == "locked 11"


def test_legacy_timestamp_is_preserved_and_attribution_is_degraded(tmp_path):
    config = _config(tmp_path)
    job = load_settings(str(config)).jobs[0]
    record = _event(
        job,
        "RENAME_WATCH_MOVED",
        "2026-07-16T12:34:56",
        str(uuid.uuid4()),
    )
    record.pop("job_namespace")
    second = dict(record, operation_id=str(uuid.uuid4()))
    log_root = tmp_path / "logs"
    _write_records(log_root, "legacy_index_events.ndjson", [record, second])

    result = status_module.build_status(
        str(config), log_root=log_root, state_root=tmp_path / "state"
    )

    assert result["degraded"] is True
    assert result["jobs"][0]["last_successful_move"]["timestamp"] == record["timestamp"]
    assert result["jobs"][0]["last_successful_move"]["legacy_ambiguous"] is True
    legacy_warnings = [
        warning
        for warning in result["warnings"]
        if warning["code"] == "legacy_ambiguous_records"
    ]
    assert legacy_warnings == [
        {
            "code": "legacy_ambiguous_records",
            "message": "legacy records were attributed by job id and lexical paths",
            "job_id": "inbox",
            "count": 2,
        }
    ]


def test_mixed_legacy_history_uses_retained_append_order(tmp_path):
    config = _config(tmp_path)
    job = load_settings(str(config)).jobs[0]
    legacy = _event(
        job,
        "RENAME_WATCH_MOVED",
        "2026-07-16T12:00:00",
        str(uuid.uuid4()),
        destination="legacy.txt",
    )
    legacy.pop("job_namespace")
    current = _event(
        job,
        "RENAME_WATCH_MOVED",
        "2026-07-16T11:00:00+00:00",
        str(uuid.uuid4()),
        destination="current.txt",
    )
    log_root = tmp_path / "logs"
    _write_records(log_root, "2_index_events.ndjson", [legacy])
    _write_records(log_root, "alpha_index_events.ndjson", [current])

    result = status_module.build_status(
        str(config), log_root=log_root, state_root=tmp_path / "state"
    )

    assert result["log_scan"]["files_read"] == 2
    assert result["jobs"][0]["last_successful_move"]["destination_path"].endswith(
        "current.txt"
    )


def test_partial_logs_skip_bad_records_links_and_unknown_jobs(tmp_path):
    config = _config(tmp_path)
    job = load_settings(str(config)).jobs[0]
    log_root = tmp_path / "logs"
    unknown = _event(
        job,
        "RENAME_WATCH_MOVED",
        "2026-07-16T12:00:00+00:00",
        str(uuid.uuid4()),
    )
    unknown["job_namespace"] = "f" * 64
    unknown["source_path"] = "/secret/unknown/source.txt"
    unknown["destination_path"] = "/secret/unknown/destination.txt"
    _write_records(log_root, "one_index_events.ndjson", [unknown])
    with (log_root / "two_index_events.ndjson").open("wb") as handle:
        handle.write(b"\xff\n")
        handle.write(b'{"event":"RENAME_WATCH_MOVED"}')
    target = tmp_path / "outside.ndjson"
    target.write_text("{}\n", encoding="utf-8")
    (log_root / "linked_index_events.ndjson").symlink_to(target)

    result = status_module.build_status(
        str(config), log_root=log_root, state_root=tmp_path / "state"
    )
    serialized_warnings = json.dumps(result["warnings"])

    assert result["degraded"] is True
    assert result["log_scan"]["unknown_job_records"] == 1
    assert result["log_scan"]["files_skipped"] == 1
    assert result["log_scan"]["records_skipped"] == 2
    assert "/secret/unknown" not in serialized_warnings


def test_valid_journal_is_sorted_rendered_and_not_mutated(tmp_path):
    config = _config(tmp_path)
    job = load_settings(str(config)).jobs[0]
    state_root = tmp_path / "state"
    source = job.watch_path / "report.txt"
    source.write_text("content", encoding="utf-8")
    journal = MoveJournal(job, state_root)
    later = journal.prepare(
        source,
        job.destination_path / "later.txt",
        {"device": 1, "inode": 2, "size": 7, "mtime_ns": 3},
        job.pattern,
        2,
    )
    earlier = journal.prepare(
        source,
        job.destination_path / "earlier.txt",
        {"device": 1, "inode": 2, "size": 7, "mtime_ns": 3},
        job.pattern,
        1,
    )
    for record, timestamp in (
        (later, "2026-07-16T12:00:00+00:00"),
        (earlier, "2026-07-16T11:00:00+00:00"),
    ):
        record["created_at"] = timestamp
        journal._path(record["operation_id"]).write_text(
            json.dumps(record), encoding="utf-8"
        )
    before = _tree_bytes(state_root)

    result = status_module.build_status(
        str(config), log_root=tmp_path / "logs", state_root=state_root
    )
    pending = result["jobs"][0]["pending_recovery_operations"]
    human = status_module.render_human(result)

    assert [item["operation_id"] for item in pending] == [
        earlier["operation_id"],
        later["operation_id"],
    ]
    assert pending[0]["source_path"] == str(source.resolve())
    assert pending[0]["attempts"] == 1
    assert earlier["operation_id"] in human
    assert _tree_bytes(state_root) == before


@pytest.mark.parametrize("kind", ["corrupt", "journal_link", "parent_link"])
def test_active_journal_corruption_and_links_fail_closed(tmp_path, kind):
    config = _config(tmp_path)
    job = load_settings(str(config)).jobs[0]
    state_root = tmp_path / "state"
    journal = MoveJournal(job, state_root)
    if kind == "parent_link":
        state_root.mkdir()
        target = tmp_path / "journal-target"
        target.mkdir()
        (state_root / "journals").symlink_to(target, target_is_directory=True)
    else:
        journal.directory.mkdir(parents=True)
        path = journal.directory / (str(uuid.uuid4()) + ".json")
        if kind == "corrupt":
            path.write_text("{}", encoding="utf-8")
        else:
            target = tmp_path / "outside.json"
            target.write_text("{}", encoding="utf-8")
            path.symlink_to(target)

    with pytest.raises(RenameWatchConfigError, match="recovery journal"):
        status_module.build_status(
            str(config), log_root=tmp_path / "logs", state_root=state_root
        )


def test_status_parser_dispatch_is_lazy_and_rejects_mixed_actions(
    tmp_path, monkeypatch
):
    parser = build_parser()
    config = _config(tmp_path)
    args = parser.parse_args(
        ["rename-watch", "--config", str(config), "--status", "--json"]
    )
    assert args.status and args.rename_watch_status_json

    import indexly.rename_watch as package

    sys.modules.pop("indexly.rename_watch.service", None)
    monkeypatch.setattr(status_module, "render_status", lambda *args, **kwargs: "ok")
    assert package.handle_rename_watch(args) == "ok"
    assert "indexly.rename_watch.service" not in sys.modules

    with pytest.raises(ValueError, match="only with --status"):
        package.handle_rename_watch(
            SimpleNamespace(
                config=str(config),
                status=False,
                rename_watch_status_json=True,
                init=False,
                check_config=False,
                once=False,
                dry_run=False,
                mode=None,
            )
        )
    mixed = SimpleNamespace(**vars(args))
    mixed.once = True
    with pytest.raises(ValueError, match="cannot be combined"):
        package.handle_rename_watch(mixed)


def test_status_json_suppresses_update_check_and_emits_one_document(
    tmp_path, monkeypatch, capsys
):
    import indexly.indexly as app
    import indexly.update_utils as update_utils

    args = SimpleNamespace(
        command="rename-watch",
        status=True,
        rename_watch_status_json=True,
        no_update_check=False,
        show_license=False,
        version=False,
        check_updates=False,
        func=lambda value: print('{"schema":"only"}'),
    )

    class Parser:
        def parse_known_args(self):
            return args, []

        def parse_args(self):
            return args

    monkeypatch.setattr(app, "build_parser", lambda: Parser())
    monkeypatch.setattr(
        update_utils,
        "check_for_updates",
        lambda: (_ for _ in ()).throw(AssertionError("update check ran")),
    )

    app.main()

    assert capsys.readouterr().out == '{"schema":"only"}\n'


@pytest.mark.parametrize("module", ["indexly", "indexly.indexly"])
@pytest.mark.parametrize("json_output", [False, True])
def test_fresh_status_is_ascii_safe_and_has_no_runtime_side_effects(
    tmp_path, module, json_output
):
    job_id = "caf\u00e9\n\x1b"
    config = _config(
        tmp_path,
        jobs=[
            {
                "id": job_id,
                "watch_path": "incoming",
                "destination_subfolder": "processed",
            }
        ],
    )
    runtime = tmp_path / "runtime"
    isolated_home = tmp_path / "home"
    command = [
        sys.executable,
        "-m",
        module,
        "rename-watch",
        "--config",
        str(config),
        "--status",
    ]
    if json_output:
        command.append("--json")
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(isolated_home),
            "INDEXLY_HOME": str(runtime),
            "PYTHONIOENCODING": "ascii",
        }
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=environment,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert not runtime.exists()
    assert not isolated_home.exists()
    if json_output:
        assert json.loads(result.stdout)["jobs"][0]["id"] == job_id
        assert result.stdout.count("\n") == 1
    else:
        assert "caf\\u00e9\\n\\u001b" in result.stdout
        assert "\x1b" not in result.stdout


def test_status_import_has_no_service_planner_locking_or_logging_side_effects():
    script = """
import sys
import indexly.rename_watch.status
for name in (
    'indexly.rename_watch.service',
    'indexly.rename_watch.planner',
    'indexly.rename_watch.locking',
    'indexly.rename_watch.logging',
):
    assert name not in sys.modules, name
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
