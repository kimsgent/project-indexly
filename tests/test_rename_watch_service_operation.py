import json
import plistlib
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexly.log_utils import LogManager
from indexly.rename_watch import logging as rename_logging
from indexly.rename_watch.config import (
    RenameWatchConfigError,
    RenameWatchServiceSettings,
    load_settings,
)
from indexly.rename_watch.error_contract import run_with_error_contract
from indexly.rename_watch.runtime_snapshot import (
    METRIC_NAMES,
    RuntimeSnapshotWriter,
    read_snapshot,
)
from indexly.rename_watch.runtime_status import build_runtime_report
from indexly.rename_watch.service import RenameWatchService
from indexly.rename_watch.service_templates import render_service_template


def _config(tmp_path, service=None):
    watch = tmp_path / "watch"
    watch.mkdir(parents=True)
    document = {
        "version": 1,
        "jobs": [
            {
                "id": "inbox",
                "watch_path": str(watch),
                "destination_subfolder": "processed",
                "pattern": "{date}-{title}-{counter}",
                "counter_format": "03d",
            }
        ],
    }
    if service is not None:
        document["service"] = service
    path = tmp_path / "rename-watch.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_service_config_defaults_and_validation(tmp_path):
    settings = load_settings(str(_config(tmp_path)))
    assert settings.service == RenameWatchServiceSettings(30.0, 5.0, 15.0)

    path = _config(
        tmp_path / "custom",
        {
            "shutdown_drain_timeout_seconds": 7.5,
            "health_interval_seconds": 2,
            "health_stale_after_seconds": 9,
        },
    )
    assert load_settings(str(path)).service == RenameWatchServiceSettings(7.5, 2.0, 9.0)


@pytest.mark.parametrize(
    "service",
    [
        {"shutdown_drain_timeout_seconds": 0},
        {"health_interval_seconds": float("inf")},
        {"health_interval_seconds": 5, "health_stale_after_seconds": 5},
    ],
)
def test_service_config_rejects_invalid_health_and_drain_values(tmp_path, service):
    with pytest.raises(RenameWatchConfigError):
        load_settings(str(_config(tmp_path, service)))


def test_runtime_snapshot_is_namespaced_strict_and_side_effect_free(tmp_path):
    settings = load_settings(str(_config(tmp_path)))
    state = tmp_path / "state"
    assert read_snapshot(settings.jobs, state) is None
    assert not state.exists()

    metrics = {name: 0 for name in METRIC_NAMES}
    metrics["scheduled"] = 3
    writer = RuntimeSnapshotWriter(settings.jobs, state)
    writer.write("ready", metrics)
    snapshot = read_snapshot(settings.jobs, state)
    assert snapshot["state"] == "ready"
    assert snapshot["metrics"]["scheduled"] == 3
    serialized = json.dumps(snapshot)
    assert str(settings.jobs[0].watch_path) not in serialized
    assert "error" not in snapshot


def test_runtime_reports_have_stable_schemas_and_unavailable_exit(tmp_path, capsys):
    config = _config(tmp_path)
    state = tmp_path / "state"
    for action in ("health", "readiness", "metrics"):
        report = build_runtime_report(str(config), action=action, state_root=state)
        assert report["schema"] == "indexly.rename-watch." + action
        assert report["version"] == 1
        assert report["state"] == "unavailable"
    assert run_with_error_contract(lambda: 4, json_errors=False) == 4
    assert capsys.readouterr().err == ""


def test_shutdown_uses_one_deadline_and_abandons_without_processing(tmp_path):
    now = [0.0]
    sleeps = []

    def clock():
        return now[0]

    def sleeper(delay):
        sleeps.append(delay)
        now[0] += delay

    service = RenameWatchService(
        [],
        state_root=tmp_path,
        clock=clock,
        sleeper=sleeper,
        service_settings=RenameWatchServiceSettings(0.25, 0.1, 1.0),
    )
    service.pending[("inbox", "source")] = (
        SimpleNamespace(),
        Path("source"),
        100.0,
        0,
        True,
    )
    service.request_shutdown()
    assert service._shutdown_deadline == 0.25
    service._drain_pending()
    assert sleeps
    assert service.metrics["shutdown_abandoned_pending"] == 1
    assert service.metrics["terminal_failures"] == 0
    assert not service.pending


def test_second_shutdown_request_makes_deadline_immediate(tmp_path):
    service = RenameWatchService(
        [], state_root=tmp_path, clock=lambda: 4.0,
        service_settings=RenameWatchServiceSettings(30, 5, 15),
    )
    service.request_shutdown()
    assert service._shutdown_deadline == 34.0
    service.request_shutdown(interrupted=True)
    assert service._shutdown_deadline == 4.0
    assert service._shutdown_interrupted is True
    assert service._accepting_events is False


