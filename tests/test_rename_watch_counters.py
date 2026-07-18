import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexly.cli_utils import build_parser
from indexly.rename_watch import handle_rename_watch
from indexly.rename_watch.config import RenameWatchConfigError, load_settings
from indexly.rename_watch.error_contract import RenameWatchUsageError
from indexly.rename_watch.counter_operator import (
    BACKUP_SCHEMA,
    COUNTER_SCHEMA,
    RESET_SCHEMA,
    build_counter_inspection,
    reset_counters,
)
from indexly.rename_watch.counter_state import CounterState, MAX_COUNTER_STATE_BYTES
from indexly.rename_watch.locking import WatchRootLock


def _config(tmp_path, jobs=None):
    jobs = jobs or [
        {
            "id": "alpha",
            "watch_path": "incoming",
            "destination_subfolder": "done",
            "pattern": "{date}-{title}-{counter}",
            "date_format": "%Y%m%d",
            "counter_format": "03d",
        }
    ]
    path = tmp_path / "rename-watch.json"
    path.write_text(json.dumps({"version": 1, "jobs": jobs}), encoding="utf-8")
    return path


def _state(tmp_path, config):
    job = load_settings(str(config)).jobs[0]
    state = CounterState(job, tmp_path / "runtime" / "rename-watch")
    state.root.mkdir(parents=True)
    return job, state


def test_parser_counter_actions_are_mutually_exclusive_and_accept_options(tmp_path):
    parser = build_parser()
    args = parser.parse_args(
        [
            "rename-watch", "--config", str(tmp_path / "c.json"),
            "--reset-counters", "--job", "alpha", "--date-key", "20240101",
            "--yes", "--json",
        ]
    )
    assert args.reset_counters is True
    assert args.job == "alpha"
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["rename-watch", "--config", "c.json", "--status", "--inspect-counters"]
        )


def test_handle_rejects_json_and_reset_only_options_without_matching_action():
    base = dict(
        config="c.json", init=False, check_config=False, status=False,
        inspect_counters=False, reset_counters=False, once=False, dry_run=False,
        mode=None, job=None, date_key=None, all_counters=False, yes=False,
    )
    with pytest.raises(ValueError, match="--json is valid"):
        handle_rename_watch(SimpleNamespace(**base, rename_watch_status_json=True))
    base["inspect_counters"] = True
    base["date_key"] = "20240101"
    with pytest.raises(ValueError, match="valid only with --reset-counters"):
        handle_rename_watch(SimpleNamespace(**base, rename_watch_status_json=False))


def test_inspection_schema_order_filter_storage_and_same_id_namespaces(tmp_path):
    config = _config(
        tmp_path,
        [
            {
                "id": "first", "watch_path": "one", "destination_subfolder": "done",
                "pattern": "{date}-{counter}", "date_format": "%Y%m%d", "counter_format": "d",
            },
            {
                "id": "plain", "watch_path": "two", "destination_subfolder": "done",
                "pattern": "{date}-{title}", "date_format": "%Y%m%d", "counter_format": "",
            },
        ],
    )
    runtime = tmp_path / "runtime"
    first = CounterState(load_settings(str(config)).jobs[0], runtime / "rename-watch")
    first.root.mkdir(parents=True)
    first.path.write_text('{"2024-01-02": 7, "20240101": 3}', encoding="utf-8")
    result = build_counter_inspection(str(config), base_dir=runtime)
    assert result["schema"] == COUNTER_SCHEMA
    assert [job["id"] for job in result["jobs"]] == ["first", "plain"]
    assert result["jobs"][0]["entries"] == [
        {"date_key": "2024-01-02", "next_value": 7},
        {"date_key": "20240101", "next_value": 3},
    ]
    assert result["jobs"][1]["storage"] == "not_applicable"
    assert build_counter_inspection(str(config), job_id="plain", base_dir=runtime)["jobs"][0]["id"] == "plain"
    with pytest.raises(RenameWatchConfigError, match="not found"):
        build_counter_inspection(str(config), job_id="FIRST", base_dir=runtime)


def test_no_counter_job_does_not_touch_stale_counter_file(tmp_path, monkeypatch):
    config = _config(
        tmp_path,
        [{
            "id": "plain", "watch_path": "in", "destination_subfolder": "done",
            "pattern": "{date}-{title}", "date_format": "%Y%m%d", "counter_format": "",
        }],
    )
    monkeypatch.setattr(CounterState, "snapshot", lambda self: (_ for _ in ()).throw(AssertionError("read")))
    result = build_counter_inspection(str(config), base_dir=tmp_path / "missing-runtime")
    assert result["jobs"][0]["storage"] == "not_applicable"
    assert not (tmp_path / "missing-runtime").exists()


