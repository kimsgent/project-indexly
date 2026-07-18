import json
import errno
import os
from dataclasses import replace
from pathlib import Path

import pytest

import indexly.rename_watch.failure_store as failure_store_module
import indexly.rename_watch.planner as planner_module
from indexly.cli_utils import build_parser
from indexly.rename_watch.config import RenameWatchConfigError, load_settings
from indexly.rename_watch.failure_operator import retry_failures
from indexly.rename_watch.failure_store import FailureStore
from indexly.rename_watch.planner import PlanMoveLog
from indexly.rename_watch.service import RenameWatchService
from indexly.rename_watch.status import build_status


def _config(tmp_path: Path, **values):
    watch = tmp_path / "watch"
    watch.mkdir(exist_ok=True)
    job = {
        "id": "failures",
        "watch_path": "watch",
        "destination_subfolder": "processed",
        "pattern": "{title}",
        "counter_format": "",
        "settle_seconds": 0.01,
        "scan_interval_seconds": 10,
        "retry": {
            "max_attempts": 3,
            "initial_delay_seconds": 0.01,
            "max_delay_seconds": 0.01,
        },
    }
    job.update(values)
    path = tmp_path / "rename-watch.json"
    path.write_text(json.dumps({"version": 1, "jobs": [job]}), encoding="utf-8")
    return path, watch


def _job(tmp_path: Path, **values):
    config, watch = _config(tmp_path, **values)
    return config, load_settings(str(config)).jobs[0], watch


def _settled_process(service, job, source, attempts=0):
    resolved = source.resolve()
    value = source.stat()
    service.snapshots[(job.job_id, str(resolved))] = (value.st_size, value.st_mtime_ns)
    service._process(job, resolved, attempts)


def test_failure_config_defaults_and_strict_policy_validation(tmp_path):
    _path, job, _watch = _job(tmp_path)
    assert job.quarantine_path is None
    assert job.no_counter_collision_policy == "fail"

    path, _ = _config(tmp_path, no_counter_collision_policy="quarantine")
    with pytest.raises(RenameWatchConfigError, match="quarantine_subfolder"):
        load_settings(str(path))

    path, _ = _config(tmp_path, quarantine_subfolder="processed/failed")
    with pytest.raises(RenameWatchConfigError, match="disjoint"):
        load_settings(str(path))

    path, _ = _config(
        tmp_path,
        pattern="{title}-{counter}",
        counter_format="03d",
        no_counter_collision_policy="leave-source",
    )
    with pytest.raises(RenameWatchConfigError, match="only when pattern omits"):
        load_settings(str(path))


def test_quarantine_rejects_portable_case_alias_of_destination(tmp_path):
    path, _ = _config(tmp_path, quarantine_subfolder="PROCESSED")

    with pytest.raises(RenameWatchConfigError, match="disjoint"):
        load_settings(str(path))


def test_check_config_probes_and_restores_missing_quarantine(tmp_path):
    _path, job, _watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    service = RenameWatchService([job], state_root=tmp_path / "state")

    service.check_config()

    assert not job.quarantine_path.exists()


def test_check_config_rejects_quarantine_regular_file(tmp_path):
    _path, job, _watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    job.quarantine_path.write_text("occupied", encoding="utf-8")

    with pytest.raises(RenameWatchConfigError, match="real directories"):
        RenameWatchService([job], state_root=tmp_path / "state").check_config()


def test_leave_source_collision_is_immediate_durable_and_blocks_rescan(
    tmp_path, monkeypatch
):
    _path, job, watch = _job(
        tmp_path, no_counter_collision_policy="leave-source"
    )
    source = watch / "Report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    target = job.destination_path / "report.txt"
    target.write_text("existing", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state")
    logged = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure", lambda *args: logged.append(args)
    )

    _settled_process(service, job, source)

    records = service.failure_stores[job.job_id].records()
    assert source.read_text(encoding="utf-8") == "source"
    assert target.read_text(encoding="utf-8") == "existing"
    assert len(records) == 1
    assert records[0]["state"] == "active"
    assert records[0]["audited"] is True
    assert records[0]["attempted_destination_path"] == str(target)
    assert service._eligible(job, source) is False
    assert service.pending == {}
    assert len(logged) == 1


