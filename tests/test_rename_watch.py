import json
from pathlib import Path

from indexly.rename_watch.config import load_settings
from indexly.rename_watch.planner import PlanMoveLog
from indexly.rename_watch.service import RenameWatchService


def _config(tmp_path, **job_values):
    incoming = tmp_path / "incoming"; incoming.mkdir()
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
