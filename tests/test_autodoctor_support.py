import importlib
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from indexly.analyze_utils import validate_json_content
from indexly.autodoctor_detect import detect_autodoctor_db
from indexly.autodoctor_analyzer import analyze_autodoctor
from indexly.cli_utils import build_parser
from indexly.universal_loader import detect_and_load


AUTODOCTOR_JSON_SAMPLE = {
    "SystemInfo": {"WindowsProductName": "Windows 11 Pro"},
    "CPU": {"TopProcesses": [{"ProcessName": "proc", "CPU": 12.3}]},
    "Memory": {"FreeGB": 12.5, "TotalGB": 31.7},
    "Disk": {"Usage": [{"Name": "C", "FreeGB": 50, "UsedGB": 100}]},
    "RootCauseDetails": {"Findings": [], "MetricStates": []},
    "HealthScore": {"Numeric": 92, "Display": "92 / 100"},
    "AutomaticRemediation": {"Status": "Completed"},
    "ExecutionStats": {"ScriptRuntimeSeconds": 12.5},
}


def _import_orchestrator(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    for module_name in (
        "indexly.analysis_orchestrator",
        "indexly.observers.runner",
        "indexly.observers",
    ):
        sys.modules.pop(module_name, None)
    return importlib.import_module("indexly.analysis_orchestrator")


def test_validate_json_content_accepts_utf8_bom(tmp_path):
    file_path = tmp_path / "AutoDoctor_Report.json"
    file_path.write_text(
        "\ufeff" + json.dumps(AUTODOCTOR_JSON_SAMPLE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    assert validate_json_content(file_path) is True


def test_detect_and_load_marks_autodoctor_json(tmp_path):
    file_path = tmp_path / "AutoDoctor_Report.json"
    file_path.write_text(
        "\ufeff" + json.dumps(AUTODOCTOR_JSON_SAMPLE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = detect_and_load(file_path, SimpleNamespace())

    assert result is not None
    assert result["metadata"]["analysis_profile"] == "autodoctor"
    assert result["metadata"]["autodoctor_kind"] == "json"


def test_detect_autodoctor_db_supports_tuple_schema():
    raw = {
        "tables": ["diagnostics", "alerts", "system_info", "telemetry_modules"],
        "schemas": {
            "diagnostics": [
                (0, "id", "INTEGER", 0, None, 1),
                (1, "module_name", "TEXT", 0, None, 0),
                (2, "status", "TEXT", 0, None, 0),
                (3, "health_score", "INTEGER", 0, None, 0),
                (4, "summary", "TEXT", 0, None, 0),
                (5, "timestamp", "DATETIME", 0, None, 0),
            ],
            "alerts": [
                (0, "id", "INTEGER", 0, None, 1),
                (1, "alert_type", "TEXT", 0, None, 0),
                (2, "severity", "TEXT", 0, None, 0),
                (3, "message", "TEXT", 0, None, 0),
                (4, "timestamp", "DATETIME", 0, None, 0),
            ],
            "system_info": [
                (0, "id", "INTEGER", 0, None, 1),
                (1, "cpu_load", "REAL", 0, None, 0),
                (2, "memory_free_gb", "REAL", 0, None, 0),
                (3, "disk_free_gb", "REAL", 0, None, 0),
                (4, "network_latency_ms", "REAL", 0, None, 0),
                (5, "timestamp", "DATETIME", 0, None, 0),
            ],
            "telemetry_modules": [
                (0, "id", "INTEGER", 0, None, 1),
                (1, "module_name", "TEXT", 0, None, 0),
                (2, "status", "TEXT", 0, None, 0),
                (3, "result_keys", "TEXT", 0, None, 0),
                (4, "timestamp", "DATETIME", 0, None, 0),
            ],
        },
    }

    detection = detect_autodoctor_db(raw)

    assert detection is not None
    assert detection["analysis_profile"] == "autodoctor"
    assert detection["autodoctor_kind"] == "db"


def test_analyze_file_routes_autodoctor_json(monkeypatch, tmp_path):
    orchestrator = _import_orchestrator(monkeypatch, tmp_path)
    file_path = tmp_path / "AutoDoctor_Report.json"
    file_path.write_text(json.dumps(AUTODOCTOR_JSON_SAMPLE), encoding="utf-8")

    monkeypatch.setattr(orchestrator, "detect_file_type", lambda _: "json")
    monkeypatch.setattr(orchestrator, "validate_file_content", lambda *_: True)
    monkeypatch.setattr(
        orchestrator,
        "detect_and_load",
        lambda *_args, **_kwargs: {
            "df": None,
            "raw": AUTODOCTOR_JSON_SAMPLE,
            "metadata": {
                "analysis_profile": "autodoctor",
                "autodoctor_kind": "json",
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_autodoctor_json_file",
        lambda **_kwargs: (
            pd.DataFrame([{"section": "health", "metric": "numeric", "value": 92}]),
            {"health": {"numeric": 92}},
            {"health": {"numeric": 92}},
        ),
    )

    args = SimpleNamespace(
        file=str(file_path),
        command="analyze-file",
        no_persist=True,
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

    result = orchestrator.analyze_file(args)

    assert result is not None
    assert result.file_type == "autodoctor-json"
    assert result.metadata["analysis_profile"] == "autodoctor"


def test_analyze_file_persists_autodoctor_json_via_specialized_saver(
    monkeypatch,
    tmp_path,
):
    orchestrator = _import_orchestrator(monkeypatch, tmp_path)
    file_path = tmp_path / "AutoDoctor_Report.json"
    file_path.write_text(json.dumps(AUTODOCTOR_JSON_SAMPLE), encoding="utf-8")

    saved_payload = {}

    monkeypatch.setattr(orchestrator, "detect_file_type", lambda _: "json")
    monkeypatch.setattr(orchestrator, "validate_file_content", lambda *_: True)
    monkeypatch.setattr(
        orchestrator,
        "detect_and_load",
        lambda *_args, **_kwargs: {
            "df": None,
            "raw": AUTODOCTOR_JSON_SAMPLE,
            "metadata": {
                "analysis_profile": "autodoctor",
                "autodoctor_kind": "json",
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_autodoctor_json_file",
        lambda **_kwargs: (
            pd.DataFrame([{"section": "health", "metric": "numeric", "value": 92}]),
            {"health": {"numeric": 92}},
            {"health": {"numeric": 92}},
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_persist_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy persistence path should not be used")
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "save_analysis_result",
        lambda **kwargs: saved_payload.update(kwargs),
    )

    args = SimpleNamespace(
        file=str(file_path),
        command="analyze-file",
        no_persist=False,
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

    result = orchestrator.analyze_file(args)

    assert result is not None
    assert result.file_type == "autodoctor-json"
    assert result.persisted is True
    assert saved_payload["file_type"] == "autodoctor-json"
    assert saved_payload["summary"] == {"health": {"numeric": 92}}
    assert isinstance(saved_payload["sample_data"], pd.DataFrame)


def test_build_parser_supports_analyze_autodoctor():
    parser = build_parser()
    args = parser.parse_args(["analyze-autodoctor", "AutoDoctor_Report.json"])

    assert args.path == "AutoDoctor_Report.json"
    assert args.source == "auto"
    assert args.top_n == 5


def test_analyze_autodoctor_persists_json_by_default(monkeypatch, tmp_path):
    file_path = tmp_path / "AutoDoctor_Report.json"
    file_path.write_text(json.dumps(AUTODOCTOR_JSON_SAMPLE), encoding="utf-8")

    saved_payload = {}

    monkeypatch.setattr(
        "indexly.autodoctor_analyzer.analyze_autodoctor_json_file",
        lambda *_args, **_kwargs: (
            pd.DataFrame([{"section": "health", "metric": "numeric", "value": 92}]),
            {"health": {"numeric": 92}},
            {"health": {"numeric": 92}},
        ),
    )
    monkeypatch.setattr(
        "indexly.autodoctor_analyzer.save_analysis_result",
        lambda **kwargs: saved_payload.update(kwargs),
    )

    args = SimpleNamespace(
        path=str(file_path),
        source="json",
        no_persist=False,
        show_summary=False,
        summary_only=False,
        full=False,
        sections=None,
        top_n=5,
    )

    result = analyze_autodoctor(args)

    assert result is not None
    assert result.file_type == "autodoctor-json"
    assert result.persisted is True
    assert saved_payload["file_type"] == "autodoctor-json"