def test_quarantine_collision_writes_immutable_sidecar_and_is_hard_excluded(
    tmp_path, monkeypatch
):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    (job.destination_path / "report.txt").write_text("existing", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state")
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)

    _settled_process(service, job, source)

    record = service.failure_stores[job.job_id].records()[0]
    payload = Path(record["current_path"])
    sidecar = payload.parent.parent / "failure.json"
    assert not source.exists()
    assert payload.read_text(encoding="utf-8") == "source"
    assert json.loads(sidecar.read_text(encoding="ascii"))["failure_id"] == record["failure_id"]
    assert service._eligible(job, payload) is False
    before = sidecar.read_bytes()
    service.failure_stores[job.job_id].mark_audited(record)
    assert sidecar.read_bytes() == before


def test_quarantine_cross_filesystem_copy_is_pinned_and_finalized(
    tmp_path, monkeypatch
):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("copied content", encoding="utf-8")
    monkeypatch.setattr(
        failure_store_module.os,
        "link",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.EXDEV, "force copy fallback")
        ),
    )

    record = FailureStore(job, tmp_path / "state").record_terminal(
        source,
        job.destination_path / "report.txt",
        OSError(errno.EXDEV, "cross-device"),
        1,
        reason="processing_error",
        disposition="quarantine",
    )

    payload = Path(record["current_path"])
    assert not source.exists()
    assert payload.read_text(encoding="utf-8") == "copied content"
    assert record["state"] == "quarantined"
    assert record["transfer_kind"] == "copy"


def test_fail_policy_keeps_bounded_retry_behavior(tmp_path, monkeypatch):
    _path, job, watch = _job(tmp_path)
    source = watch / "report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    (job.destination_path / "report.txt").write_text("existing", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state", clock=lambda: 0.0)
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)

    _settled_process(service, job, source, attempts=0)

    pending = service.pending[(job.job_id, str(source.resolve()))]
    assert pending[3] == 1
    assert service.failure_stores[job.job_id].records() == []


def test_retry_failure_performs_normal_move_and_preserves_sidecar(
    tmp_path, monkeypatch
):
    config, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    target = job.destination_path / "report.txt"
    target.write_text("existing", encoding="utf-8")
    state = tmp_path / "state"
    service = RenameWatchService([job], state_root=state)
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)
    monkeypatch.setattr("indexly.rename_watch.failure_operator.log_move", lambda *args: None)
    _settled_process(service, job, source)
    record = service.failure_stores[job.job_id].records()[0]
    sidecar = Path(record["current_path"]).parent.parent / "failure.json"
    target.unlink()

    result = retry_failures(
        str(config),
        job_id=job.job_id,
        failure_id=record["failure_id"],
        yes=True,
        state_root=state,
    )

    assert result["retried"][0]["state"] == "moved"
    assert target.read_text(encoding="utf-8") == "source"
    assert FailureStore(job, state).records() == []
    assert sidecar.exists()


def test_retry_collision_preserves_failure_record_and_payload(tmp_path, monkeypatch):
    config, job, watch = _job(
        tmp_path, no_counter_collision_policy="leave-source"
    )
    source = watch / "report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    (job.destination_path / "report.txt").write_text("existing", encoding="utf-8")
    state = tmp_path / "state"
    service = RenameWatchService([job], state_root=state)
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)
    _settled_process(service, job, source)
    record = service.failure_stores[job.job_id].records()[0]

    with pytest.raises(FileExistsError):
        retry_failures(
            str(config),
            job_id=job.job_id,
            failure_id=record["failure_id"],
            yes=True,
            state_root=state,
        )

    assert source.exists()
    assert FailureStore(job, state).get(record["failure_id"])["state"] == "active"


def test_retry_parser_contract():
    args = build_parser().parse_args(
        [
            "rename-watch", "--config", "c.json", "--retry-failures",
            "--job", "alpha", "--failure-id", "3f7bbf87-842b-4a68-a3a8-1450d36f47f5",
            "--yes", "--json",
        ]
    )
    assert args.retry_failures is True
    assert args.failure_id == "3f7bbf87-842b-4a68-a3a8-1450d36f47f5"
    assert args.rename_watch_status_json is True


def test_dry_run_reports_nonmoving_collision_disposition(tmp_path):
    _path, job, watch = _job(
        tmp_path, no_counter_collision_policy="leave-source"
    )
    source = watch / "report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    (job.destination_path / "report.txt").write_text("existing", encoding="utf-8")

    plans = RenameWatchService([job], state_root=tmp_path / "state").dry_run_once()

    assert len(plans) == 1
    assert plans[0].disposition == "leave-source"
    assert source.exists()


