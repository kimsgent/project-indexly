import importlib
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from indexly.analyze_utils import validate_json_content
from indexly.autodoctor_detect import detect_autodoctor_db, detect_autodoctor_json
from indexly.autodoctor_analyzer import analyze_autodoctor
from indexly.autodoctor_summary import build_autodoctor_json_summary
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

AUTODOCTOR_TELEMETRY_SAMPLE = {
    "RunID": "20260416-081258-BTNB05",
    "GeneratedAt": "2026-04-16T08:32:47.8857104+02:00",
    "Hostname": "BTNB05",
    "User": "Nango Franklin",
    "AutoDoctorVersion": "1.2.0",
    "ExecutionStats": {
        "ModuleCount": 17,
        "ScriptRuntimeSeconds": 1188.56,
        "ModulesSucceeded": 17,
        "ModulesFailed": 0,
    },
    "DatabaseSync": {
        "LastWriteUTC": "2026-04-16T06:32:47.9557223Z",
        "Error": None,
        "DiagnosticsWritten": True,
        "AlertsWritten": True,
        "Enabled": True,
    },
    "System": {
        "Timestamp": "2026-04-16T08:32:47.8857104+02:00",
        "OS": {
            "Caption": "Microsoft Windows 11 Pro",
            "LastBootUp": "/Date(1775543269500)/",
            "Architecture": "64-Bit",
            "Build": "26100",
            "Version": "10.0.26100",
        },
        "Environment": {
            "Manufacturer": "LENOVO",
            "Model": "20E2001JGE",
            "Type": "PhysicalMachine",
        },
        "CPU": {"CurrentLoad": 26},
        "Memory": {"TotalGB": 31.7, "FreeGB": 17.09},
        "Disk": [
            {
                "DeviceID": "C:",
                "SizeGB": 416.42,
                "FreeSpaceGB": 198.77,
                "PercentFree": 47.7,
            }
        ],
        "Network": {
            "Description": "Intel(R) Ethernet Connection",
            "DHCPEnabled": False,
            "IPAddresses": ["192.168.77.194"],
        },
    },
    "Modules": [
        {
            "ModuleName": "CPU Analysis",
            "Status": "Success",
            "ResultKeys": ["CurrentCPULoadPercent"],
        }
    ],
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


def test_detect_autodoctor_json_marks_telemetry_variant():
    detection = detect_autodoctor_json(AUTODOCTOR_TELEMETRY_SAMPLE)

    assert detection is not None
    assert detection["analysis_profile"] == "autodoctor"
    assert detection["autodoctor_variant"] == "telemetry"


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


def test_build_autodoctor_json_summary_uses_fallback_identity_and_formats_timestamp():
    report = {
        **AUTODOCTOR_JSON_SAMPLE,
        "AutomaticRemediation": {
            "Status": "Completed",
            "Timestamp": "/Date(1776321167385)/",
        },
    }

    summary = build_autodoctor_json_summary(report)

    assert summary["autodoctor_variant"] == "report"
    assert summary["host_name"] is None
    assert summary["identity"] == "Windows 11 Pro"
    assert summary["generated_time"] != "/Date(1776321167385)/"
    assert "2026" in str(summary["generated_time"])


def test_build_autodoctor_json_summary_prefers_telemetry_hostname():
    summary = build_autodoctor_json_summary(AUTODOCTOR_TELEMETRY_SAMPLE)

    assert summary["autodoctor_variant"] == "telemetry"
    assert summary["host_name"] == "BTNB05"
    assert summary["identity"] == "BTNB05"
    assert summary["generated_time"] != AUTODOCTOR_TELEMETRY_SAMPLE["GeneratedAt"]
    assert summary["overview"]["module_count"] == 17


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
