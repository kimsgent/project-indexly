import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


def _base_args(file_path, no_persist):
    return SimpleNamespace(
        file=str(file_path),
        command="analyze-file",
        no_persist=no_persist,
        show_summary=False,
        treeview=False,
        summarize_search=False,
        sortdate_by="asc",
        export_path=None,
        format="txt",
        compress_export=False,
        db_mode="replace",
        use_saved=False,
        use_cleaned=False,
    )


def _import_orchestrator(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    for module_name in (
        "indexly.analysis_orchestrator",
        "indexly.observers.runner",
        "indexly.observers",
    ):
        sys.modules.pop(module_name, None)
    return importlib.import_module("indexly.analysis_orchestrator")


def test_analyze_file_json_respects_no_persist(monkeypatch, tmp_path):
    orchestrator = _import_orchestrator(monkeypatch, tmp_path)
    file_path = tmp_path / "records.json"
    file_path.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")

    save_calls = []

    monkeypatch.setattr(orchestrator, "detect_file_type", lambda _: "json")
    monkeypatch.setattr(orchestrator, "validate_file_content", lambda *_: True)
    monkeypatch.setattr(
        orchestrator,
        "detect_and_load",
        lambda *_: {"df": None, "raw": [{"a": 1}, {"a": 2}], "metadata": {}},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_record_list_json_pipeline",
        lambda **_: (
            pd.DataFrame({"a": [1, 2]}),
            {"detected_type": "ndjson"},
            {"rows": 2, "cols": 1},
            {},
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "save_analysis_result",
        lambda **kwargs: save_calls.append(kwargs),
    )

    args = _base_args(file_path=file_path, no_persist=True)
    result = orchestrator.analyze_file(args)

    assert result is not None
    assert save_calls == []


def test_analyze_file_json_persists_when_enabled(monkeypatch, tmp_path):
    orchestrator = _import_orchestrator(monkeypatch, tmp_path)
    file_path = tmp_path / "records.json"
    file_path.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")

    save_calls = []

    monkeypatch.setattr(orchestrator, "detect_file_type", lambda _: "json")
    monkeypatch.setattr(orchestrator, "validate_file_content", lambda *_: True)
    monkeypatch.setattr(
        orchestrator,
        "detect_and_load",
        lambda *_: {"df": None, "raw": [{"a": 1}, {"a": 2}], "metadata": {}},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_record_list_json_pipeline",
        lambda **_: (
            pd.DataFrame({"a": [1, 2]}),
            {"detected_type": "ndjson"},
            {"rows": 2, "cols": 1},
            {},
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "save_analysis_result",
        lambda **kwargs: save_calls.append(kwargs),
    )

    args = _base_args(file_path=file_path, no_persist=False)
    result = orchestrator.analyze_file(args)

    assert result is not None
    assert len(save_calls) == 1


def test_analyze_json_command_uses_orchestrator_json_path(monkeypatch, tmp_path):
    orchestrator = _import_orchestrator(monkeypatch, tmp_path)
    file_path = tmp_path / "records.json"
    file_path.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")

    save_calls = []
    detect_calls = []

    monkeypatch.setattr(orchestrator, "detect_file_type", lambda _: "json")
    monkeypatch.setattr(orchestrator, "validate_file_content", lambda *_: True)

    def _fake_detect_and_load(*_args, **_kwargs):
        detect_calls.append("called")
        return {"df": None, "raw": [{"a": 1}, {"a": 2}], "metadata": {}}

    monkeypatch.setattr(orchestrator, "detect_and_load", _fake_detect_and_load)
    monkeypatch.setattr(
        orchestrator,
        "run_record_list_json_pipeline",
        lambda **_: (
            pd.DataFrame({"a": [1, 2]}),
            {"detected_type": "ndjson"},
            {"rows": 2, "cols": 1},
            {},
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_json_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("analyze-json should use the orchestrator JSON path")
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "save_analysis_result",
        lambda **kwargs: save_calls.append(kwargs),
    )

    args = _base_args(file_path=file_path, no_persist=False)
    args.command = "analyze-json"
    result = orchestrator.analyze_file(args)

    assert result is not None
    assert detect_calls == ["called"]
    assert len(save_calls) == 1
