from __future__ import annotations

from typing import Any


AUTODOCTOR_REPORT_JSON_KEY_WEIGHTS = {
    "RootCauseDetails": 3,
    "HealthScore": 3,
    "AutomaticRemediation": 2,
    "ExecutionStats": 2,
    "SystemInfo": 1,
    "CPU": 1,
    "Memory": 1,
    "Disk": 1,
    "Network": 1,
    "InstalledSoftware": 1,
    "Drivers": 1,
}

AUTODOCTOR_TELEMETRY_JSON_KEY_WEIGHTS = {
    "RunID": 3,
    "GeneratedAt": 3,
    "Hostname": 2,
    "ExecutionStats": 2,
    "DatabaseSync": 2,
    "System": 2,
    "Modules": 2,
    "AutoDoctorVersion": 1,
}

AUTODOCTOR_DB_SIGNATURE = {
    "diagnostics": {"module_name", "status", "health_score", "summary", "timestamp"},
    "alerts": {"alert_type", "severity", "message", "timestamp"},
    "system_info": {
        "cpu_load",
        "memory_free_gb",
        "disk_free_gb",
        "network_latency_ms",
        "timestamp",
    },
    "telemetry_modules": {"module_name", "status", "result_keys", "timestamp"},
}


def detect_autodoctor_json(raw: Any) -> dict[str, Any] | None:
    """
    Detect AutoDoctor's structured JSON outputs using weighted top-level key
    fingerprints for both report JSON and telemetry JSON.
    """
    if not isinstance(raw, dict):
        return None

    keys = set(raw.keys())
    report_matches = sorted(k for k in AUTODOCTOR_REPORT_JSON_KEY_WEIGHTS if k in keys)
    telemetry_matches = sorted(
        k for k in AUTODOCTOR_TELEMETRY_JSON_KEY_WEIGHTS if k in keys
    )
    report_score = sum(AUTODOCTOR_REPORT_JSON_KEY_WEIGHTS[k] for k in report_matches)
    telemetry_score = sum(
        AUTODOCTOR_TELEMETRY_JSON_KEY_WEIGHTS[k] for k in telemetry_matches
    )

    if report_score < 7 and telemetry_score < 8:
        return None

    if telemetry_score > report_score:
        variant = "telemetry"
        matched_keys = telemetry_matches
        score = telemetry_score
    else:
        variant = "report"
        matched_keys = report_matches
        score = report_score

    confidence = "high" if score >= 10 else "medium"
    return {
        "analysis_profile": "autodoctor",
        "autodoctor_kind": "json",
        "autodoctor_variant": variant,
        "autodoctor_confidence": confidence,
        "autodoctor_score": score,
        "matched_keys": matched_keys,
        "section_count": len(keys),
    }


def detect_autodoctor_db(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Detect AutoDoctor's SQLite schema from table names plus a small set of
    required columns on the highest-value tables.
    """
    raw = raw or {}
    tables = {str(t).lower() for t in raw.get("tables", [])}
    if not AUTODOCTOR_DB_SIGNATURE.keys() <= tables:
        return None

    schemas = raw.get("schemas", {}) or {}
    missing_requirements: dict[str, list[str]] = {}

    for table_name, required_columns in AUTODOCTOR_DB_SIGNATURE.items():
        table_schema = schemas.get(table_name) or schemas.get(table_name.lower()) or []
        column_names = {
            (
                str(col.get("name", "")).lower()
                if isinstance(col, dict)
                else str(col[1]).lower() if isinstance(col, (list, tuple)) and len(col) > 1 else ""
            )
            for col in table_schema
            if isinstance(col, (dict, list, tuple))
        }
        missing = sorted(required_columns - column_names)
        if missing:
            missing_requirements[table_name] = missing

    if missing_requirements:
        return None

    return {
        "analysis_profile": "autodoctor",
        "autodoctor_kind": "db",
        "autodoctor_confidence": "high",
        "matched_tables": sorted(AUTODOCTOR_DB_SIGNATURE.keys()),
    }