def test_startup_replays_unaudited_failure_and_blocks_same_identity(
    tmp_path, monkeypatch
):
    _config_path, job, watch = _job(tmp_path)
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    state = tmp_path / "state"
    store = FailureStore(job, state)
    record = store.record_terminal(
        source,
        None,
        RuntimeError("line one\nline two\x00" + "x" * 2000),
        3,
        reason="processing_error",
        disposition="leave-source",
    )
    assert record["audited"] is False
    replayed = []
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_failure_record",
        lambda selected_job, selected_record: replayed.append(selected_record["failure_id"]),
    )
    service = RenameWatchService([job], state_root=state)

    service._recover_pending_moves()

    assert replayed == [record["failure_id"]]
    assert store.get(record["failure_id"])["audited"] is True
    assert service._eligible(job, source) is False
    assert "\n" not in record["error"]["message"]
    assert len(record["error"]["message"]) <= 1024


def test_status_exposes_retryable_failure_id_without_internal_identity(tmp_path):
    config, job, watch = _job(tmp_path)
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    state = tmp_path / "state"
    record = FailureStore(job, state).record_terminal(
        source,
        None,
        RuntimeError("failed"),
        2,
        reason="processing_error",
        disposition="leave-source",
    )

    output = build_status(str(config), state_root=state, log_root=tmp_path / "logs")
    failure = output["jobs"][0]["active_failures"][0]

    assert output["jobs"][0]["active_failure_count"] == 1
    assert failure["failure_id"] == record["failure_id"]
    assert "source_identity" not in failure


def test_linked_or_oversized_failure_record_fails_closed(tmp_path):
    _config_path, job, watch = _job(tmp_path)
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    state = tmp_path / "state"
    store = FailureStore(job, state)
    record = store.record_terminal(
        source, None, RuntimeError("failed"), 1,
        reason="processing_error", disposition="leave-source",
    )
    path = store._path(record["failure_id"])
    path.unlink()
    target = tmp_path / "outside.json"
    target.write_text("{}", encoding="utf-8")
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks unavailable")

    with pytest.raises(RenameWatchConfigError, match="without links"):
        store.records()


def test_runtime_quarantine_symlink_swap_is_rejected_without_outside_write(
    tmp_path, monkeypatch
):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    job.quarantine_path.symlink_to(outside, target_is_directory=True)
    source = watch / "report.txt"
    source.write_text("source", encoding="utf-8")
    job.destination_path.mkdir()
    (job.destination_path / "report.txt").write_text("existing", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state")
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)

    with pytest.raises(RenameWatchConfigError, match="real director"):
        _settled_process(service, job, source)

    assert source.exists()
    assert list(outside.iterdir()) == []


def test_all_jobs_protect_shared_root_quarantine(tmp_path):
    _path, first, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
        recursive=True,
    )
    second = replace(
        first,
        job_id="second",
        destination_path=watch / "second-processed",
        quarantine_path=None,
        no_counter_collision_policy="fail",
    )
    payload = first.quarantine_path / "namespace" / "failure" / "payload.txt"
    payload.parent.mkdir(parents=True)
    payload.write_text("content", encoding="utf-8")
    service = RenameWatchService([first, second], state_root=tmp_path / "state")

    assert service._eligible(second, payload) is False
    assert payload.resolve() not in service._discover_candidates(second)


