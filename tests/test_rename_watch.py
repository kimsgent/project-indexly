import json
from pathlib import Path

from indexly.rename_watch.config import RenameWatchConfigError, initialize_settings, load_settings
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


def test_initialize_creates_safe_template(tmp_path):
    path = initialize_settings(str(tmp_path / "rename-watch.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["jobs"][0]["watch_path"] == "inbox"
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