import json
import errno
import math
import os
import stat
import subprocess
import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from indexly.cli_utils import build_parser
from indexly.rename_watch.config import RenameWatchConfigError, initialize_settings, load_settings
from indexly.rename_watch import locking as locking_module
from indexly.rename_watch import identity as identity_module
from indexly.rename_watch import planner as planner_module
from indexly.rename_watch.locking import WatchRootLock
from indexly.rename_watch.planner import PlanMoveLog
from indexly.rename_watch import service as service_module
from indexly.rename_watch.service import RenameWatchService, handle_rename_watch


def _config(tmp_path, **job_values):
    incoming = tmp_path / "incoming"; incoming.mkdir(exist_ok=True)
    job = {"id": "inbox", "watch_path": "incoming", "destination_subfolder": "processed", "settle_seconds": 0.01, "scan_interval_seconds": 10}
    job.update(job_values)
    path = tmp_path / "rename-watch.json"; path.write_text(json.dumps({"version": 1, "jobs": [job]}), encoding="utf-8")
    return path, incoming


def test_config_resolves_paths_relative_to_config(tmp_path):
    path, incoming = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]
    assert job.watch_path == incoming.resolve()
    assert job.destination_path == (incoming / "processed").resolve()


def test_config_allows_missing_watch_path_without_creating_it(tmp_path):
    path, incoming = _config(tmp_path)
    incoming.rmdir()

    job = load_settings(str(path)).jobs[0]

    assert job.watch_path == incoming.resolve()
    assert not incoming.exists()


def test_config_rejects_watch_path_that_is_a_file(tmp_path):
    path, incoming = _config(tmp_path)
    incoming.rmdir()
    incoming.write_text("not a directory", encoding="utf-8")

    try:
        load_settings(str(path))
    except RenameWatchConfigError:
        pass
    else:
        raise AssertionError("a watch path that is a file must be rejected")


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_config_rejects_nonfinite_timing_values(tmp_path, value):
    path, _ = _config(tmp_path, settle_seconds=value)

    with pytest.raises(RenameWatchConfigError, match="positive number"):
        load_settings(str(path))


def test_planner_moves_and_creates_destination(tmp_path):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    job = load_settings(str(path)).jobs[0]
    source = incoming / "My report.txt"; source.write_text("content", encoding="utf-8")
    target = PlanMoveLog(job, tmp_path / "state").plan_and_move(source)
    assert target.exists() and target.parent == job.destination_path and not source.exists()