def test_sidecar_writer_handles_partial_os_write(tmp_path, monkeypatch):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    store = FailureStore(job, tmp_path / "state")
    real_write = os.write

    def partial(descriptor, payload):
        return real_write(descriptor, payload[: max(1, len(payload) // 3)])

    monkeypatch.setattr("indexly.rename_watch.failure_store.os.write", partial)
    record = store.record_terminal(
        source,
        job.destination_path / "report.txt",
        FileExistsError("collision"),
        1,
        reason="no_counter_collision",
        disposition="quarantine",
    )

    sidecar = Path(record["current_path"]).parent.parent / "failure.json"
    assert json.loads(sidecar.read_text(encoding="ascii"))["failure_id"] == record["failure_id"]


def test_quarantine_preserves_reserved_sidecar_basename(tmp_path):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "failure.json"
    source.write_text("not metadata", encoding="utf-8")
    store = FailureStore(job, tmp_path / "state")

    record = store.record_terminal(
        source,
        job.destination_path / "failure.json",
        FileExistsError("collision"),
        1,
        reason="no_counter_collision",
        disposition="quarantine",
    )

    payload = Path(record["current_path"])
    sidecar = payload.parent.parent / "failure.json"
    assert payload.name == "failure.json"
    assert payload.read_text(encoding="utf-8") == "not metadata"
    assert json.loads(sidecar.read_text(encoding="ascii"))["failure_id"] == record["failure_id"]


def test_recovery_recreates_missing_sidecar_without_mutating_payload(tmp_path):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    store = FailureStore(job, tmp_path / "state")
    record = store.record_terminal(
        source,
        job.destination_path / "report.txt",
        FileExistsError("collision"),
        1,
        reason="no_counter_collision",
        disposition="quarantine",
    )
    payload = Path(record["current_path"])
    sidecar = payload.parent.parent / "failure.json"
    sidecar.unlink()
    before = payload.read_bytes()

    store.recover()

    assert payload.read_bytes() == before
    assert json.loads(sidecar.read_text(encoding="ascii"))["failure_id"] == record["failure_id"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-descriptor race test")
def test_quarantine_parent_substitution_preserves_source(tmp_path, monkeypatch):
    _path, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    real_move = failure_store_module._move_without_overwrite_at

    def substitute_parent(
        source_path, target_name, directory_descriptor, *args, **kwargs
    ):
        parked = watch / "parked-quarantine"
        job.quarantine_path.rename(parked)
        try:
            job.quarantine_path.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks unavailable")
        return real_move(
            source_path,
            target_name,
            directory_descriptor,
            *args,
            **kwargs,
        )

    store = FailureStore(job, tmp_path / "state")
    monkeypatch.setattr(
        failure_store_module, "_move_without_overwrite_at", substitute_parent
    )

    with pytest.raises(RenameWatchConfigError, match="real directories"):
        store.record_terminal(
            source,
            job.destination_path / "report.txt",
            FileExistsError("collision"),
            1,
            reason="no_counter_collision",
            disposition="quarantine",
        )

    assert source.read_text(encoding="utf-8") == "content"
    assert list(outside.iterdir()) == []


def test_retry_log_failure_is_recovered_before_payload_validation(
    tmp_path, monkeypatch
):
    config, job, watch = _job(
        tmp_path,
        quarantine_subfolder="quarantine",
        no_counter_collision_policy="quarantine",
    )
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    job.destination_path.mkdir()
    target = job.destination_path / "report.txt"
    target.write_text("existing", encoding="utf-8")
    state = tmp_path / "state"
    service = RenameWatchService([job], state_root=state)
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)
    _settled_process(service, job, source)
    record = service.failure_stores[job.job_id].records()[0]
    payload = Path(record["current_path"])
    target.unlink()
    monkeypatch.setattr(
        "indexly.rename_watch.failure_operator.log_move",
        lambda *args: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        retry_failures(
            str(config),
            job_id=job.job_id,
            failure_id=record["failure_id"],
            yes=True,
            state_root=state,
        )

    assert not payload.exists()
    assert target.read_text(encoding="utf-8") == "content"
    assert FailureStore(job, state).get(record["failure_id"])["state"] == "retry_moved"
    assert len(service.movers[job.job_id].journal.pending()) == 1
    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move", lambda *args, **kwargs: None
    )

    recovered = RenameWatchService([job], state_root=state)
    recovered._recover_pending_moves()

    assert FailureStore(job, state).records() == []
    assert recovered.movers[job.job_id].journal.pending() == []


def test_retry_cleanup_crash_is_idempotent_by_failure_id(tmp_path, monkeypatch):
    config, job, watch = _job(tmp_path, no_counter_collision_policy="leave-source")
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    job.destination_path.mkdir()
    target = job.destination_path / "report.txt"
    target.write_text("existing", encoding="utf-8")
    state = tmp_path / "state"
    service = RenameWatchService([job], state_root=state)
    monkeypatch.setattr("indexly.rename_watch.service.log_failure", lambda *args: None)
    _settled_process(service, job, source)
    record = service.failure_stores[job.job_id].records()[0]
    target.unlink()
    monkeypatch.setattr("indexly.rename_watch.failure_operator.log_move", lambda *args: None)
    real_resolve = FailureStore.resolve
    monkeypatch.setattr(
        FailureStore,
        "resolve",
        lambda *args: (_ for _ in ()).throw(RuntimeError("cleanup interrupted")),
    )

    with pytest.raises(RuntimeError, match="cleanup interrupted"):
        retry_failures(
            str(config),
            job_id=job.job_id,
            failure_id=record["failure_id"],
            yes=True,
            state_root=state,
        )

    assert target.read_text(encoding="utf-8") == "content"
    assert PlanMoveLog(job, state).journal.pending() == []
    assert FailureStore(job, state).get(record["failure_id"])["state"] == "retry_moved"
    monkeypatch.setattr(FailureStore, "resolve", real_resolve)

    result = retry_failures(
        str(config),
        job_id=job.job_id,
        failure_id=record["failure_id"],
        yes=True,
        state_root=state,
    )

    assert [item["failure_id"] for item in result["retried"]] == [record["failure_id"]]
    assert FailureStore(job, state).records() == []


def test_bulk_retry_is_deterministic_fail_fast_and_partially_committed(
    tmp_path, monkeypatch
):
    config, job, watch = _job(tmp_path, no_counter_collision_policy="leave-source")
    state = tmp_path / "state"
    store = FailureStore(job, state)
    for name in ("alpha.txt", "beta.txt"):
        source = watch / name
        source.write_text(name, encoding="utf-8")
        store.record_terminal(
            source,
            None,
            PermissionError("locked"),
            3,
            reason="processing_error",
            disposition="leave-source",
        )
    ordered = store.records()
    first, second = ordered
    job.destination_path.mkdir()
    blocked_target = job.destination_path / Path(second["current_path"]).name
    blocked_target.write_text("existing", encoding="utf-8")
    monkeypatch.setattr("indexly.rename_watch.failure_operator.log_move", lambda *args: None)

    with pytest.raises(FileExistsError):
        retry_failures(
            str(config),
            job_id=job.job_id,
            all_failures=True,
            yes=True,
            state_root=state,
        )

    remaining = store.records()
    assert [record["failure_id"] for record in remaining] == [second["failure_id"]]
    first_target = job.destination_path / Path(first["current_path"]).name
    assert first_target.read_text(encoding="utf-8") == Path(first["current_path"]).name
    assert blocked_target.read_text(encoding="utf-8") == "existing"


def test_retry_counter_job_uses_fresh_normal_counter_allocation(tmp_path, monkeypatch):
    config, job, watch = _job(
        tmp_path,
        pattern="{title}-{counter}",
        counter_format="02d",
    )
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    state = tmp_path / "state"
    store = FailureStore(job, state)
    record = store.record_terminal(
        source, None, PermissionError("locked"), 3,
        reason="processing_error", disposition="leave-source",
    )
    monkeypatch.setattr("indexly.rename_watch.failure_operator.log_move", lambda *args: None)

    retry_failures(
        str(config), job_id=job.job_id, failure_id=record["failure_id"],
        yes=True, state_root=state,
    )

    targets = list(job.destination_path.iterdir())
    assert len(targets) == 1
    assert targets[0].name.endswith("-00.txt")
    assert store.records() == []


def test_retry_recovery_pending_reports_original_exact_move(tmp_path, monkeypatch):
    config, job, watch = _job(tmp_path)
    source = watch / "report.txt"
    source.write_text("content", encoding="utf-8")
    source_identity = source.stat()
    state = tmp_path / "state"
    mover = PlanMoveLog(job, state)
    real_unlink = Path.unlink

    def keep_source(path_value, *args, **kwargs):
        if path_value == source:
            raise PermissionError("source locked")
        return real_unlink(path_value, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", keep_source)
    with pytest.raises(PermissionError, match="source locked"):
        mover.plan_and_move_operation(
            source,
            1,
            (source_identity.st_dev, source_identity.st_ino),
        )
    pending = mover.journal.pending()[0]
    store = FailureStore(job, state)
    record = store.record_terminal(
        source,
        Path(pending["destination_path"]),
        PermissionError("source locked"),
        2,
        reason="recovery_pending",
        disposition="leave-source",
    )
    monkeypatch.setattr(Path, "unlink", real_unlink)
    monkeypatch.setattr("indexly.rename_watch.failure_operator.log_move", lambda *args: None)

    result = retry_failures(
        str(config),
        job_id=job.job_id,
        failure_id=record["failure_id"],
        yes=True,
        state_root=state,
    )

    assert [item["failure_id"] for item in result["retried"]] == [record["failure_id"]]
    assert not source.exists()
    assert Path(pending["destination_path"]).read_text(encoding="utf-8") == "content"
    assert mover.journal.pending() == []
    assert store.records() == []
