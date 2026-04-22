from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from typing import Any


DOTNET_DATE_RE = re.compile(r"^/?Date\((?P<ms>-?\d+)(?:[+-]\d+)?\)/?$")


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def map_domain(category: str | None) -> str:
    normalized = (category or "").strip().lower()
    if normalized == "cpu":
        return "CPU pressure"
    if normalized == "memory":
        return "Memory pressure"
    if normalized == "disk":
        return "Disk pressure"
    if normalized == "network":
        return "Network health"
    if normalized in {"software", "drivers"}:
        return "Data quality"
    if normalized == "events":
        return "System events"
    if normalized == "modules":
        return "Module execution"
    if normalized == "databasesync":
        return "Database sync"
    return "General diagnostics"


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_timestamp(value: Any) -> str | None:
    """
    Present timestamps in a human-friendly form when they are parseable while
    preserving the raw string whenever the source format is unfamiliar.
    """
    raw = value.get("value") if isinstance(value, dict) else value
    if raw in (None, ""):
        return None

    text = str(raw)
    match = DOTNET_DATE_RE.fullmatch(text)
    if match:
        dt = datetime.fromtimestamp(int(match.group("ms")) / 1000, tz=timezone.utc)
        return dt.astimezone().isoformat(sep=" ", timespec="seconds")

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.isoformat(sep=" ", timespec="seconds")
        return dt.astimezone().isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return text


def _pick_host_name(report: dict[str, Any]) -> str | None:
    """
    Prefer true host identifiers when available. Telemetry exposes host data at
    the top level, while reports often omit it entirely.
    """
    candidates = [
        report.get("Hostname"),
        report.get("HostName"),
        report.get("ComputerName"),
        report.get("CsName"),
    ]

    system_info = report.get("SystemInfo") or {}
    candidates.extend(
        system_info.get(key)
        for key in ("CsName", "ComputerName", "Hostname", "HostName", "PSComputerName")
    )

    for value in candidates:
        if value:
            return str(value)

    run_id = report.get("RunID")
    if isinstance(run_id, str):
        parts = run_id.split("-")
        if len(parts) >= 3 and parts[-1]:
            return parts[-1]

    return None


def _pick_windows_label(report: dict[str, Any]) -> str | None:
    system_info = report.get("SystemInfo") or {}
    system = report.get("System") or {}
    os_block = system.get("OS") or {}
    for value in (
        system_info.get("WindowsProductName"),
        os_block.get("Caption"),
        os_block.get("Version"),
    ):
        if value:
            return str(value)
    return None


def _pick_identity(report: dict[str, Any]) -> str | None:
    return _pick_host_name(report) or _pick_windows_label(report)


def _compute_memory_used_percent(
    *,
    total: Any,
    free: Any,
    used_percent: Any = None,
) -> float | None:
    explicit_used = _coerce_float(used_percent)
    if explicit_used is not None:
        return explicit_used

    total_value = _coerce_float(total)
    free_value = _coerce_float(free)
    if total_value and total_value > 0 and free_value is not None:
        return round(((total_value - free_value) / total_value) * 100, 2)
    return None


