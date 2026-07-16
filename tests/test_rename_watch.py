import json
import errno
import os
from dataclasses import replace
from pathlib import Path

import pytest

from indexly.rename_watch.config import RenameWatchConfigError, initialize_settings, load_settings
from indexly.rename_watch import planner as planner_module
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


def test_once_ignores_empty_folder_without_logging(tmp_path, monkeypatch):
    path, _ = _config(tmp_path)
    job = load_settings(str(path)).jobs[0]
    calls = []
    monkeypatch.setattr("indexly.rename_watch.service.log_move", lambda *args: calls.append(args))
    RenameWatchService([job]).run_once()
    assert calls == []


def test_once_creates_missing_watch_folder_without_creating_destination(tmp_path):
    path, _ = _config(tmp_path, watch_path="missing/parents/inbox")
    incoming = tmp_path / "missing" / "parents" / "inbox"
    job = load_settings(str(path)).jobs[0]

    RenameWatchService([job]).run_once()

    assert incoming.is_dir()
    assert not job.destination_path.exists()


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

    def create_collision_then_move(source_path, target_path):
        if not collided:
            target_path.write_text("existing", encoding="utf-8")
            collided.append(target_path)
        return real_move(source_path, target_path)

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
    assert not target.exists()


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
        RenameWatchService([first_job, second_job]).run_forever()
    except RenameWatchConfigError as exc:
        assert "second" in str(exc)
        assert str(second_path) in str(exc)
    else:
        raise AssertionError("observer startup failure must be reported")

    assert incoming.is_dir()
    assert second_path.is_dir()
    assert all(observer.stopped for observer in observers)
