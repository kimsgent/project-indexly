import json
import os
import stat
from types import SimpleNamespace
from pathlib import Path

import pytest

import indexly.rename_watch.failure_store as failure_store_module
import indexly.rename_watch.recovery_operator as recovery_operator
from indexly.cli_utils import build_parser
from indexly.rename_watch import handle_rename_watch
from indexly.rename_watch.config import RenameWatchConfigError, load_settings
from indexly.rename_watch.error_contract import RenameWatchUsageError
from indexly.rename_watch.failure_store import FailureStore
from indexly.rename_watch.journal import atomic_write_json
from indexly.rename_watch.planner import PlanMoveLog
from indexly.rename_watch.recovery_operator import resolve_recovery
from indexly.rename_watch.service import RenameWatchService


def _job(tmp_path: Path):
    watch = tmp_path / "watch"
    watch.mkdir()
    config = tmp_path / "rename-watch.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "id": "inbox",
                        "watch_path": "watch",
                        "destination_subfolder": "processed",
                        "pattern": "{title}",
                        "counter_format": "",
                        "settle_seconds": 0.01,
                        "scan_interval_seconds": 10,
                        "retry": {
                            "max_attempts": 4,
                            "initial_delay_seconds": 0.01,
                            "max_delay_seconds": 0.01,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return config, load_settings(str(config)).jobs[0], watch


def _conflict(tmp_path: Path, monkeypatch):
    config, job, watch = _job(tmp_path)
    state = tmp_path / "state"
    source = watch / "report.txt"
    source.write_text("payload", encoding="utf-8")
    identity = source.stat()
    mover = PlanMoveLog(job, state)
    real_unlink = Path.unlink

    def fail_source_unlink(path, *args, **kwargs):
        if path == source:
            raise PermissionError("simulated Windows sharing violation")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source_unlink)
    with pytest.raises(PermissionError, match="sharing violation"):
        mover.plan_and_move_operation(
            source, expected_source_identity=(identity.st_dev, identity.st_ino)
        )
    journal = mover.journal.pending()[0]
    assert journal["state"] == "destination_finalized"
    assert journal["transfer_kind"] == "hard_link"
    failure = FailureStore(job, state).record_terminal(
        source,
        Path(journal["destination_path"]),
        PermissionError("simulated Windows sharing violation"),
        2,
        reason="recovery_pending",
        disposition="leave-source",
    )
    monkeypatch.setattr(Path, "unlink", real_unlink)
    return config, job, watch, state, mover, journal, failure


def test_externally_handled_resolution_preserves_renamed_payload_and_unblocks_run(
    tmp_path, monkeypatch
):
    config, job, watch, state, mover, journal, failure = _conflict(
        tmp_path, monkeypatch
    )
    destination = Path(journal["destination_path"])
    destination.unlink()
    renamed = source = Path(journal["source_path"])
    renamed = source.with_name("renamed.txt")
    source.rename(renamed)

    result = resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        yes=True,
        state_root=state,
    )

    receipt = Path(result["receipt_path"])
    evidence = json.loads(receipt.read_text(encoding="utf-8"))
    assert evidence["disposition"] == "externally_handled"
    assert evidence["journal_evidence"] == journal
    assert evidence["failure_evidence"] == failure
    assert evidence["result"]["filesystem_payload_mutations"] == 0
    assert renamed.read_text(encoding="utf-8") == "payload"
    assert mover.journal.pending() == []
    assert FailureStore(job, state).records() == []

    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move", lambda *args, **kwargs: None
    )
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=state,
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    service.run_once()
    assert not renamed.exists(), FailureStore(job, state).records()
    assert (job.destination_path / "renamed.txt").read_text(
        encoding="utf-8"
    ) == "payload"


@pytest.mark.skipif(
    os.name != "nt",
    reason="requires Windows delete-sharing semantics",
)
def test_windows_open_handle_conflict_is_resolved_without_payload_mutation(
    tmp_path, monkeypatch
):
    config, job, watch = _job(tmp_path)
    state = tmp_path / "state"
    source = watch / "word-save-as.docx"
    source.write_bytes(b"simulated Word payload")
    identity = source.stat()
    mover = PlanMoveLog(job, state)

    with source.open("rb"):
        with pytest.raises(PermissionError):
            mover.plan_and_move_operation(
                source,
                expected_source_identity=(identity.st_dev, identity.st_ino),
            )
        journal = mover.journal.pending()[0]
        destination = Path(journal["destination_path"])
        assert source.exists()
        assert destination.exists()
        assert os.path.samefile(source, destination)

    destination.unlink()
    renamed = source.with_name("word-save-as-renamed.docx")
    source.rename(renamed)
    before = renamed.read_bytes()

    result = resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        yes=True,
        state_root=state,
    )

    assert result["filesystem_payload_mutations"] == 0
    assert renamed.read_bytes() == before
    assert mover.journal.pending() == []

    monkeypatch.setattr(
        "indexly.rename_watch.service.log_move", lambda *args, **kwargs: None
    )
    current = [0.0]
    service = RenameWatchService(
        [job],
        state_root=state,
        clock=lambda: current[0],
        sleeper=lambda delay: current.__setitem__(0, current[0] + delay),
    )
    service.run_once()
    assert not renamed.exists()
    assert (job.destination_path / "word-save-as-renamed.docx").read_bytes() == before


