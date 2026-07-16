import json
import errno
import os
import subprocess
import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from indexly.rename_watch.config import RenameWatchConfigError, initialize_settings, load_settings
from indexly.rename_watch import locking as locking_module
from indexly.rename_watch import identity as identity_module
from indexly.rename_watch import planner as planner_module
from indexly.rename_watch.locking import WatchRootLock
from indexly.rename_watch.planner import PlanMoveLog
from indexly.rename_watch.service import RenameWatchService


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

def crash(source_path, target_path, destination_created, destination_finalized):
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
        source_path, target_path, destination_created, destination_finalized
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
        source_path, target_path, destination_created, destination_finalized
    ):
        real_move(
            source_path,
            target_path,
            destination_created,
            destination_finalized,
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
        source_path, target_path, destination_created, destination_finalized
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
        source_path, target_path, destination_created, destination_finalized
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
        source_path, target_path, destination_created, destination_finalized
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

    def callback_then_fail(_, attempts=1):
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
    ):
        if not collided:
            target_path.write_text("existing", encoding="utf-8")
            collided.append(target_path)
        return real_move(
            source_path,
            target_path,
            on_destination_created,
            on_destination_finalized,
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