def test_tick_stops_between_claimed_operations_at_shutdown_deadline(tmp_path):
    now = [0.0]
    service = RenameWatchService(
        [], state_root=tmp_path, clock=lambda: now[0],
        service_settings=RenameWatchServiceSettings(1, 0.1, 1),
    )
    for name in ("first", "second"):
        service.pending[("inbox", name)] = (
            SimpleNamespace(), Path(name), 0.0, 0, False
        )
    processed = []

    def process(_job, path, _attempts):
        processed.append(path.name)
        now[0] = 2.0

    service._process = process
    service.request_shutdown()
    service.tick(reconcile=False)
    assert processed == ["first"]
    assert len(service.pending) == 1


def test_second_shutdown_request_interrupts_observer_join_slices(tmp_path):
    service = RenameWatchService(
        [], state_root=tmp_path,
        service_settings=RenameWatchServiceSettings(30, 5, 15),
    )

    class Observer:
        alive = True
        timeouts = []

        def stop(self):
            pass

        def is_alive(self):
            return self.alive

        def join(self, timeout):
            self.timeouts.append(timeout)
            service.request_shutdown()

    observer = Observer()
    service.observers = [observer]
    service.request_shutdown()
    service._stop_observers()
    assert observer.timeouts == [0.1]


def test_retry_metric_counts_attempt_transition_during_event_race(tmp_path):
    service = RenameWatchService([], state_root=tmp_path, clock=lambda: 0.0)
    job = SimpleNamespace(job_id="inbox", settle_seconds=0.0)
    path = tmp_path / "source.txt"
    service.schedule(job, path, attempts=0, assume_eligible=True)
    service.schedule(job, path, attempts=1, assume_eligible=True)
    assert service.metrics["scheduled"] == 1
    assert service.metrics["retries"] == 1


def test_audit_failures_are_fatal_and_interrupts_are_not_counted(tmp_path):
    service = RenameWatchService([], state_root=tmp_path)
    with pytest.raises(RuntimeError):
        service._audit(lambda: (_ for _ in ()).throw(RuntimeError("audit")))
    assert service.metrics["audit_write_failures"] == 1
    with pytest.raises(KeyboardInterrupt):
        service._audit(lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert service.metrics["audit_write_failures"] == 1


def test_template_render_uses_absolute_derived_values_and_timeout(tmp_path, monkeypatch):
    config = _config(tmp_path)
    home = tmp_path / "runtime"
    monkeypatch.setenv("INDEXLY_HOME", str(home))
    rendered = render_service_template(
        str(config), platform="systemd", service_user="indexly", service_group="indexly"
    )
    assert "@@" not in rendered
    assert "TimeoutStopSec=40s" in rendered
    assert "rename-watch.json" in rendered
    assert str((home / "service-logs").resolve()) not in rendered  # journal owns systemd output


def test_templates_preserve_unicode_and_parse_manager_formats(tmp_path, monkeypatch):
    config = _config(tmp_path / "café & queue")
    home = tmp_path / "runtime"
    monkeypatch.setenv("INDEXLY_HOME", str(home))
    systemd = render_service_template(
        str(config), platform="systemd", service_user="indexly", service_group="indexly"
    )
    assert "café" in systemd
    windows = render_service_template(
        str(config), platform="windows", service_user=r"NT AUTHORITY\LocalService"
    )
    ElementTree.fromstring(windows)
    launchd = render_service_template(
        str(config), platform="launchd", service_user="_indexly", service_group="_indexly"
    )
    plistlib.loads(launchd.encode("utf-8"))


def test_runtime_snapshot_rejects_linked_parent(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(RenameWatchConfigError):
        RuntimeSnapshotWriter([], linked).write(
            "ready", {name: 0 for name in METRIC_NAMES}
        )


def test_log_policy_checks_real_destination_and_configured_boundary(tmp_path, monkeypatch):
    actual = tmp_path / "actual-log"
    actual.mkdir()
    monkeypatch.setattr(rename_logging, "NDJSON_LOG_DIR", actual)
    assert rename_logging.validate_log_policy(max_bytes=4, retention_days=2) == (4, 2)
    assert list(actual.iterdir()) == []


def test_rename_watch_log_records_rotate_and_retention_isolated(tmp_path, monkeypatch):
    old = tmp_path / "2000" / "01" / "2000-01-01_index_events.ndjson"
    old.parent.mkdir(parents=True)
    old.write_text("{}\n", encoding="utf-8")
    manager = LogManager(log_dir=tmp_path, max_bytes=1, retention_days=1, async_mode=False)
    monkeypatch.setattr(rename_logging, "log_index_event_dict_sync", manager.log_sync)
    rename_logging.log_move("job", tmp_path / "a.txt", tmp_path / "b.txt", "{title}", 1)
    rename_logging.log_move("job", tmp_path / "c.txt", tmp_path / "d.txt", "{title}", 1)
    records = []
    for path in tmp_path.rglob("*_index_events*.ndjson"):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    assert len(records) == 2
    assert {record["event"] for record in records} == {"RENAME_WATCH_MOVED"}
    assert old.exists() is False