@pytest.mark.parametrize(
    "payload",
    [b"not-json", b"[]", b'{"20240101": true}', b'{"bad": 1}', b'{"20240101": -1}', b'\xff'],
)
def test_strict_counter_reader_rejects_invalid_state(tmp_path, payload):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_bytes(payload)
    with pytest.raises(RenameWatchConfigError):
        state.strict_snapshot()


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific open mode")
def test_strict_counter_reader_opens_counter_state_in_binary_mode(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 1}', encoding="utf-8")
    real_open = os.open
    flags_seen = []

    def capture_open(path, flags, *args, **kwargs):
        flags_seen.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("indexly.rename_watch.counter_state.os.open", capture_open)

    assert state.strict_snapshot() == {"20240101": 1}
    assert flags_seen == [
        os.O_RDONLY
        | os.O_BINARY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    ]

def test_strict_counter_reader_rejects_oversize_symlink_and_nonregular(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_bytes(b" " * (MAX_COUNTER_STATE_BYTES + 1))
    with pytest.raises(RenameWatchConfigError, match="oversized"):
        state.strict_snapshot()
    state.path.unlink()
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    if os.name != "nt":
        state.path.symlink_to(target)
        with pytest.raises(RenameWatchConfigError, match="regular file"):
            state.strict_snapshot()
        state.path.unlink()
    state.path.mkdir()
    with pytest.raises(RenameWatchConfigError, match="regular file"):
        state.strict_snapshot()


def test_strict_live_loader_does_not_erase_valid_keys_on_corruption(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4, "bad": 9}', encoding="utf-8")
    before = state.path.read_bytes()
    with pytest.raises(RenameWatchConfigError):
        state.next("20240101")
    with pytest.raises(RenameWatchConfigError):
        state.ensure_at_least("20240101", 5)
    assert state.path.read_bytes() == before


def test_legacy_inspection_is_ambiguous_and_namespaced_state_shadows_it(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.legacy_path.write_text('{"20240101": 4}', encoding="utf-8")
    first = build_counter_inspection(str(config), base_dir=tmp_path / "runtime")["jobs"][0]
    assert first["storage"] == "legacy" and first["legacy_ambiguous"] is True
    state.path.write_text('{"20240102": 8}', encoding="utf-8")
    second = build_counter_inspection(str(config), base_dir=tmp_path / "runtime")["jobs"][0]
    assert second["storage"] == "namespaced"
    assert second["entries"] == [{"date_key": "20240102", "next_value": 8}]


class _TTY:
    def __init__(self, value=True):
        self.value = value

    def isatty(self):
        return self.value


def test_reset_requires_confirmation_and_exact_existing_key(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    with pytest.raises(RenameWatchConfigError, match="did not match"):
        reset_counters(
            str(config), job_id="alpha", date_key="20240101", base_dir=tmp_path / "runtime",
            input_func=lambda prompt: "reset alpha", stdin=_TTY(),
        )
    with pytest.raises(RenameWatchConfigError, match="does not exist"):
        reset_counters(
            str(config), job_id="alpha", date_key="20240102", yes=True,
            base_dir=tmp_path / "runtime",
        )
    assert json.loads(state.path.read_text()) == {"20240101": 4}


def test_reset_accepts_exact_interactive_phrase(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    result = reset_counters(
        str(config), job_id="alpha", all_counters=True,
        base_dir=tmp_path / "runtime", input_func=lambda prompt: "RESET alpha", stdin=_TTY(),
    )
    assert result["changed"] is True


def test_reset_non_tty_and_json_require_yes(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    with pytest.raises(RenameWatchConfigError, match="not a TTY"):
        reset_counters(
            str(config), job_id="alpha", all_counters=True,
            base_dir=tmp_path / "runtime", stdin=_TTY(False),
        )


def test_reset_rejects_job_without_counter(tmp_path):
    config = _config(
        tmp_path,
        [{
            "id": "plain", "watch_path": "in", "destination_subfolder": "done",
            "pattern": "{date}-{title}", "date_format": "%Y%m%d", "counter_format": "",
        }],
    )
    with pytest.raises(RenameWatchConfigError, match="does not use counters"):
        reset_counters(
            str(config), job_id="plain", all_counters=True, yes=True,
            base_dir=tmp_path / "runtime",
        )
    with pytest.raises(RenameWatchUsageError, match="requires --yes"):
        reset_counters(
            str(config), job_id="alpha", all_counters=True, json_output=True,
            base_dir=tmp_path / "runtime",
        )


def test_reset_writes_durable_backup_before_namespaced_mutation(tmp_path):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.legacy_path.write_text('{"20240101": 4, "20240102": 8}', encoding="utf-8")
    legacy_before = state.legacy_path.read_bytes()
    result = reset_counters(
        str(config), job_id="alpha", date_key="20240101", yes=True,
        base_dir=tmp_path / "runtime",
    )
    assert result["schema"] == RESET_SCHEMA and result["changed"] is True
    backup = json.loads(Path(result["backup_path"]).read_text(encoding="utf-8"))
    assert backup["schema"] == BACKUP_SCHEMA
    assert backup["source_storage"] == "legacy"
    assert backup["counters"] == {"20240101": 4, "20240102": 8}
    assert json.loads(state.path.read_text()) == {"20240102": 8}
    assert state.legacy_path.read_bytes() == legacy_before
    if os.name != "nt":
        assert stat_mode(Path(result["backup_path"])) == 0o600


def stat_mode(path):
    return path.stat().st_mode & 0o777


def test_all_reset_empty_state_is_noop_without_backup_or_state_write(tmp_path):
    config = _config(tmp_path)
    result = reset_counters(
        str(config), job_id="alpha", all_counters=True, yes=True,
        base_dir=tmp_path / "runtime",
    )
    assert result["changed"] is False and result["backup_path"] is None
    assert not (tmp_path / "runtime").exists()


def test_reset_refuses_pending_journal_and_backup_failure_preserves_state(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    import indexly.rename_watch.counter_operator as operator

    monkeypatch.setattr(operator, "read_journal_records", lambda job, root: [{"state": "prepared"}])
    with pytest.raises(RenameWatchConfigError, match="pending recovery"):
        reset_counters(
            str(config), job_id="alpha", all_counters=True, yes=True,
            base_dir=tmp_path / "runtime",
        )
    monkeypatch.setattr(operator, "read_journal_records", lambda job, root: [])
    monkeypatch.setattr(operator, "_write_backup", lambda *args: (_ for _ in ()).throw(RenameWatchConfigError("backup failed")))
    with pytest.raises(RenameWatchConfigError, match="backup failed"):
        reset_counters(
            str(config), job_id="alpha", all_counters=True, yes=True,
            base_dir=tmp_path / "runtime",
        )
    assert json.loads(state.path.read_text()) == {"20240101": 4}


def test_inspection_rejects_state_root_symlink_and_same_id_roots_differ(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _config(first_dir)
    second = _config(second_dir)
    first_namespace = build_counter_inspection(str(first), base_dir=tmp_path / "r1")["jobs"][0]["namespace"]
    second_namespace = build_counter_inspection(str(second), base_dir=tmp_path / "r2")["jobs"][0]["namespace"]
    assert first_namespace != second_namespace

    if os.name != "nt":
        runtime = tmp_path / "runtime-link"
        runtime.mkdir()
        target = tmp_path / "outside"
        target.mkdir()
        (runtime / "rename-watch").symlink_to(target, target_is_directory=True)
        with pytest.raises(RenameWatchConfigError, match="real directory"):
            build_counter_inspection(str(first), base_dir=runtime)


def test_reset_rejects_real_corrupt_journal(tmp_path):
    config = _config(tmp_path)
    job, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    journal_dir = state.root / "journals" / state.namespace
    journal_dir.mkdir(parents=True)
    (journal_dir / "broken.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(RenameWatchConfigError, match="journal is unreadable"):
        reset_counters(
            str(config), job_id=job.job_id, all_counters=True, yes=True,
            base_dir=tmp_path / "runtime",
        )
    assert json.loads(state.path.read_text()) == {"20240101": 4}


def test_reset_holds_watch_lock_through_backup_and_write(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    import indexly.rename_watch.counter_operator as operator

    held = {"value": False}

    class FakeLock:
        def __init__(self, path):
            self.path = path

        def acquire(self):
            held["value"] = True

        def release(self):
            held["value"] = False

    real_backup = operator._write_backup

    def checked_backup(*args, **kwargs):
        assert held["value"] is True
        return real_backup(*args, **kwargs)

    real_save = CounterState._save

    def checked_save(self, values):
        assert held["value"] is True
        return real_save(self, values)

    monkeypatch.setattr(operator, "WatchRootLock", FakeLock)
    monkeypatch.setattr(operator, "_write_backup", checked_backup)
    monkeypatch.setattr(CounterState, "_save", checked_save)
    reset_counters(
        str(config), job_id="alpha", all_counters=True, yes=True,
        base_dir=tmp_path / "runtime",
    )
    assert held["value"] is False


def test_real_held_watch_lock_refuses_reset_without_mutation(tmp_path):
    config = _config(tmp_path)
    job, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    held = WatchRootLock(job.watch_path)
    held.acquire()
    try:
        with pytest.raises(RenameWatchConfigError, match="locked or unavailable"):
            reset_counters(
                str(config), job_id="alpha", all_counters=True, yes=True,
                base_dir=tmp_path / "runtime",
            )
    finally:
        held.release()
    assert json.loads(state.path.read_text()) == {"20240101": 4}
    assert not (state.root / "counter-backups").exists()


def test_backup_directory_symlink_fails_before_state_mutation(tmp_path):
    if os.name == "nt":
        pytest.skip("creating a symlink may require elevated Windows privileges")
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    outside = tmp_path / "outside-backup"
    outside.mkdir()
    (state.root / "counter-backups").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RenameWatchConfigError, match="real directories"):
        reset_counters(
            str(config), job_id="alpha", all_counters=True, yes=True,
            base_dir=tmp_path / "runtime",
        )
    assert json.loads(state.path.read_text()) == {"20240101": 4}
    assert list(outside.iterdir()) == []


def test_state_save_failure_occurs_after_backup_and_preserves_original(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _, state = _state(tmp_path, config)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")

    def fail_save(self, values):
        raise RenameWatchConfigError("injected save failure")

    monkeypatch.setattr(CounterState, "_save", fail_save)
    with pytest.raises(RenameWatchConfigError, match="injected save failure"):
        reset_counters(
            str(config), job_id="alpha", all_counters=True, yes=True,
            base_dir=tmp_path / "runtime",
        )
    assert json.loads(state.path.read_text()) == {"20240101": 4}
    backups = list((state.root / "counter-backups" / state.namespace).glob("*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["counters"] == {"20240101": 4}


def test_fresh_process_inspection_json_is_ascii_and_runtime_pure(tmp_path):
    config = _config(
        tmp_path,
        [{
            "id": "caf\u00e9\njob", "watch_path": "in", "destination_subfolder": "done",
            "pattern": "{date}-{title}-{counter}", "date_format": "%Y%m%d", "counter_format": "d",
        }],
    )
    runtime = tmp_path / "must-not-exist"
    env = dict(os.environ)
    env["INDEXLY_HOME"] = os.fspath(runtime)
    env["PYTHONPATH"] = os.fspath(Path(__file__).parents[1] / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "indexly", "rename-watch", "--config", str(config), "--inspect-counters", "--json"],
        cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout.count("\n") == 1
    assert all(ord(character) < 128 for character in completed.stdout)
    assert json.loads(completed.stdout)["schema"] == COUNTER_SCHEMA
    assert not runtime.exists()

    direct = subprocess.run(
        [sys.executable, "-m", "indexly.indexly", "rename-watch", "--config", str(config), "--inspect-counters", "--json"],
        cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True, check=False,
    )
    assert direct.returncode == 0 and direct.stderr == ""
    assert json.loads(direct.stdout)["schema"] == COUNTER_SCHEMA
    assert not runtime.exists()


def test_fresh_process_reset_json_is_one_ascii_document(tmp_path):
    config = _config(tmp_path)
    runtime = tmp_path / "runtime-cli"
    job = load_settings(str(config)).jobs[0]
    state = CounterState(job, runtime / "rename-watch")
    state.root.mkdir(parents=True)
    state.path.write_text('{"20240101": 4}', encoding="utf-8")
    env = dict(os.environ)
    env["INDEXLY_HOME"] = os.fspath(runtime)
    env["PYTHONPATH"] = os.fspath(Path(__file__).parents[1] / "src")
    completed = subprocess.run(
        [
            sys.executable, "-m", "indexly", "rename-watch", "--config", str(config),
            "--reset-counters", "--job", "alpha", "--all-counters", "--yes", "--json",
        ],
        cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0 and completed.stderr == ""
    assert completed.stdout.count("\n") == 1
    assert all(ord(character) < 128 for character in completed.stdout)
    assert json.loads(completed.stdout)["schema"] == RESET_SCHEMA