@pytest.mark.parametrize("existing", ["source", "destination"])
def test_resolution_refuses_when_recorded_path_exists(tmp_path, monkeypatch, existing):
    config, job, _watch, state, _mover, journal, _failure = _conflict(
        tmp_path, monkeypatch
    )
    source = Path(journal["source_path"])
    destination = Path(journal["destination_path"])
    if existing == "source":
        destination.unlink()
    else:
        source.unlink()

    with pytest.raises(RenameWatchConfigError, match="still exists"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("state", "destination_created", "finalized hard-link"),
        ("transfer_kind", "copy", "finalized hard-link"),
    ],
)
def test_resolution_refuses_wrong_journal_kind(
    tmp_path, monkeypatch, field, value, message
):
    config, job, _watch, state, mover, journal, _failure = _conflict(
        tmp_path, monkeypatch
    )
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()
    raw = dict(journal, **{field: value})
    if field == "state":
        raw["destination_fingerprint"] = None
    atomic_write_json(mover.journal._path(journal["operation_id"]), raw)

    with pytest.raises(RenameWatchConfigError, match=message):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )


def test_resolution_refuses_ambiguous_matching_failures(tmp_path, monkeypatch):
    config, job, _watch, state, _mover, journal, _failure = _conflict(
        tmp_path, monkeypatch
    )
    store = FailureStore(job, state)
    store.record_terminal(
        Path(journal["source_path"]),
        Path(journal["destination_path"]),
        PermissionError("again"),
        2,
        reason="recovery_pending",
        disposition="leave-source",
    )
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()

    with pytest.raises(RenameWatchConfigError, match="ambiguous"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )


def test_resolution_does_not_select_stale_same_path_failure(tmp_path, monkeypatch):
    config, job, _watch, state, _mover, journal, failure = _conflict(
        tmp_path, monkeypatch
    )
    stale = dict(failure)
    stale_identity = dict(
        stale["source_identity"], inode=stale["source_identity"]["inode"] + 1
    )
    stale["source_identity"] = stale_identity
    stale["current_identity"] = stale_identity
    store = FailureStore(job, state)
    atomic_write_json(store._path(stale["failure_id"]), stale)
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()

    result = resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        yes=True,
        state_root=state,
    )

    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["failure_evidence"] is None
    assert store.records() == [stale]


class _TTY:
    def isatty(self):
        return True


def test_resolution_confirmation_and_machine_output_validation(tmp_path, monkeypatch):
    config, job, _watch, state, _mover, journal, _failure = _conflict(
        tmp_path, monkeypatch
    )
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()
    with pytest.raises(RenameWatchConfigError, match="confirmation did not match"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            input_func=lambda prompt: "RESOLVE wrong",
            stdin=_TTY(),
            state_root=state,
        )
    with pytest.raises(RenameWatchUsageError, match="machine-readable"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            json_output=True,
            state_root=state,
        )
    answer = "RESOLVE " + journal["operation_id"]
    result = resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        input_func=lambda prompt: answer,
        stdin=_TTY(),
        state_root=state,
    )
    assert result["disposition"] == "externally_handled"


def test_resolution_rerun_finishes_cleanup_after_receipt_write(tmp_path, monkeypatch):
    config, job, _watch, state, mover, journal, failure = _conflict(
        tmp_path, monkeypatch
    )
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()
    real_retire = PlanMoveLog._retire_externally_handled_locked

    def crash_after_receipt(self, evidence):
        raise RuntimeError("injected crash")

    monkeypatch.setattr(
        PlanMoveLog, "_retire_externally_handled_locked", crash_after_receipt
    )
    with pytest.raises(RuntimeError, match="injected crash"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )
    receipts = list((state / "recovery-resolutions").rglob("*.json"))
    assert len(receipts) == 1
    assert mover.journal.pending() == [journal]
    assert FailureStore(job, state).records() == [failure]

    monkeypatch.setattr(PlanMoveLog, "_retire_externally_handled_locked", real_retire)
    first_bytes = receipts[0].read_bytes()
    resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        yes=True,
        state_root=state,
    )
    assert receipts[0].read_bytes() == first_bytes
    assert mover.journal.pending() == []
    assert FailureStore(job, state).records() == []
    resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        yes=True,
        state_root=state,
    )
    assert receipts[0].read_bytes() == first_bytes