def _pick_fullest_disk_report(disk_usage: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = [
        {
            "name": item.get("Name"),
            "free_gb": item.get("FreeGB"),
            "used_gb": item.get("UsedGB"),
        }
        for item in disk_usage
        if isinstance(item, dict)
    ]
    if not normalized:
        return None
    return max(normalized, key=lambda item: _coerce_float(item.get("used_gb")) or 0)


def _pick_fullest_disk_telemetry(disks: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = []
    for item in disks:
        if not isinstance(item, dict):
            continue
        size_gb = _coerce_float(item.get("SizeGB"))
        free_gb = _coerce_float(item.get("FreeSpaceGB"))
        used_gb = None
        if size_gb is not None and free_gb is not None:
            used_gb = round(size_gb - free_gb, 2)
        normalized.append(
            {
                "name": item.get("DeviceID"),
                "free_gb": free_gb,
                "used_gb": used_gb,
            }
        )

    if not normalized:
        return None
    return max(normalized, key=lambda item: _coerce_float(item.get("used_gb")) or 0)


def _build_main_concern(
    metric_states: list[dict[str, Any]],
    primary_driver: dict[str, Any] | None,
) -> str:
    concerning_metric = next(
        (
            item
            for item in metric_states
            if item.get("State") not in {"Stable", "Decreasing"}
        ),
        None,
    )
    if concerning_metric:
        return f"{concerning_metric.get('Metric')} {concerning_metric.get('State')}"
    if primary_driver:
        return str(primary_driver.get("Category") or "General diagnostics")
    return "System stable"


def _summarize_software(software_rows: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    names = [
        str(item.get("DisplayName")).strip()
        for item in software_rows
        if isinstance(item, dict) and item.get("DisplayName")
    ]
    normalized = [name.lower() for name in names if name]
    duplicates = [
        {"name": name, "count": count}
        for name, count in Counter(normalized).most_common(top_n)
        if count > 1
    ]
    blank_rows = sum(
        1
        for item in software_rows
        if not isinstance(item, dict) or not (item.get("DisplayName") or "").strip()
    )
    return {
        "count": len(software_rows),
        "blank_rows": blank_rows,
        "duplicate_names": duplicates,
        "sample": names[:top_n],
    }


def _summarize_drivers(driver_rows: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    incomplete_rows = [
        item
        for item in driver_rows
        if isinstance(item, dict)
        and (
            not (item.get("DeviceName") or "").strip()
            or not (item.get("DriverVersion") or "").strip()
            or not (item.get("DriverProviderName") or "").strip()
        )
    ]
    return {
        "count": len(driver_rows),
        "incomplete_rows": len(incomplete_rows),
        "sample_incomplete": incomplete_rows[:top_n],
    }


def _report_summary(
    report: dict[str, Any],
    *,
    top_n: int,
    sections: set[str],
) -> dict[str, Any]:
    root_details = report.get("RootCauseDetails") or {}
    metric_states = ensure_list(root_details.get("MetricStates"))
    score_breakdown = root_details.get("ScoreBreakdown") or {}
    score_categories = ensure_list(score_breakdown.get("Categories"))
    findings = ensure_list(root_details.get("Findings"))
    trend_window = (
        (root_details.get("HistoricalAnalysis") or {}).get("TrendWindow")
        or {}
    )

    primary_driver = score_categories[0] if score_categories else None
    stable_components = [
        {"metric": item.get("Metric"), "state": item.get("State")}
        for item in metric_states
        if item.get("State") in {"Stable", "Decreasing"}
    ]

    grouped_findings: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        grouped_findings.setdefault(map_domain(finding.get("Category")), []).append(
            finding
        )

    system_info = report.get("SystemInfo") or {}
    cpu = report.get("CPU") or {}
    memory = report.get("Memory") or {}
    disk = report.get("Disk") or {}
    network = report.get("Network") or {}
    remediation = report.get("AutomaticRemediation") or {}

    installed_software = ensure_list(report.get("InstalledSoftware"))
    drivers = ensure_list(report.get("Drivers"))
    startup_programs = ensure_list(report.get("StartupPrograms"))
    adapters = ensure_list(network.get("Adapters"))
    top_processes = ensure_list(cpu.get("TopProcesses"))
    generated_raw = report.get("GeneratedAt") or remediation.get("Timestamp")

    summary = {
        "analysis_profile": "autodoctor",
        "source_type": "json",
        "autodoctor_variant": "report",
        "section_count": len(report),
        "matched_sections": sorted(report.keys()),
        "host_name": _pick_host_name(report),
        "identity": _pick_identity(report),
        "generated_time": _format_timestamp(generated_raw),
        "generated_time_raw": generated_raw,
        "health": {
            "numeric": (report.get("HealthScore") or {}).get("Numeric"),
            "display": (report.get("HealthScore") or {}).get("Display"),
            "summary": report.get("RootCauseAnalysis"),
            "main_concern": _build_main_concern(metric_states, primary_driver),
        },
    }

    if "overview" in sections:
        summary["overview"] = {
            "windows_product": system_info.get("WindowsProductName"),
            "windows_version": system_info.get("WindowsVersion"),
            "architecture": system_info.get("OsArchitecture"),
            "uptime_days": (report.get("SystemUptime") or {}).get("UptimeDays"),
            "runtime_seconds": (report.get("ExecutionStats") or {}).get(
                "ScriptRuntimeSeconds"
            ),
        }

    if "system" in sections:
        disk_usage = ensure_list(disk.get("Usage"))
        summary["system"] = {
            "cpu_load_percent": (cpu.get("LoadStatus") or {}).get(
                "CurrentCPULoadPercent"
            ),
            "memory_free_gb": memory.get("FreeGB"),
            "memory_total_gb": memory.get("TotalGB"),
            "memory_used_percent": _compute_memory_used_percent(
                total=memory.get("TotalGB"),
                free=memory.get("FreeGB"),
                used_percent=memory.get("UsedPercent"),
            ),
            "network_latency_ms": (network.get("Connectivity") or {}).get(
                "AvgLatencyMS"
            ),
            "network_status": (network.get("Connectivity") or {}).get("Status"),
            "fullest_disk": _pick_fullest_disk_report(disk_usage),
            "top_processes": top_processes[:top_n],
        }

    if "findings" in sections:
        summary["findings"] = {
            "severity_counts": root_details.get("SeverityCounts") or {},
            "latest_findings": findings[:top_n],
            "findings_by_domain": [
                {"domain": domain, "count": len(items), "findings": items[:top_n]}
                for domain, items in grouped_findings.items()
            ],
            "primary_driver": primary_driver,
            "supporting_factors": [
                finding.get("Message")
                for finding in ensure_list(
                    primary_driver.get("Findings") if primary_driver else []
                )[:top_n]
                if isinstance(finding, dict) and finding.get("Message")
            ]
            or [
                finding.get("Message")
                for finding in findings[:top_n]
                if isinstance(finding, dict) and finding.get("Message")
            ],
        }

    if "inventory" in sections:
        summary["inventory"] = {
            "software": _summarize_software(installed_software, top_n),
            "drivers": _summarize_drivers(drivers, top_n),
            "startup_program_count": len(startup_programs),
            "network_adapter_count": len(adapters),
            "top_startup_programs": startup_programs[:top_n],
        }

    if "trends" in sections:
        summary["trends"] = {
            "window": {
                "label": trend_window.get("WindowLabel"),
                "historical_samples": trend_window.get("HistoricalSamples"),
                "minimum_samples": trend_window.get("MinimumSamples"),
                "used_fallback": trend_window.get("UsedFallback"),
                "fallback_reason": trend_window.get("FallbackReason"),
            },
            "metric_states": metric_states[:top_n],
            "stable_components": stable_components[:top_n],
            "gradual_trends": ensure_list(root_details.get("GradualTrends"))[:top_n],
            "baseline_deviations": ensure_list(
                root_details.get("BaselineDeviations")
            )[:top_n],
        }

    if "remediation" in sections:
        summary["remediation"] = {
            "status": remediation.get("Status"),
            "timestamp": _format_timestamp(remediation.get("Timestamp")),
            "timestamp_raw": remediation.get("Timestamp"),
            "restore_point": remediation.get("RestorePoint"),
            "system_repair": remediation.get("SystemRepair"),
            "defender_scan": remediation.get("DefenderScan"),
        }

    if "data_quality" in sections:
        summary["data_quality"] = {
            "detected_issues": ensure_list(root_details.get("DetectedIssues"))[:top_n],
            "validation_issues": ensure_list(root_details.get("ValidationIssues"))[
                :top_n
            ],
            "software_blank_rows": summary.get("inventory", {})
            .get("software", {})
            .get("blank_rows"),
            "software_duplicate_names": summary.get("inventory", {})
            .get("software", {})
            .get("duplicate_names"),
            "incomplete_driver_rows": summary.get("inventory", {})
            .get("drivers", {})
            .get("incomplete_rows"),
        }

    return summary


def _telemetry_summary(
    report: dict[str, Any],
    *,
    top_n: int,
    sections: set[str],
) -> dict[str, Any]:
    execution = report.get("ExecutionStats") or {}
    database_sync = report.get("DatabaseSync") or {}
    system = report.get("System") or {}
    os_block = system.get("OS") or {}
    environment = system.get("Environment") or {}
    cpu = system.get("CPU") or {}
    memory = system.get("Memory") or {}
    disks = ensure_list(system.get("Disk"))
    network = system.get("Network") or {}
    modules = ensure_list(report.get("Modules"))

    module_count = execution.get("ModuleCount") or len(modules) or None
    modules_succeeded = execution.get("ModulesSucceeded")
    modules_failed = execution.get("ModulesFailed")
    failed_modules = [
        module
        for module in modules
        if isinstance(module, dict)
        and str(module.get("Status") or "").lower() != "success"
    ]

    if modules_succeeded is None and module_count is not None and modules_failed is not None:
        modules_succeeded = max(module_count - int(modules_failed), 0)
    if modules_failed is None:
        modules_failed = len(failed_modules)

    health_numeric = None
    if module_count and modules_succeeded is not None:
        health_numeric = round((int(modules_succeeded) / int(module_count)) * 100)

    sync_status = "Healthy"
    sync_summary = "No failing modules recorded in telemetry snapshot"
    if database_sync.get("Error"):
        sync_status = "Error"
        sync_summary = str(database_sync.get("Error"))
    elif database_sync and not database_sync.get("Enabled", True):
        sync_status = "Disabled"
        sync_summary = "Database sync is disabled for this telemetry snapshot"
    elif database_sync and (
        not database_sync.get("DiagnosticsWritten", True)
        or not database_sync.get("AlertsWritten", True)
    ):
        sync_status = "Partial"
        sync_summary = "Telemetry sync completed with partial database writes"

    latest_findings: list[dict[str, Any]] = []
    if database_sync.get("Error"):
        latest_findings.append(
            {
                "Category": "DatabaseSync",
                "Severity": "Critical",
                "Message": str(database_sync.get("Error")),
            }
        )
    elif database_sync and not database_sync.get("Enabled", True):
        latest_findings.append(
            {
                "Category": "DatabaseSync",
                "Severity": "Warning",
                "Message": "Database sync is disabled for this telemetry snapshot.",
            }
        )
    elif database_sync and (
        not database_sync.get("DiagnosticsWritten", True)
        or not database_sync.get("AlertsWritten", True)
    ):
        latest_findings.append(
            {
                "Category": "DatabaseSync",
                "Severity": "Warning",
                "Message": "Telemetry sync completed with partial writes.",
            }
        )

    for module in failed_modules[:top_n]:
        latest_findings.append(
            {
                "Category": "Modules",
                "Severity": "Critical",
                "Message": f"{module.get('ModuleName') or 'Unknown module'} reported status {module.get('Status') or 'Unknown'}",
            }
        )

    if not latest_findings and module_count:
        latest_findings.append(
            {
                "Category": "Modules",
                "Severity": "Info",
                "Message": "All recorded modules succeeded in this telemetry snapshot.",
            }
        )

    main_concern = (
        latest_findings[0]["Message"]
        if latest_findings
        else "Telemetry snapshot healthy"
    )
    health_summary = (
        f"{len(failed_modules)} module(s) reported non-success status"
        if failed_modules
        else sync_summary
    )

    summary = {
        "analysis_profile": "autodoctor",
        "source_type": "json",
        "autodoctor_variant": "telemetry",
        "section_count": len(report),
        "matched_sections": sorted(report.keys()),
        "host_name": _pick_host_name(report),
        "identity": _pick_identity(report),
        "generated_time": _format_timestamp(report.get("GeneratedAt") or system.get("Timestamp")),
        "generated_time_raw": report.get("GeneratedAt") or system.get("Timestamp"),
        "health": {
            "numeric": health_numeric,
            "display": (
                f"{modules_succeeded}/{module_count} modules succeeded"
                if module_count and modules_succeeded is not None
                else "Telemetry snapshot"
            ),
            "summary": health_summary,
            "main_concern": main_concern,
        },
    }

    if "overview" in sections:
        summary["overview"] = {
            "windows_product": os_block.get("Caption"),
            "windows_version": os_block.get("Version") or os_block.get("Build"),
            "architecture": os_block.get("Architecture"),
            "runtime_seconds": execution.get("ScriptRuntimeSeconds"),
            "autodoctor_version": report.get("AutoDoctorVersion"),
            "user": report.get("User"),
            "run_id": report.get("RunID"),
            "module_count": module_count,
            "modules_succeeded": modules_succeeded,
            "modules_failed": modules_failed,
            "module_success_text": (
                f"{modules_succeeded}/{module_count} succeeded"
                if module_count and modules_succeeded is not None
                else None
            ),
            "manufacturer": environment.get("Manufacturer"),
            "model": environment.get("Model"),
            "system_type": environment.get("Type"),
        }

    if "system" in sections:
        summary["system"] = {
            "cpu_load_percent": cpu.get("CurrentLoad"),
            "memory_free_gb": memory.get("FreeGB"),
            "memory_total_gb": memory.get("TotalGB"),
            "memory_used_percent": _compute_memory_used_percent(
                total=memory.get("TotalGB"),
                free=memory.get("FreeGB"),
            ),
            "network_latency_ms": None,
            "network_status": network.get("Description")
            or ("DHCP enabled" if network.get("DHCPEnabled") else "Static network"),
            "fullest_disk": _pick_fullest_disk_telemetry(disks),
            "top_processes": [],
        }

    if "findings" in sections:
        summary["findings"] = {
            "severity_counts": {
                "Critical": sum(
                    1 for item in latest_findings if item.get("Severity") == "Critical"
                ),
                "Warning": sum(
                    1 for item in latest_findings if item.get("Severity") == "Warning"
                ),
                "Info": sum(
                    1 for item in latest_findings if item.get("Severity") == "Info"
                ),
            },
            "latest_findings": latest_findings[:top_n],
            "supporting_factors": [item.get("Message") for item in latest_findings[:top_n]],
        }

    if "inventory" in sections:
        summary["inventory"] = {
            "module_count": module_count,
            "failed_module_count": len(failed_modules),
            "module_sample": [
                module.get("ModuleName")
                for module in modules[:top_n]
                if isinstance(module, dict) and module.get("ModuleName")
            ],
        }

    if "trends" in sections:
        summary["trends"] = {
            "window": {},
            "metric_states": [],
            "stable_components": [],
            "gradual_trends": [],
            "baseline_deviations": [],
        }

    if "remediation" in sections:
        summary["remediation"] = {}

    if "data_quality" in sections:
        summary["data_quality"] = {
            "database_sync_error": database_sync.get("Error"),
            "modules_missing_result_keys": [
                module.get("ModuleName")
                for module in modules
                if isinstance(module, dict) and not module.get("ResultKeys")
            ][:top_n],
        }

    summary["database_sync"] = {
        "status": sync_status,
        "enabled": database_sync.get("Enabled"),
        "diagnostics_written": database_sync.get("DiagnosticsWritten"),
        "alerts_written": database_sync.get("AlertsWritten"),
        "last_write": _format_timestamp(database_sync.get("LastWriteUTC")),
        "last_write_raw": database_sync.get("LastWriteUTC"),
        "error": database_sync.get("Error"),
    }

    return summary


def build_autodoctor_json_summary(
    report: dict[str, Any],
    *,
    top_n: int = 5,
    sections: set[str] | None = None,
) -> dict[str, Any]:
    """
    Build a compact, source-native summary for AutoDoctor's two JSON families:
    the human-readable report output and the telemetry snapshot output.
    """
    sections = sections or {
        "overview",
        "system",
        "findings",
        "inventory",
        "trends",
        "remediation",
        "data_quality",
    }

    telemetry_keys = {"RunID", "GeneratedAt", "Hostname", "System", "Modules"}
    if telemetry_keys & set(report.keys()):
        return _telemetry_summary(report, top_n=top_n, sections=sections)
    return _report_summary(report, top_n=top_n, sections=sections)


def build_autodoctor_db_summary(
    *,
    latest_system: dict[str, Any] | None,
    alert_summary: list[dict[str, Any]],
    module_status: list[dict[str, Any]],
    health_trend: list[dict[str, Any]],
    remediation_status: dict[str, Any] | None,
    baselines: list[dict[str, Any]],
    latest_root_cause: dict[str, Any] | None,
    top_n: int = 5,
) -> dict[str, Any]:
    latest_system = latest_system or {}
    latest_root_cause = latest_root_cause or {}
    return {
        "analysis_profile": "autodoctor",
        "source_type": "db",
        "health": {
            "numeric": latest_root_cause.get("health_score"),
            "summary": latest_root_cause.get("summary"),
            "timestamp": latest_root_cause.get("timestamp"),
        },
        "system": {
            "hostname": latest_system.get("hostname"),
            "cpu_load_percent": latest_system.get("cpu_load"),
            "memory_free_gb": latest_system.get("memory_free_gb"),
            "disk_free_gb": latest_system.get("disk_free_gb"),
            "network_latency_ms": latest_system.get("network_latency_ms"),
            "timestamp": latest_system.get("timestamp"),
        },
        "findings": {
            "alert_summary": alert_summary[:top_n],
        },
        "modules": {
            "status": module_status[:top_n],
            "failed_modules": [
                item for item in module_status if int(item.get("failed") or 0) > 0
            ][:top_n],
        },
        "trends": {
            "health_trend": health_trend[-top_n:],
            "baselines": baselines[:top_n],
        },
        "remediation": remediation_status or {},
    }