def test_recovery_resumes_prepared_counter_operation_without_consuming_another_counter(
    tmp_path, monkeypatch
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)

    monkeypatch.setattr(
        mover.state,
        "_save",
        lambda data: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        mover.plan_and_move_operation(source)

    prepared = mover.journal.pending()[0]
    assert prepared["state"] == "prepared"
    assert prepared["counter"] == 0
    assert source.exists()
    assert not Path(prepared["destination_path"]).exists()

    recovered_mover = PlanMoveLog(job, state_root)
    recovered = recovered_mover.recover_pending(source, attempts=4)[0]
    assert recovered.operation_id == prepared["operation_id"]
    assert recovered.attempts == 4
    assert recovered.destination == Path(prepared["destination_path"])
    assert recovered.destination.read_text(encoding="utf-8") == "content"
    assert not source.exists()
    assert recovered_mover.state._load()[prepared["date_key"]] == 1
    recovered_mover.complete(recovered.operation_id)


def test_abrupt_exit_after_hard_link_fails_closed_with_both_links_preserved(tmp_path):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    script = """
import os
import sys
from pathlib import Path
from indexly.rename_watch.config import load_settings
from indexly.rename_watch import planner as p

job = load_settings(sys.argv[1]).jobs[0]
source = Path(sys.argv[2])
state = Path(sys.argv[3])

def crash(
    source_path,
    target_path,
    destination_created,
    destination_finalized,
    expected_source_identity=None,
):
    os.link(source_path, target_path)
    destination_created(p._destination_identity(target_path.stat()))
    os._exit(23)

p._move_without_overwrite = crash
p.PlanMoveLog(job, state).plan_and_move_operation(source)
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(path), str(source), str(state_root)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 23, process.stderr
    pending = PlanMoveLog(job, state_root).journal.pending()[0]
    target = Path(pending["destination_path"])
    assert source.exists() and target.exists()
    assert os.path.samestat(source.stat(), target.stat())

    mover = PlanMoveLog(job, state_root)
    with pytest.raises(RenameWatchConfigError, match="duplicate hard links"):
        mover.recover_pending()
    assert source.exists()
    assert target.read_text(encoding="utf-8") == "content"
    assert list(job.destination_path.iterdir()) == [target]


def test_recovery_preserves_source_and_partial_copy_for_manual_resolution(
    tmp_path, monkeypatch
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("complete content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"

    def crash_during_copy(
        source_path,
        target_path,
        destination_created,
        destination_finalized,
        expected_source_identity=None,
    ):
        with target_path.open("xb") as handle:
            handle.write(b"partial")
        destination_created(planner_module._destination_identity(target_path.stat()))
        raise KeyboardInterrupt()

    monkeypatch.setattr(planner_module, "_move_without_overwrite", crash_during_copy)
    with pytest.raises(KeyboardInterrupt):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)

    monkeypatch.undo()
    mover = PlanMoveLog(job, state_root)
    with pytest.raises(RenameWatchConfigError, match="both files were preserved"):
        mover.recover_pending()
    pending = mover.journal.pending()[0]
    assert source.read_text(encoding="utf-8") == "complete content"
    assert Path(pending["destination_path"]).read_text(encoding="utf-8") == "partial"


def test_recovery_detects_completed_move_before_moved_transition(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    real_move = planner_module._move_without_overwrite

    def move_then_interrupt(
        source_path,
        target_path,
        destination_created,
        destination_finalized,
        expected_source_identity=None,
    ):
        real_move(
            source_path,
            target_path,
            destination_created,
            destination_finalized,
            expected_source_identity,
        )
        raise KeyboardInterrupt()

    monkeypatch.setattr(planner_module, "_move_without_overwrite", move_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)
    pending = PlanMoveLog(job, state_root).journal.pending()[0]
    assert pending["state"] == "destination_finalized"
    assert not source.exists()

    monkeypatch.undo()
    mover = PlanMoveLog(job, state_root)
    recovered = mover.recover_pending()[0]
    assert recovered.destination.read_text(encoding="utf-8") == "content"
    mover.complete(recovered.operation_id)


def test_recovery_fails_closed_when_owned_destination_identity_changes(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("source", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"

    def leave_destination(
        source_path,
        target_path,
        destination_created,
        destination_finalized,
        expected_source_identity=None,
    ):
        target_path.write_text("partial", encoding="utf-8")
        destination_created(planner_module._destination_identity(target_path.stat()))
        raise KeyboardInterrupt()

    monkeypatch.setattr(planner_module, "_move_without_overwrite", leave_destination)
    with pytest.raises(KeyboardInterrupt):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)
    pending = PlanMoveLog(job, state_root).journal.pending()[0]
    target = Path(pending["destination_path"])
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("external", encoding="utf-8")
    os.replace(replacement, target)

    monkeypatch.undo()
    with pytest.raises(RenameWatchConfigError, match="destination identity changed"):
        PlanMoveLog(job, state_root).recover_pending()
    assert source.read_text(encoding="utf-8") == "source"
    assert target.read_text(encoding="utf-8") == "external"


def test_recovery_rejects_unreliable_zero_destination_identity(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("source", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"

    def leave_destination(
        source_path,
        target_path,
        destination_created,
        destination_finalized,
        expected_source_identity=None,
    ):
        target_path.write_text("partial", encoding="utf-8")
        destination_created({"device": 0, "inode": 0})
        raise KeyboardInterrupt()

    monkeypatch.setattr(planner_module, "_move_without_overwrite", leave_destination)
    with pytest.raises(KeyboardInterrupt):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)
    monkeypatch.undo()

    with pytest.raises(RenameWatchConfigError, match="identity is not reliable"):
        PlanMoveLog(job, state_root).recover_pending()
    assert source.read_text(encoding="utf-8") == "source"
    pending = PlanMoveLog(job, state_root).journal.pending()[0]
    assert Path(pending["destination_path"]).read_text(encoding="utf-8") == "partial"


def test_source_missing_requires_destination_finalized_phase(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("1234567", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"

    def leave_same_size_corruption(
        source_path,
        target_path,
        destination_created,
        destination_finalized,
        expected_source_identity=None,
    ):
        target_path.write_text("7654321", encoding="utf-8")
        destination_created(planner_module._destination_identity(target_path.stat()))
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        planner_module, "_move_without_overwrite", leave_same_size_corruption
    )
    with pytest.raises(KeyboardInterrupt):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)
    source.unlink()
    monkeypatch.undo()

    with pytest.raises(RenameWatchConfigError, match="destination is not verified"):
        PlanMoveLog(job, state_root).recover_pending()


def test_service_recovers_moved_journal_and_audits_stable_operation_id(
    tmp_path, monkeypatch
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    result = PlanMoveLog(job, state_root).plan_and_move_operation(source, attempts=3)
    calls = []

    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    service = RenameWatchService([job], state_root=state_root)
    service._recover_pending_moves()

    assert calls[0][0][1:5] == (
        result.source,
        result.destination,
        result.pattern,
        3,
    )
    assert calls[0][1] == {
        "operation_id": result.operation_id,
        "recovered": True,
    }
    assert service.movers[job.job_id].journal.pending() == []


def test_audit_failure_retains_moved_journal_for_stable_retry(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    result = PlanMoveLog(job, state_root).plan_and_move_operation(source)
    service = RenameWatchService([job], state_root=state_root)

    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("audit unavailable")),
    )
    with pytest.raises(OSError, match="audit unavailable"):
        service._recover_pending_moves()
    pending = service.movers[job.job_id].journal.pending()
    assert pending[0]["state"] == "moved"
    assert pending[0]["operation_id"] == result.operation_id

    calls = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    RenameWatchService([job], state_root=state_root)._recover_pending_moves()
    assert calls == [{"operation_id": result.operation_id, "recovered": True}]


def test_moved_recovery_rejects_same_size_destination_modification(tmp_path):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("original", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    result = PlanMoveLog(job, state_root).plan_and_move_operation(source)
    original_mtime = result.destination.stat().st_mtime_ns
    result.destination.write_text("modified", encoding="utf-8")
    os.utime(
        result.destination,
        ns=(original_mtime + 5_000_000_000, original_mtime + 5_000_000_000),
    )

    with pytest.raises(RenameWatchConfigError, match="metadata changed"):
        PlanMoveLog(job, state_root).recover_pending()


def test_no_counter_recovery_does_not_read_or_change_legacy_counter_state(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path, pattern="{date}-{title}", counter_format=""
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    state_root.mkdir()
    legacy = state_root / "inbox.json"
    legacy.write_text(json.dumps({"20260716": 9}), encoding="utf-8")

    monkeypatch.setattr(
        planner_module,
        "_move_without_overwrite",
        lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)
    monkeypatch.undo()

    mover = PlanMoveLog(job, state_root)
    recovered = mover.recover_pending()[0]
    assert json.loads(legacy.read_text(encoding="utf-8")) == {"20260716": 9}
    assert not mover.state.path.exists()
    mover.complete(recovered.operation_id)


def test_state_paths_hash_unsafe_job_ids_and_separate_roots(tmp_path):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    first_job = replace(load_settings(str(path)).jobs[0], job_id="../unsafe")
    second_root = tmp_path / "second"
    second_root.mkdir()
    second_job = replace(
        first_job,
        watch_path=second_root,
        destination_path=second_root / "processed",
    )
    state_root = tmp_path / "state"
    first = PlanMoveLog(first_job, state_root)
    second = PlanMoveLog(second_job, state_root)

    assert first.state.path.parent == state_root
    assert first.state.legacy_path is None
    assert first.state.path != second.state.path
    assert first.journal.directory != second.journal.directory
    assert "unsafe" not in first.state.path.name


def test_canonical_root_identity_normalizes_actual_unicode_spelling(
    tmp_path, monkeypatch
):
    decomposed = tmp_path / "Cafe\u0301"
    monkeypatch.setattr(
        identity_module, "_actual_filesystem_path", lambda path: decomposed
    )

    identity = identity_module.canonical_root_identity(tmp_path / "ignored")

    assert "Cafe\u0301" not in identity
    assert "caf\u00e9" in identity.casefold()


def test_corrupt_recovery_journal_stops_the_affected_job(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    monkeypatch.setattr(
        planner_module,
        "_move_without_overwrite",
        lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    mover = PlanMoveLog(job, state_root)
    with pytest.raises(KeyboardInterrupt):
        mover.plan_and_move_operation(source)
    journal_path = next(mover.journal.directory.glob("*.json"))
    journal_path.write_text("{", encoding="utf-8")

    with pytest.raises(RenameWatchConfigError, match="journal is unreadable"):
        PlanMoveLog(job, state_root).recover_pending()
    assert source.read_text(encoding="utf-8") == "content"


def test_once_ignores_empty_folder_without_logging(tmp_path, monkeypatch):
    path, _ = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]
    calls = []
    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args: calls.append(args))
    RenameWatchService([job], state_root=tmp_path / "state").run_once()
    assert calls == []


def test_once_waits_through_full_retry_schedule_and_can_succeed(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 3,
            "initial_delay_seconds": 2,
            "max_delay_seconds": 4,
        },
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    mover = service.movers[job.job_id]
    real_plan = mover.plan_and_move_operation
    attempts_seen = []
    audits = []

    def fail_twice(source_path, attempts, expected_source_identity=None):
        attempts_seen.append((attempts, current[0]))
        if len(attempts_seen) < 3:
            raise PermissionError("locked")
        return real_plan(source_path, attempts, expected_source_identity)

    mover.plan_and_move_operation = fail_twice
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: audits.append((args, kwargs)),
    )

    service.run_once()

    assert [value[0] for value in attempts_seen] == [1, 2, 3]
    assert current[0] == pytest.approx(7.5)
    assert len(audits) == 1
    assert not source.exists()
    assert service.pending == {}


def test_once_exhausts_retries_and_logs_one_terminal_failure(tmp_path, monkeypatch):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 3,
            "initial_delay_seconds": 2,
            "max_delay_seconds": 4,
        },
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    attempts_seen = []
    failures = []

    def always_locked(source_path, attempts, expected_source_identity=None):
        attempts_seen.append(attempts)
        raise PermissionError("locked")

    service.movers[job.job_id].plan_and_move_operation = always_locked
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )

    service.run_once()

    assert attempts_seen == [1, 2, 3]
    assert len(failures) == 1
    assert failures[0][4] == 3
    assert isinstance(failures[0][5], PermissionError)
    assert source.exists()
    assert service.pending == {}


def test_once_terminal_failure_clears_only_unstarted_journal(tmp_path, monkeypatch):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 2,
            "initial_delay_seconds": 1,
            "max_delay_seconds": 1,
        },
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    failures = []
    monkeypatch.setattr(
        planner_module,
        "_move_without_overwrite",
        lambda *args: (_ for _ in ()).throw(PermissionError("locked")),
    )
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )

    service.run_once()

    assert len(failures) == 1
    assert source.exists()
    assert service.movers[job.job_id].journal.pending() == []


def test_once_times_out_a_continuously_changing_file(tmp_path, monkeypatch):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 2,
            "initial_delay_seconds": 1,
            "max_delay_seconds": 1,
        },
    )
    source = incoming / "report.txt"
    source.write_text("x", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    changes = [1]

    def advance(delay):
        current[0] += delay
        changes[0] += 1
        source.write_text("x" * changes[0], encoding="utf-8")

    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=advance,
    )
    failures = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )

    service.run_once()

    assert len(failures) == 1
    assert isinstance(failures[0][5], TimeoutError)
    assert source.exists()
    assert service.pending == {}
    assert current[0] == pytest.approx(service._once_budget(job))


def test_once_freezes_initial_reconciliation_set(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, settle_seconds=0.5)
    initial = incoming / "initial.txt"
    later = incoming / "later.txt"
    initial.write_text("initial", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]

    def advance(delay):
        current[0] += delay
        if not later.exists():
            later.write_text("later", encoding="utf-8")

    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args, **kwargs: None)

    RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=advance,
    ).run_once()

    assert not initial.exists()
    assert later.read_text(encoding="utf-8") == "later"
    assert len(list(job.destination_path.iterdir())) == 1


def test_once_does_not_consume_replacement_at_frozen_path(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, settle_seconds=0.5)
    source = incoming / "report.txt"
    replacement = tmp_path / "replacement.txt"
    source.write_text("initial", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    replaced = [False]

    def advance(delay):
        current[0] += delay
        if not replaced[0]:
            os.replace(replacement, source)
            replaced[0] = True

    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args, **kwargs: None)
    RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=advance,
    ).run_once()

    assert source.read_text(encoding="utf-8") == "replacement"
    assert not job.destination_path.exists()


def test_once_identity_is_captured_during_reconciliation(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, settle_seconds=0.5)
    source = incoming / "report.txt"
    replacement = tmp_path / "replacement.txt"
    source.write_text("initial", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], state_root=tmp_path / "state")
    real_freeze = service._freeze_once_work

    def replace_before_freeze():
        os.replace(replacement, source)
        return real_freeze()

    service._freeze_once_work = replace_before_freeze
    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args, **kwargs: None)

    service.run_once()

    assert source.read_text(encoding="utf-8") == "replacement"
    assert not job.destination_path.exists()


def test_once_planner_boundary_rejects_last_moment_replacement(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 2,
            "initial_delay_seconds": 1,
            "max_delay_seconds": 1,
        },
    )
    source = incoming / "report.txt"
    replacement = tmp_path / "replacement.txt"
    source.write_text("initial", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    mover = service.movers[job.job_id]
    real_plan = mover.plan_and_move_operation
    replaced = [False]

    def replace_at_boundary(source_path, attempts, expected_source_identity=None):
        if not replaced[0]:
            os.replace(replacement, source_path)
            replaced[0] = True
        return real_plan(source_path, attempts, expected_source_identity)

    mover.plan_and_move_operation = replace_at_boundary
    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args, **kwargs: None)

    service.run_once()

    assert source.read_text(encoding="utf-8") == "replacement"
    assert not job.destination_path.exists()
    assert mover.journal.pending() == []


def test_once_transient_identity_stat_error_uses_retry_policy(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, settle_seconds=0.5)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    real_identity_check = service._once_source_replaced
    checks = [0]
    audits = []

    def fail_once(key, source_path):
        checks[0] += 1
        if checks[0] == 1:
            raise PermissionError("temporary stat failure")
        return real_identity_check(key, source_path)

    service._once_source_replaced = fail_once
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: audits.append((args, kwargs)),
    )

    service.run_once()

    assert checks[0] >= 2
    assert len(audits) == 1
    assert audits[0][0][4] == 2
    assert not source.exists()


def test_once_unavailable_discovery_identity_fails_closed_on_replacement(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 2,
            "initial_delay_seconds": 1,
            "max_delay_seconds": 1,
        },
    )
    source = incoming / "report.txt"
    replacement = tmp_path / "replacement.txt"
    source.write_text("initial", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    real_freeze = service._freeze_once_work
    failures = []
    monkeypatch.setattr(
        service,
        "_capture_once_identity",
        lambda source_path: (_ for _ in ()).throw(PermissionError("stat failed")),
    )

    def replace_before_freeze():
        os.replace(replacement, source)
        return real_freeze()

    service._freeze_once_work = replace_before_freeze
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )

    service.run_once()

    assert len(failures) == 1
    assert isinstance(failures[0][5], OSError)
    assert source.read_text(encoding="utf-8") == "replacement"
    assert not job.destination_path.exists()


def test_once_excludes_other_file_processing_time_from_deadlines(
    tmp_path, monkeypatch
):
    path, first_root = _config(tmp_path, settle_seconds=0.5)
    first_job = load_settings(str(path)).jobs[0]
    first_job = replace(first_job, retry=replace(first_job.retry, max_attempts=1))
    second_root = tmp_path / "second"
    second_root.mkdir()
    second_job = replace(
        first_job,
        job_id="second",
        watch_path=second_root,
        destination_path=second_root / "processed",
        settle_seconds=1.0,
    )
    first_source = first_root / "first.txt"
    second_source = second_root / "second.txt"
    first_source.write_text("first", encoding="utf-8")
    second_source.write_text("second", encoding="utf-8")
    current = [0.0]
    service = RenameWatchService(
        [first_job, second_job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    first_mover = service.movers[first_job.job_id]
    real_first_plan = first_mover.plan_and_move_operation

    def slow_first(source_path, attempts, expected_source_identity=None):
        current[0] += 100.0
        return real_first_plan(source_path, attempts, expected_source_identity)

    first_mover.plan_and_move_operation = slow_first
    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args, **kwargs: None)

    service.run_once()

    assert not first_source.exists()
    assert not second_source.exists()
    assert len(list(second_job.destination_path.iterdir())) == 1


def test_once_fixed_clock_exits_and_releases_root_lock(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, settle_seconds=0.5)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    failures = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )
    service = RenameWatchService(
        [job],
        state_root=tmp_path / "state",
        clock=lambda: 0.0,
        sleeper=lambda delay: None,
    )

    service.run_once()

    assert len(failures) == 1
    assert isinstance(failures[0][5], TimeoutError)
    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


def test_once_budget_handles_huge_retry_count_without_exponentiation(tmp_path):
    path, _ = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]
    job = replace(job, retry=replace(job.retry, max_attempts=10 ** 1000))

    budget = RenameWatchService._once_budget(job)

    assert math.isfinite(budget)
    assert budget > job.retry.max_delay_seconds * 1000


def test_due_work_is_claimed_atomically_and_future_work_remains(tmp_path):
    path, incoming = _config(tmp_path)
    first = incoming / "first.txt"
    second = incoming / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], clock=lambda: 10.0)
    service.schedule(job, first)
    service.schedule(job, second, delay=5.0)

    claimed = service._claim_due(10.0)

    assert [value[1] for _, value in claimed] == [first.resolve()]
    assert [value[1] for value in service.pending.values()] == [second.resolve()]


def test_schedule_between_claim_and_processing_is_not_lost(tmp_path):
    path, incoming = _config(tmp_path)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], clock=lambda: 10.0)
    service.schedule(job, source)
    claimed = service._claim_due(10.0)

    service.schedule(job, source, reset_settle=True)
    _, (claimed_job, claimed_path, _, attempts, _) = claimed[0]
    service._process(claimed_job, claimed_path, attempts)

    key = (job.job_id, str(source.resolve()))
    assert key in service.pending
    assert service.pending[key][2] > 10.0
    service.tick()
    assert source.exists()
    assert key in service.pending


def test_callback_cannot_shorten_retry_backoff_or_reset_attempts(tmp_path):
    path, incoming = _config(tmp_path)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], clock=lambda: 10.0)
    key = (job.job_id, str(source.resolve()))
    stat = source.stat()
    service.snapshots[key] = (stat.st_size, stat.st_mtime_ns)
    service.schedule(job, source)
    claimed = service._claim_due(10.0)

    def callback_then_fail(_, attempts=1, expected_source_identity=None):
        service.schedule(job, source, reset_settle=True)
        raise PermissionError("locked")

    service.movers[job.job_id].plan_and_move_operation = callback_then_fail

    _, (claimed_job, claimed_path, _, attempts, _) = claimed[0]
    service._process(claimed_job, claimed_path, attempts)

    assert service.pending[key][2] == 12.0
    assert service.pending[key][3] == 1
    assert service.pending[key][4] is True


@pytest.mark.parametrize("reset_settle", [False, True])
def test_replacement_after_retry_claim_preserves_attempt_count(tmp_path, reset_settle):
    path, incoming = _config(tmp_path)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], clock=lambda: 10.0)
    key = (job.job_id, str(source.resolve()))
    stat = source.stat()
    service.snapshots[key] = (stat.st_size, stat.st_mtime_ns)
    service.schedule(job, source, attempts=2)
    claimed = service._claim_due(10.0)
    service.schedule(job, source, reset_settle=reset_settle)

    _, (claimed_job, claimed_path, _, attempts, _) = claimed[0]
    service._process(claimed_job, claimed_path, attempts)

    assert service.pending[key][3] == 2


def test_concurrent_event_scheduling_is_synchronized(tmp_path):
    path, incoming = _config(tmp_path)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], clock=lambda: 10.0)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: service.schedule(job, source), range(100)))

    assert len(service.pending) == 1


def test_once_creates_missing_watch_folder_without_creating_destination(tmp_path):
    path, _ = _config(tmp_path, watch_path="missing/parents/inbox")
    incoming = tmp_path / "missing" / "parents" / "inbox"
    job = load_settings(str(path)).jobs[0]

    RenameWatchService([job], state_root=tmp_path / "state").run_once()

    assert incoming.is_dir()
    assert not job.destination_path.exists()


def test_watch_root_lock_blocks_other_instances_and_releases(tmp_path):
    watch_root = tmp_path / "incoming"
    watch_root.mkdir()
    first = WatchRootLock(watch_root)
    second = WatchRootLock(watch_root / ".")
    first.acquire()
    try:
        with pytest.raises(RenameWatchConfigError, match="locked or unavailable"):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()


def test_once_releases_watch_root_lock_after_failure(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    service = RenameWatchService([job], state_root=state_root)
    monkeypatch.setattr(service, "reconcile", lambda _: (_ for _ in ()).throw(OSError("scan failed")))

    with pytest.raises(OSError, match="scan failed"):
        service.run_once()

    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


def test_service_deduplicates_same_canonical_watch_root_lock(tmp_path):
    path, incoming = _config(tmp_path)
    first_job = load_settings(str(path)).jobs[0]
    second_job = replace(
        first_job,
        job_id="second",
        watch_path=incoming / ".",
        destination_path=incoming / "other-processed",
    )
    service = RenameWatchService(
        [first_job, second_job], state_root=tmp_path / "state"
    )
    service._prepare_watch_paths()

    service._acquire_root_locks()
    try:
        assert len(service.root_locks) == 1
    finally:
        service._release_root_locks()


def test_lock_namespace_does_not_depend_on_service_state_root(tmp_path):
    watch_root = tmp_path / "incoming"
    watch_root.mkdir()
    first = WatchRootLock(watch_root)
    second = WatchRootLock(watch_root)
    first.acquire()
    try:
        with pytest.raises(RenameWatchConfigError, match="locked or unavailable"):
            second.acquire()
    finally:
        first.release()


def test_lock_namespace_ignores_process_temp_environment(tmp_path):
    watch_root = tmp_path / "incoming"
    watch_root.mkdir()
    alternate_temp = tmp_path / "alternate-temp"
    alternate_temp.mkdir()
    script = (
        "import sys; from pathlib import Path; "
        "from indexly.rename_watch.locking import WatchRootLock; "
        "lock=WatchRootLock(Path(sys.argv[1])); lock.acquire(); "
        "print('ready', flush=True); sys.stdin.readline(); lock.release()"
    )
    environment = os.environ.copy()
    environment.update(
        {"TEMP": str(alternate_temp), "TMP": str(alternate_temp), "TMPDIR": str(alternate_temp)}
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(watch_root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(RenameWatchConfigError, match="locked or unavailable"):
            WatchRootLock(watch_root).acquire()
    finally:
        try:
            process.communicate("\n", timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=10)


def test_release_attempts_every_root_lock(tmp_path):
    service = RenameWatchService([], state_root=tmp_path / "state")
    released = []

    class FakeLock:
        def __init__(self, name, error=None):
            self.name = name
            self.error = error

        def release(self):
            released.append(self.name)
            if self.error:
                raise self.error

    service.root_locks = [
        FakeLock("first"),
        FakeLock("second", OSError("unlock failed")),
    ]

    with pytest.raises(OSError, match="unlock failed"):
        service._release_root_locks()

    assert released == ["second", "first"]
    assert service.root_locks == []


def test_observer_stop_failure_still_releases_root_lock(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, mode="event")
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], state_root=tmp_path / "state")
    service.stop_event.set()

    class BrokenObserver:
        def schedule(self, handler, watch_path, recursive=False):
            pass

        def start(self):
            pass

        def stop(self):
            raise OSError("stop failed")

        def is_alive(self):
            return False

    monkeypatch.setattr("indexly.rename_watch.service.Observer", BrokenObserver)

    with pytest.raises(OSError, match="stop failed"):
        service.run_forever()

    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


def test_non_oserror_during_partial_lock_acquisition_cleans_up(tmp_path, monkeypatch):
    watch_root = tmp_path / "incoming"
    watch_root.mkdir()
    lock = WatchRootLock(watch_root)
    assert len(lock.keys) == 2
    calls = []
    released = []

    def acquire_platform(key):
        calls.append(key)
        if len(calls) == 2:
            raise KeyboardInterrupt()
        return ("test", object())

    def release_handles():
        released.extend(lock._handles)
        lock._handles = []
        return None

    monkeypatch.setattr(lock, "_acquire_platform_lock", acquire_platform)
    monkeypatch.setattr(lock, "_release_handles", release_handles)

    with pytest.raises(KeyboardInterrupt):
        lock.acquire()

    assert len(released) == 1
    assert not set(lock.keys).intersection(locking_module._PROCESS_KEYS)


def test_symlink_candidates_are_ignored(tmp_path):
    path, incoming = _config(tmp_path)
    target = incoming / "target.txt"
    link = incoming / "link.txt"
    target.write_text("content", encoding="utf-8")
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip("file symlinks are unavailable: {0}".format(exc))
    job = load_settings(str(path)).jobs[0]

    assert not RenameWatchService([job])._eligible(job, link)


def test_runtime_rejects_watch_path_replaced_by_file(tmp_path):
    path, incoming = _config(tmp_path)
    incoming.rmdir()
    job = load_settings(str(path)).jobs[0]
    incoming.write_text("not a directory", encoding="utf-8")

    try:
        RenameWatchService([job]).run_once()
    except RenameWatchConfigError:
        pass
    else:
        raise AssertionError("a runtime watch path that is a file must be rejected")


def test_initialize_creates_safe_template(tmp_path):
    path = initialize_settings(str(tmp_path / "rename-watch.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["jobs"][0]["watch_path"] == "inbox"
    assert (tmp_path / "inbox").is_dir()
    try:
        initialize_settings(str(path))
    except RenameWatchConfigError:
        pass
    else:
        raise AssertionError("must not overwrite existing configuration")

def test_counter_format_is_required_only_when_counter_is_used(tmp_path):
    path, _ = _config(tmp_path, pattern="{date}-{title}", counter_format="")
    assert load_settings(str(path)).jobs[0].counter_format == ""
    path, _ = _config(tmp_path, pattern="{date}-{title}-{counter}", counter_format="03d")
    assert load_settings(str(path)).jobs[0].counter_format == "03d"
    path, _ = _config(tmp_path, pattern="{date}-{title}", counter_format="03d")
    try:
        load_settings(str(path))
    except RenameWatchConfigError:
        pass
    else:
        raise AssertionError("counter format without {counter} must be rejected")


def test_title_format_controls_rendering(tmp_path):
    path, incoming = _config(tmp_path, pattern="{title}", title_format="camel-case")
    source = incoming / "Monthly Report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    target = PlanMoveLog(job, tmp_path / "state").plan_and_move(source)
    assert target.name == "monthlyReport.txt"


def test_standard_title_format_reuses_existing_rename_naming(tmp_path):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}",
        counter_format="",
        title_format="standard",
    )
    source = incoming / "20240115-Monthly Report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]

    target = PlanMoveLog(job, tmp_path / "state").plan_and_move(source)

    assert target.name == "20240115-monthly-report.txt"


def test_pattern_without_counter_ignores_persisted_counter_state(tmp_path):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}",
        counter_format="",
        title_format="standard",
    )
    source = incoming / "20240115-report.txt"
    source.write_text("content", encoding="utf-8")
    state_root = tmp_path / "state"
    state_root.mkdir()
    state_path = state_root / "inbox.json"
    state_path.write_text(json.dumps({"20240115": 2}), encoding="utf-8")
    job = load_settings(str(path)).jobs[0]

    target = PlanMoveLog(job, state_root).plan_and_move(source)

    assert target.name == "20240115-report.txt"
    assert json.loads(state_path.read_text(encoding="utf-8")) == {"20240115": 2}


def test_collision_race_never_overwrites_existing_target(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("source", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    real_move = planner_module._move_without_overwrite
    collided = []

    def create_collision_then_move(
        source_path,
        target_path,
        on_destination_created=None,
        on_destination_finalized=None,
        expected_source_identity=None,
    ):
        if not collided:
            target_path.write_text("existing", encoding="utf-8")
            collided.append(target_path)
        return real_move(
            source_path,
            target_path,
            on_destination_created,
            on_destination_finalized,
            expected_source_identity,
        )

    monkeypatch.setattr(planner_module, "_move_without_overwrite", create_collision_then_move)

    target = PlanMoveLog(job, tmp_path / "state").plan_and_move(source)

    assert collided[0].read_text(encoding="utf-8") == "existing"
    assert target != collided[0]
    assert target.read_text(encoding="utf-8") == "source"


def test_copy_fallback_preserves_source_if_it_changes(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("original", encoding="utf-8")
    real_copy = planner_module.shutil.copyfileobj

    def reject_hard_link(source_path, target_path):
        raise OSError(errno.EXDEV, "different filesystem")

    def copy_then_change(source_handle, target_handle):
        real_copy(source_handle, target_handle)
        source.write_text("changed after copy", encoding="utf-8")

    monkeypatch.setattr(planner_module.os, "link", reject_hard_link)
    monkeypatch.setattr(planner_module.shutil, "copyfileobj", copy_then_change)

    try:
        planner_module._move_without_overwrite(source, target)
    except OSError as exc:
        assert "Source changed" in str(exc)
    else:
        raise AssertionError("a changing source must not be removed after fallback copying")

    assert source.read_text(encoding="utf-8") == "changed after copy"
    assert target.read_text(encoding="utf-8") == "original"


def test_copy_fallback_rejects_unreliable_destination_identity(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("content", encoding="utf-8")
    real_fstat = planner_module.os.fstat
    calls = []

    def reject_hard_link(source_path, target_path):
        raise OSError(errno.EXDEV, "different filesystem")

    def unreliable_target_fstat(descriptor):
        value = real_fstat(descriptor)
        calls.append(value)
        if len(calls) != 2:
            return value
        return SimpleNamespace(
            st_dev=value.st_dev,
            st_ino=0,
            st_size=value.st_size,
            st_mtime_ns=value.st_mtime_ns,
        )

    monkeypatch.setattr(planner_module.os, "link", reject_hard_link)
    monkeypatch.setattr(planner_module.os, "fstat", unreliable_target_fstat)

    with pytest.raises(OSError, match="identity is unavailable"):
        planner_module._move_without_overwrite(source, target)

    assert source.read_text(encoding="utf-8") == "content"
    assert target.exists()


@pytest.mark.parametrize("failing_phase", ["created", "finalized"])
def test_hard_link_callback_failure_preserves_both_paths(
    tmp_path, failing_phase
):
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("content", encoding="utf-8")

    def created(identity):
        if failing_phase == "created":
            raise OSError("journal unavailable")

    def finalized():
        if failing_phase == "finalized":
            raise OSError("journal unavailable")

    with pytest.raises(OSError, match="journal unavailable"):
        planner_module._move_without_overwrite(source, target, created, finalized)

    assert source.read_text(encoding="utf-8") == "content"
    assert target.read_text(encoding="utf-8") == "content"
    assert os.path.samestat(source.stat(), target.stat())


def test_source_unlink_failure_preserves_hard_link_destination(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("content", encoding="utf-8")
    real_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == source:
            raise PermissionError("source locked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError, match="source locked"):
        planner_module._move_without_overwrite(source, target)

    assert source.exists() and target.exists()
    assert os.path.samestat(source.stat(), target.stat())


def test_planner_rejects_nested_destination_symlink_swap_before_state_changes(
    tmp_path,
):
    path, incoming = _config(
        tmp_path,
        destination_subfolder="nested/processed",
        pattern="{date}-{title}-{counter}",
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    outside = tmp_path / "outside"
    outside.mkdir()
    (incoming / "nested").symlink_to(outside, target_is_directory=True)
    state_root = tmp_path / "state"

    with pytest.raises(RenameWatchConfigError, match="symlink or reparse point"):
        PlanMoveLog(job, state_root).plan_and_move_operation(source)

    assert source.read_text(encoding="utf-8") == "content"
    assert list(outside.iterdir()) == []
    assert not state_root.exists()


def test_once_revalidates_destination_after_readiness_before_planning(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        destination_subfolder="processed",
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    outside = tmp_path / "outside"
    outside.mkdir()
    state_root = tmp_path / "state"
    current = [0.0]

    def swap_during_settle(delay):
        current[0] += delay
        if not job.destination_path.exists():
            job.destination_path.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: pytest.fail("unsafe move was audited"),
    )
    service = RenameWatchService(
        [job],
        state_root=state_root,
        clock=lambda: current[0],
        sleeper=swap_during_settle,
    )

    with pytest.raises(RenameWatchConfigError, match="symlink or reparse point"):
        service.run_once()

    assert source.read_text(encoding="utf-8") == "content"
    assert list(outside.iterdir()) == []
    assert not state_root.exists()


def test_planner_final_guard_catches_destination_swap_before_target_creation(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}",
        counter_format="",
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    outside = tmp_path / "outside"
    outside.mkdir()
    held_destination = incoming / "held-processed"
    mover = PlanMoveLog(job, tmp_path / "state")
    real_guard = mover._guard_destination
    swapped = []

    def swap_after_journal_before_target(target=None, expected_destination_identity=None):
        if target is not None and mover.journal.pending() and not swapped:
            job.destination_path.rename(held_destination)
            job.destination_path.symlink_to(outside, target_is_directory=True)
            swapped.append(True)
        return real_guard(target, expected_destination_identity)

    monkeypatch.setattr(mover, "_guard_destination", swap_after_journal_before_target)

    with pytest.raises(RenameWatchConfigError, match="symlink or reparse point"):
        mover.plan_and_move_operation(source)

    assert swapped == [True]
    assert source.read_text(encoding="utf-8") == "content"
    assert list(outside.iterdir()) == []
    assert list(held_destination.iterdir()) == []
    assert mover.journal.pending()[0]["state"] == "prepared"


def test_recovery_guards_destination_before_counter_or_journal_mutation(tmp_path):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    job.destination_path.mkdir()
    target = job.destination_path / "target.txt"
    record = mover.journal.prepare(
        source,
        target,
        planner_module._identity_record(source.stat()),
        job.pattern,
        1,
        date_key="20240115",
        counter=0,
        counter_next=1,
    )
    journal_path = mover.journal._path(record["operation_id"])
    journal_before = journal_path.read_bytes()
    held_destination = incoming / "held-processed"
    job.destination_path.rename(held_destination)
    outside = tmp_path / "outside"
    outside.mkdir()
    job.destination_path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RenameWatchConfigError, match="symlink or reparse point"):
        mover.recover_pending()

    assert source.read_text(encoding="utf-8") == "content"
    assert list(outside.iterdir()) == []
    assert not mover.state.path.exists()
    assert journal_path.read_bytes() == journal_before


@pytest.mark.parametrize("transfer_kind", ["hard_link", "copy"])
def test_once_retries_only_finalized_source_unlink_and_completes(
    tmp_path, monkeypatch, transfer_kind
):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 3,
            "initial_delay_seconds": 1,
            "max_delay_seconds": 1,
        },
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    current = [0.0]
    state_root = tmp_path / "state"
    service = RenameWatchService(
        [job],
        state_root=state_root,
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    real_unlink = Path.unlink
    unlink_attempts = []
    audits = []
    failures = []

    if transfer_kind == "copy":
        monkeypatch.setattr(
            planner_module.os,
            "link",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                OSError(errno.EXDEV, "force copy fallback")
            ),
        )

    def fail_source_unlink_once(path_value, *args, **kwargs):
        if path_value == source:
            unlink_attempts.append(path_value)
            if len(unlink_attempts) == 1:
                raise PermissionError("source locked")
        return real_unlink(path_value, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source_unlink_once)
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: audits.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )

    service.run_once()

    assert len(unlink_attempts) == 2
    assert len(audits) == 1
    assert failures == []
    assert not source.exists()
    target = Path(audits[0][0][2])
    assert target.read_text(encoding="utf-8") == "content"
    assert service.movers[job.job_id].journal.pending() == []


@pytest.mark.parametrize("transfer_kind", ["hard_link", "copy"])
def test_once_persistent_finalized_unlink_failure_logs_once_and_keeps_evidence(
    tmp_path, monkeypatch, transfer_kind
):
    path, incoming = _config(
        tmp_path,
        settle_seconds=0.5,
        retry={
            "max_attempts": 2,
            "initial_delay_seconds": 1,
            "max_delay_seconds": 1,
        },
    )
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    other_root = tmp_path / "other-incoming"
    other_root.mkdir()
    other_source = other_root / "other.txt"
    other_source.write_text("other", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    other_job = replace(
        job,
        job_id="other",
        watch_path=other_root,
        destination_path=other_root / "processed",
    )
    current = [0.0]
    service = RenameWatchService(
        [job, other_job],
        state_root=tmp_path / "state",
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    real_unlink = Path.unlink
    failures = []
    audits = []

    if transfer_kind == "copy":
        monkeypatch.setattr(
            planner_module.os,
            "link",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                OSError(errno.EXDEV, "force copy fallback")
            ),
        )

    def keep_source_locked(path_value, *args, **kwargs):
        if path_value == source:
            raise PermissionError("source locked")
        return real_unlink(path_value, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", keep_source_locked)
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args: failures.append(args),
    )
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: audits.append((args, kwargs)),
    )

    service.run_once()

    assert len(failures) == 1
    assert len(audits) == 1
    assert isinstance(failures[0][5], PermissionError)
    assert source.read_text(encoding="utf-8") == "content"
    assert not other_source.exists()
    pending = service.movers[job.job_id].journal.pending()
    assert len(pending) == 1
    assert pending[0]["state"] == "destination_finalized"
    assert pending[0]["transfer_kind"] == transfer_kind
    destination = Path(pending[0]["destination_path"])
    assert destination.read_text(encoding="utf-8") == "content"
    if transfer_kind == "hard_link":
        assert os.path.samestat(source.stat(), destination.stat())
    else:
        assert not os.path.samestat(source.stat(), destination.stat())


def test_counter_uses_rendered_filename_date_across_restarts(tmp_path):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}-{counter}",
        counter_format="03d",
    )
    first = incoming / "20240115.txt"
    second = incoming / "20240115-second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    os.utime(first, (1700000000, 1700000000))
    os.utime(second, (1730000000, 1730000000))
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"

    first_target = PlanMoveLog(job, state_root).plan_and_move(first)
    second_target = PlanMoveLog(job, state_root).plan_and_move(second)

    assert first_target.name == "20240115-file-000.txt"
    assert second_target.name == "20240115-second-001.txt"


def test_observer_startup_creates_missing_path_and_cleans_up_on_failure(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path, mode="event")
    first_job = load_settings(str(path)).jobs[0]
    incoming.rmdir()
    second_path = tmp_path / "second"
    second_job = replace(
        first_job,
        job_id="second",
        watch_path=second_path,
        destination_path=second_path / "processed",
    )
    observers = []

    class FakeObserver:
        def __init__(self):
            self.started = False
            self.stopped = False
            observers.append(self)

        def schedule(self, handler, watch_path, recursive=False):
            assert Path(watch_path).is_dir()
            if len(observers) == 2:
                raise OSError("watch unavailable")

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def is_alive(self):
            return self.started and not self.stopped

        def join(self, timeout=None):
            self.started = False

    monkeypatch.setattr("indexly.rename_watch.service.Observer", FakeObserver)

    try:
        RenameWatchService(
            [first_job, second_job], state_root=tmp_path / "state"
        ).run_forever()
    except RenameWatchConfigError as exc:
        assert "second" in str(exc)
        assert str(second_path) in str(exc)
    else:
        raise AssertionError("observer startup failure must be reported")

    assert incoming.is_dir()
    assert second_path.is_dir()
    assert all(observer.stopped for observer in observers)


def _operator_args(config, **values):
    defaults = {
        "config": str(config),
        "init": False,
        "check_config": False,
        "once": False,
        "dry_run": False,
        "mode": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_rename_watch_parser_accepts_stage_two_operator_flags(tmp_path):
    parser = build_parser()
    config = tmp_path / "rename-watch.json"

    checked = parser.parse_args(
        ["rename-watch", "--config", str(config), "--check-config"]
    )
    previewed = parser.parse_args(
        ["rename-watch", "--config", str(config), "--once", "--dry-run"]
    )

    assert checked.check_config and not checked.once
    assert previewed.once and previewed.dry_run
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "rename-watch",
                "--config",
                str(config),
                "--init",
                "--check-config",
            ]
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"dry_run": True}, "--dry-run requires --once"),
        ({"init": True, "once": True}, "--init cannot be combined"),
        ({"check_config": True, "mode": "event"}, "--check-config cannot be combined"),
        ({"check_config": True, "once": True}, "--check-config cannot be combined"),
        ({"dry_run": True, "once": True, "mode": "event"}, "--dry-run cannot be combined"),
    ],
)
def test_operator_handler_rejects_incompatible_actions_before_loading_config(
    tmp_path, values, message
):
    with pytest.raises(ValueError, match=message):
        handle_rename_watch(_operator_args(tmp_path / "missing.json", **values))


def test_check_config_creates_only_watch_root_and_has_no_runtime_side_effects(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        watch_path="missing/parents/incoming",
        destination_subfolder="processed",
    )
    incoming.rmdir()
    state_root = tmp_path / "state"
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], state_root=state_root)
    monkeypatch.setattr(
        service,
        "_recover_pending_moves",
        lambda: pytest.fail("check-config attempted recovery"),
    )
    monkeypatch.setattr(
        service,
        "_start_observers",
        lambda: pytest.fail("check-config started observers"),
    )
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: pytest.fail("check-config wrote an audit"),
    )

    service.check_config()

    assert job.watch_path.is_dir()
    assert not job.destination_path.exists()
    assert not state_root.exists()
    assert service.root_locks == []


def test_check_config_strictly_reads_counter_and_journal_without_mutating_them(
    tmp_path
):
    path, _ = _config(tmp_path, pattern="{date}-{title}-{counter}")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    mover.state.path.parent.mkdir(parents=True)
    mover.state.path.write_text(json.dumps({"20240115": 4}), encoding="utf-8")
    source = job.watch_path / "report.txt"
    source.write_text("content", encoding="utf-8")
    job.destination_path.mkdir()
    record = mover.journal.prepare(
        source,
        job.destination_path / "planned.txt",
        planner_module._identity_record(source.stat()),
        job.pattern,
        1,
        date_key="20240115",
        counter=4,
        counter_next=5,
    )
    counter_before = mover.state.path.read_bytes()
    journal_path = mover.journal._path(record["operation_id"])
    journal_before = journal_path.read_bytes()

    RenameWatchService([job], state_root=state_root).check_config()

    assert mover.state.path.read_bytes() == counter_before
    assert journal_path.read_bytes() == journal_before
    assert source.exists()


@pytest.mark.parametrize("state_kind", ["counter", "journal"])
def test_check_config_surfaces_corrupt_state(tmp_path, state_kind):
    path, _ = _config(tmp_path, pattern="{date}-{title}-{counter}")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    if state_kind == "counter":
        mover.state.path.parent.mkdir(parents=True)
        mover.state.path.write_text("{", encoding="utf-8")
        match = "counter state is unreadable"
    else:
        mover.journal.directory.mkdir(parents=True)
        (mover.journal.directory / "broken.json").write_text("{", encoding="utf-8")
        match = "journal is unreadable"

    with pytest.raises(RenameWatchConfigError, match=match):
        RenameWatchService([job], state_root=state_root).check_config()

    lock = WatchRootLock(job.watch_path)
    lock.acquire()
    lock.release()


@pytest.mark.parametrize(
    "failure", ["mkdir-destination", "mkdir-state", "open", "replace"]
)
def test_check_config_runtime_probe_failures_clean_artifacts_and_release_lock(
    tmp_path, monkeypatch, failure
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    real_mkdir = Path.mkdir
    real_open = planner_module.os.open
    real_replace = planner_module.os.replace

    if failure.startswith("mkdir"):
        denied_directory = (
            job.destination_path
            if failure == "mkdir-destination"
            else state_root
        )

        def fail_probe_mkdir(path_value, *args, **kwargs):
            if path_value == denied_directory:
                raise PermissionError("injected mkdir failure")
            return real_mkdir(path_value, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fail_probe_mkdir)
    elif failure == "open":
        def fail_probe_open(path_value, *args, **kwargs):
            if ".indexly-rename-watch-check-" in os.fspath(path_value):
                raise PermissionError("injected open failure")
            return real_open(path_value, *args, **kwargs)

        monkeypatch.setattr(planner_module.os, "open", fail_probe_open)
    else:
        def fail_probe_replace(source_path, destination_path, *args, **kwargs):
            if ".indexly-rename-watch-check-" in os.fspath(destination_path):
                raise PermissionError("injected replace failure")
            return real_replace(source_path, destination_path, *args, **kwargs)

        monkeypatch.setattr(planner_module.os, "replace", fail_probe_replace)

    with pytest.raises(RenameWatchConfigError, match="runtime probe"):
        RenameWatchService([job], state_root=state_root).check_config()

    assert not job.destination_path.exists()
    assert not state_root.exists()
    assert sorted(path_value.name for path_value in incoming.iterdir()) == []
    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


def test_check_config_counter_update_open_failure_preserves_bytes_and_cleans(
    tmp_path, monkeypatch
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    state_root.mkdir()
    mover.state.path.write_text('{"20240115": 4}\n', encoding="utf-8")
    before = mover.state.path.read_bytes()
    real_open = planner_module.os.open

    def fail_counter_open(path_value, *args, **kwargs):
        if Path(path_value) == mover.state.path:
            raise PermissionError("injected counter open failure")
        return real_open(path_value, *args, **kwargs)

    monkeypatch.setattr(planner_module.os, "open", fail_counter_open)

    with pytest.raises(RenameWatchConfigError, match="counter update runtime probe"):
        RenameWatchService([job], state_root=state_root).check_config()

    assert mover.state.path.read_bytes() == before
    assert not job.destination_path.exists()
    assert sorted(path_value.name for path_value in state_root.iterdir()) == [
        mover.state.path.name
    ]
    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


def test_check_config_watch_root_probe_failure_with_existing_destination_cleans(
    tmp_path, monkeypatch
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    job = load_settings(str(path)).jobs[0]
    job.destination_path.mkdir()
    state_root = tmp_path / "state"
    real_open = planner_module.os.open

    def fail_watch_root_probe(path_value, *args, **kwargs):
        candidate = Path(path_value)
        if (
            candidate.parent == incoming
            and candidate.name.startswith(".indexly-rename-watch-check-")
        ):
            raise PermissionError("injected watch-root probe failure")
        return real_open(path_value, *args, **kwargs)

    monkeypatch.setattr(planner_module.os, "open", fail_watch_root_probe)

    with pytest.raises(RenameWatchConfigError, match="watch_path.*runtime probe"):
        RenameWatchService([job], state_root=state_root).check_config()

    assert job.destination_path.is_dir()
    assert list(job.destination_path.iterdir()) == []
    assert not state_root.exists()
    assert sorted(path_value.name for path_value in incoming.iterdir()) == [
        job.destination_path.name
    ]
    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


@pytest.mark.parametrize("counter_kind", ["symlink", "directory", "reparse"])
@pytest.mark.parametrize("operation", ["check", "dry-run"])
def test_strict_counter_state_rejects_links_reparse_and_non_regular_files(
    tmp_path, monkeypatch, counter_kind, operation
):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    (incoming / "report.txt").write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    state_root.mkdir()
    if counter_kind == "symlink":
        target = tmp_path / "counter-target.json"
        target.write_text("{}", encoding="utf-8")
        mover.state.path.symlink_to(target)
    elif counter_kind == "directory":
        mover.state.path.mkdir()
    else:
        mover.state.path.write_text("{}", encoding="utf-8")
        real_lstat = Path.lstat
        monkeypatch.setattr(
            planner_module.stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
            raising=False,
        )

        def reparse_lstat(path_value):
            if path_value == mover.state.path:
                return SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o600,
                    st_file_attributes=0x400,
                )
            return real_lstat(path_value)

        monkeypatch.setattr(Path, "lstat", reparse_lstat)

    service = RenameWatchService([job], state_root=state_root)
    with pytest.raises(RenameWatchConfigError, match="regular file"):
        service.check_config() if operation == "check" else service.dry_run_once()

    assert not job.destination_path.exists()
    lock = WatchRootLock(incoming)
    lock.acquire()
    lock.release()


@pytest.mark.parametrize("operation", ["check", "dry-run"])
def test_operator_commands_fail_nonblocking_when_watch_root_is_locked(
    tmp_path, operation
):
    path, incoming = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]
    held = WatchRootLock(incoming)
    held.acquire()
    service = RenameWatchService([job], state_root=tmp_path / "state")
    try:
        with pytest.raises(RenameWatchConfigError, match="locked or unavailable"):
            if operation == "check":
                service.check_config()
            else:
                service.dry_run_once()
    finally:
        held.release()
    assert service.root_locks == []


def test_dry_run_is_pure_and_uses_strict_snapshot_collisions_and_reservations(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}-{counter}",
        counter_format="03d",
    )
    second = incoming / "20240115-b.txt"
    first = incoming / "20240115-a.txt"
    second.write_text("second", encoding="utf-8")
    first.write_text("first", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    mover.state.path.parent.mkdir(parents=True)
    mover.state.path.write_text(json.dumps({"20240115": 2}), encoding="utf-8")
    counter_before = mover.state.path.read_bytes()
    monkeypatch.setattr(
        planner_module,
        "_move_without_overwrite",
        lambda *args, **kwargs: pytest.fail("dry-run attempted a move"),
    )
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda *args, **kwargs: pytest.fail("dry-run wrote a move audit"),
    )
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure",
        lambda *args, **kwargs: pytest.fail("dry-run wrote a failure audit"),
    )
    service = RenameWatchService([job], state_root=state_root)

    plans = service.dry_run_once()

    assert [plan.source for plan in plans] == [first.resolve(), second.resolve()]
    assert [plan.destination.name for plan in plans] == [
        "20240115-a-002.txt",
        "20240115-b-003.txt",
    ]
    assert first.read_text(encoding="utf-8") == "first"
    assert second.read_text(encoding="utf-8") == "second"
    assert not job.destination_path.exists()
    assert mover.state.path.read_bytes() == counter_before
    assert not mover.journal.directory.exists()


def test_dry_run_models_existing_counter_collision_without_consuming_state(tmp_path):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}-{counter}",
        counter_format="03d",
    )
    source = incoming / "20240115-report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    job.destination_path.mkdir()
    collision = job.destination_path / "20240115-report-000.txt"
    collision.write_text("existing", encoding="utf-8")
    state_root = tmp_path / "state"

    plans = RenameWatchService([job], state_root=state_root).dry_run_once()

    assert plans[0].destination.name == "20240115-report-001.txt"
    assert collision.read_text(encoding="utf-8") == "existing"
    assert not state_root.exists()


@pytest.mark.parametrize("collision_kind", ["existing", "reservation"])
def test_dry_run_rejects_no_counter_collisions(tmp_path, collision_kind):
    path, incoming = _config(
        tmp_path,
        pattern="{date}",
        counter_format="",
    )
    first = incoming / "20240115-a.txt"
    first.write_text("first", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    if collision_kind == "existing":
        job.destination_path.mkdir()
        (job.destination_path / "20240115.txt").write_text(
            "existing", encoding="utf-8"
        )
    else:
        (incoming / "20240115-b.txt").write_text("second", encoding="utf-8")

    with pytest.raises(RenameWatchConfigError, match="dry-run destination collision"):
        RenameWatchService([job], state_root=tmp_path / "state").dry_run_once()

    assert first.exists()


def test_filesystem_name_policy_detects_actual_volume_and_cleans_probes(tmp_path):
    path, incoming = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]

    policy = planner_module._filesystem_name_policy(job.destination_path)

    assert isinstance(policy.case_insensitive, bool)
    assert isinstance(policy.unicode_normalizing, bool)
    assert list(incoming.iterdir()) == []


@pytest.mark.parametrize("case_insensitive", [True, False])
def test_dry_run_case_equivalence_matches_destination_filesystem_policy(
    tmp_path, monkeypatch, case_insensitive
):
    path, incoming = _config(tmp_path, pattern="{date}", counter_format="")
    upper = incoming / "20240115-alpha.TXT"
    lower = incoming / "20240115-beta.txt"
    upper.write_text("upper", encoding="utf-8")
    lower.write_text("lower", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    monkeypatch.setattr(
        planner_module,
        "_filesystem_name_policy",
        lambda destination: planner_module.FilesystemNamePolicy(
            directory_key=str(destination),
            case_insensitive=case_insensitive,
            unicode_normalizing=False,
        ),
    )
    service = RenameWatchService([job], state_root=tmp_path / "state")

    if case_insensitive:
        with pytest.raises(
            RenameWatchConfigError, match="dry-run destination collision"
        ):
            service.dry_run_once()
    else:
        plans = service.dry_run_once()
        assert [plan.destination.name for plan in plans] == [
            "20240115.TXT",
            "20240115.txt",
        ]

    assert sorted(path_value.name for path_value in incoming.iterdir()) == [
        upper.name,
        lower.name,
    ]


@pytest.mark.parametrize("unicode_normalizing", [True, False])
def test_dry_run_unicode_equivalence_matches_destination_filesystem_policy(
    tmp_path, monkeypatch, unicode_normalizing
):
    path, incoming = _config(tmp_path, pattern="{date}", counter_format="")
    composed = incoming / "20240115-alpha.\u00e9"
    decomposed = incoming / "20240115-beta.e\u0301"
    composed.write_text("composed", encoding="utf-8")
    decomposed.write_text("decomposed", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    monkeypatch.setattr(
        planner_module,
        "_filesystem_name_policy",
        lambda destination: planner_module.FilesystemNamePolicy(
            directory_key=str(destination),
            case_insensitive=False,
            unicode_normalizing=unicode_normalizing,
        ),
    )
    service = RenameWatchService([job], state_root=tmp_path / "state")

    if unicode_normalizing:
        with pytest.raises(
            RenameWatchConfigError, match="dry-run destination collision"
        ):
            service.dry_run_once()
    else:
        plans = service.dry_run_once()
        assert len(plans) == 2

    assert composed.exists() and decomposed.exists()


def test_dry_run_fails_closed_on_counter_or_recovery_state(tmp_path):
    path, incoming = _config(tmp_path, pattern="{date}-{title}-{counter}")
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    mover = PlanMoveLog(job, state_root)
    mover.state.path.parent.mkdir(parents=True)
    mover.state.path.write_text(json.dumps({"date": True}), encoding="utf-8")

    with pytest.raises(RenameWatchConfigError, match="invalid entry"):
        RenameWatchService([job], state_root=state_root).dry_run_once()

    mover.state.path.write_text("{}", encoding="utf-8")
    job.destination_path.mkdir()
    record = mover.journal.prepare(
        source,
        job.destination_path / "planned.txt",
        planner_module._identity_record(source.stat()),
        job.pattern,
        1,
        date_key="date",
        counter=0,
        counter_next=1,
    )
    journal_path = mover.journal._path(record["operation_id"])
    journal_before = journal_path.read_bytes()

    with pytest.raises(RenameWatchConfigError, match="unfinished recovery operation"):
        RenameWatchService([job], state_root=state_root).dry_run_once()

    assert journal_path.read_bytes() == journal_before
    assert source.exists()


def test_dry_run_freezes_candidates_before_planning(tmp_path, monkeypatch):
    path, incoming = _config(tmp_path)
    initial = incoming / "initial.txt"
    initial.write_text("initial", encoding="utf-8")
    later = incoming / "later.txt"
    job = load_settings(str(path)).jobs[0]
    service = RenameWatchService([job], state_root=tmp_path / "state")
    mover = service.movers[job.job_id]
    real_preview = mover.preview

    def add_later_then_preview(sources, reservations):
        later.write_text("later", encoding="utf-8")
        return real_preview(sources, reservations)

    monkeypatch.setattr(mover, "preview", add_later_then_preview)

    plans = service.dry_run_once()

    assert [plan.source for plan in plans] == [initial.resolve()]
    assert later.exists()


def test_real_once_matches_dry_run_sorted_counter_mapping(tmp_path, monkeypatch):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}-{counter}",
        counter_format="03d",
        settle_seconds=0.5,
    )
    second = incoming / "20240115-b.txt"
    first = incoming / "20240115-a.txt"
    second.write_text("second", encoding="utf-8")
    first.write_text("first", encoding="utf-8")
    job = load_settings(str(path)).jobs[0]
    state_root = tmp_path / "state"
    preview = RenameWatchService([job], state_root=state_root).dry_run_once()
    current = [0.0]
    moved = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda job_id, source, destination, *args, **kwargs: moved.append(
            (Path(source), Path(destination))
        ),
    )

    RenameWatchService(
        [job],
        state_root=state_root,
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    ).run_once()

    assert moved == [
        (plan.source, plan.destination)
        for plan in preview
    ]


def test_dry_run_reserves_sources_across_same_root_jobs_like_real_once(
    tmp_path, monkeypatch
):
    path, incoming = _config(
        tmp_path,
        pattern="{date}-{title}-{counter}",
        counter_format="03d",
        settle_seconds=0.5,
    )
    source = incoming / "20240115-report.txt"
    source.write_text("content", encoding="utf-8")
    first_job = load_settings(str(path)).jobs[0]
    second_job = replace(
        first_job,
        job_id="second",
        destination_path=incoming / "second-processed",
    )
    state_root = tmp_path / "state"
    preview = RenameWatchService(
        [first_job, second_job], state_root=state_root
    ).dry_run_once()
    assert [plan.job_id for plan in preview] == [first_job.job_id]

    current = [0.0]
    moved = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move",
        lambda job_id, source_path, destination, *args, **kwargs: moved.append(
            (job_id, Path(source_path), Path(destination))
        ),
    )
    RenameWatchService(
        [first_job, second_job],
        state_root=state_root,
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    ).run_once()

    assert moved == [
        (preview[0].job_id, preview[0].source, preview[0].destination)
    ]


def test_handler_dispatches_check_and_dry_run_with_deterministic_output(
    tmp_path, monkeypatch, capsys
):
    path, incoming = _config(tmp_path)
    source = incoming / "report.txt"
    source.write_text("content", encoding="utf-8")
    calls = []

    class FakeService:
        def __init__(self, jobs):
            self.jobs = jobs

        def check_config(self):
            calls.append("check")

        def dry_run_once(self):
            calls.append("dry-run")
            return [
                SimpleNamespace(
                    job_id="inbox",
                    source=source.resolve(),
                    destination=(incoming / "processed" / "planned.txt").resolve(),
                )
            ]

    monkeypatch.setattr(service_module, "RenameWatchService", FakeService)

    handle_rename_watch(_operator_args(path, check_config=True))
    handle_rename_watch(_operator_args(path, once=True, dry_run=True))
    output = capsys.readouterr().out.splitlines()

    assert calls == ["check", "dry-run"]
    assert output[0].startswith("Rename-watch configuration is valid:")
    assert output[1] == "DRY-RUN job=inbox source={0} destination={1}".format(
        source.resolve(), (incoming / "processed" / "planned.txt").resolve()
    )