def test_receipt_embedded_failure_must_match_journal_without_live_record(
    tmp_path, monkeypatch
):
    config, job, _watch, state, _mover, journal, failure = _conflict(
        tmp_path, monkeypatch
    )
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()

    def crash_after_receipt(self, evidence):
        raise RuntimeError("injected crash")

    monkeypatch.setattr(
        PlanMoveLog, "_retire_externally_handled_locked", crash_after_receipt
    )
    with pytest.raises(RuntimeError, match="injected crash"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )
    receipt_path = next((state / "recovery-resolutions").rglob("*.json"))
    FailureStore(job, state).resolve(failure)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    forged = dict(receipt["failure_evidence"])
    forged_identity = dict(
        forged["source_identity"], inode=forged["source_identity"]["inode"] + 1
    )
    forged["source_identity"] = forged_identity
    forged["current_identity"] = forged_identity
    receipt["failure_evidence"] = forged
    receipt_path.chmod(stat.S_IWRITE | stat.S_IREAD)
    atomic_write_json(receipt_path, receipt)

    with pytest.raises(RenameWatchConfigError, match="failure evidence is invalid"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )


def test_receipt_publication_does_not_clobber_race_winner(tmp_path, monkeypatch):
    config, job, _watch, state, _mover, journal, _failure = _conflict(
        tmp_path, monkeypatch
    )
    Path(journal["destination_path"]).unlink()
    Path(journal["source_path"]).unlink()
    real_link = recovery_operator.os.link
    published = []

    def publish_winner(source, destination):
        winner = json.loads(Path(source).read_text(encoding="utf-8"))
        winner["resolved_at"] = "race-winner"
        atomic_write_json(Path(destination), winner)
        published.append(Path(destination).read_bytes())
        raise FileExistsError("injected competing publisher")

    monkeypatch.setattr(recovery_operator.os, "link", publish_winner)
    result = resolve_recovery(
        str(config),
        job_id=job.job_id,
        operation_id=journal["operation_id"],
        yes=True,
        state_root=state,
    )
    monkeypatch.setattr(recovery_operator.os, "link", real_link)

    receipt_path = Path(result["receipt_path"])
    assert (
        json.loads(receipt_path.read_text(encoding="utf-8"))["resolved_at"]
        == "race-winner"
    )
    assert receipt_path.read_bytes() == published[0]


def test_resolution_rechecks_paths_immediately_before_publication(
    tmp_path, monkeypatch
):
    config, job, _watch, state, _mover, journal, _failure = _conflict(
        tmp_path, monkeypatch
    )
    source = Path(journal["source_path"])
    Path(journal["destination_path"]).unlink()
    source.unlink()
    real_mkstemp = recovery_operator.tempfile.mkstemp

    def recreate_source(*args, **kwargs):
        result = real_mkstemp(*args, **kwargs)
        source.write_text("late external payload", encoding="utf-8")
        return result

    monkeypatch.setattr(recovery_operator.tempfile, "mkstemp", recreate_source)
    with pytest.raises(RenameWatchConfigError, match="recorded source still exists"):
        resolve_recovery(
            str(config),
            job_id=job.job_id,
            operation_id=journal["operation_id"],
            yes=True,
            state_root=state,
        )
    assert not list((state / "recovery-resolutions").rglob("*.json"))


def test_parser_and_handler_require_exact_resolution_scope(tmp_path):
    parser = build_parser()
    args = parser.parse_args(
        [
            "rename-watch",
            "--config",
            str(tmp_path / "c.json"),
            "--resolve-recovery",
            "--job",
            "inbox",
            "--operation-id",
            "00000000-0000-0000-0000-000000000001",
            "--yes",
            "--json",
        ]
    )
    assert args.resolve_recovery
    with pytest.raises(RenameWatchUsageError, match="--job is required"):
        handle_rename_watch(
            type(
                "Args",
                (),
                {
                    **vars(args),
                    "job": None,
                    "rename_watch_status_json": False,
                },
            )()
        )


@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_receipt_read_rejects_links_and_reparse_points(tmp_path, monkeypatch, kind):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    real_lstat = Path.lstat

    def marked_lstat(path):
        value = real_lstat(path)
        if path != receipt:
            return value
        mode = stat.S_IFLNK if kind == "symlink" else value.st_mode
        attributes = recovery_operator._REPARSE or 0x400 if kind == "reparse" else 0
        return SimpleNamespace(
            st_mode=mode,
            st_file_attributes=attributes,
            st_size=value.st_size,
            st_dev=value.st_dev,
            st_ino=value.st_ino,
            st_mtime_ns=value.st_mtime_ns,
        )

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    monkeypatch.setattr(recovery_operator, "_REPARSE", 0x400)

    with pytest.raises(RenameWatchConfigError, match="not a regular file"):
        recovery_operator._read_receipt(receipt, tmp_path)


def test_receipt_read_rejects_reparse_ancestor(tmp_path, monkeypatch):
    state = tmp_path / "state"
    ancestor = state / "recovery-resolutions"
    directory = ancestor / "namespace"
    directory.mkdir(parents=True)
    receipt = directory / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    real_lstat = Path.lstat

    def marked_lstat(path):
        value = real_lstat(path)
        if path != ancestor:
            return value
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_file_attributes=0x400,
            st_dev=value.st_dev,
            st_ino=value.st_ino,
        )

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    monkeypatch.setattr(failure_store_module, "_REPARSE", 0x400)

    with pytest.raises(RenameWatchConfigError, match="only real directories"):
        recovery_operator._read_receipt(receipt, state)
