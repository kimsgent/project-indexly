from __future__ import annotations

from collections import Counter
from typing import Any


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
    return "General diagnostics"


def _pick_host_name(report: dict[str, Any]) -> str | None:
    system_info = report.get("SystemInfo") or {}
    for key in ("CsName", "ComputerName", "Hostname", "HostName", "PSComputerName"):
        value = system_info.get(key)
        if value:
            return str(value)
    return None


def _build_main_concern(metric_states: list[dict[str, Any]], primary_driver: dict[str, Any] | None) -> str:
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


def build_autodoctor_json_summary(
    report: dict[str, Any],
    *,
    top_n: int = 5,
    sections: set[str] | None = None,
) -> dict[str, Any]:
    """
    Build a compact, source-native summary for an AutoDoctor JSON report without
    flattening unrelated sections into one synthetic table.
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

    root_details = (report or {}).get("RootCauseDetails") or {}
    metric_states = ensure_list(root_details.get("MetricStates"))
    score_breakdown = root_details.get("ScoreBreakdown") or {}
    score_categories = ensure_list(score_breakdown.get("Categories"))
    findings = ensure_list(root_details.get("Findings"))
    trend_window = ((root_details.get("HistoricalAnalysis") or {}).get("TrendWindow")) or {}

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
        grouped_findings.setdefault(map_domain(finding.get("Category")), []).append(finding)

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

    summary = {
        "analysis_profile": "autodoctor",
        "source_type": "json",
        "section_count": len(report or {}),
        "matched_sections": sorted(report.keys()) if isinstance(report, dict) else [],
        "host_name": _pick_host_name(report),
        "generated_time": (
            (remediation.get("Timestamp") or {}).get("value")
            if isinstance(remediation.get("Timestamp"), dict)
            else remediation.get("Timestamp")
        ),
        "health": {
            "numeric": ((report or {}).get("HealthScore") or {}).get("Numeric"),
            "display": ((report or {}).get("HealthScore") or {}).get("Display"),
            "summary": (report or {}).get("RootCauseAnalysis"),
            "main_concern": _build_main_concern(metric_states, primary_driver),
        },
    }

    if "overview" in sections:
        summary["overview"] = {
            "windows_product": system_info.get("WindowsProductName"),
            "windows_version": system_info.get("WindowsVersion"),
            "architecture": system_info.get("OsArchitecture"),
            "uptime_days": (report.get("SystemUptime") or {}).get("UptimeDays"),
            "runtime_seconds": (report.get("ExecutionStats") or {}).get("ScriptRuntimeSeconds"),
        }

    if "system" in sections:
        disk_usage = ensure_list(disk.get("Usage"))
        fullest_disk = None
        if disk_usage:
            fullest_disk = max(
                (
                    {
                        "name": item.get("Name"),
                        "free_gb": item.get("FreeGB"),
                        "used_gb": item.get("UsedGB"),
                    }
                    for item in disk_usage
                    if isinstance(item, dict)
                ),
                key=lambda item: float(item.get("used_gb") or 0),
                default=None,
            )

        summary["system"] = {
            "cpu_load_percent": ((cpu.get("LoadStatus") or {}).get("CurrentCPULoadPercent")),
            "memory_free_gb": memory.get("FreeGB"),
            "memory_total_gb": memory.get("TotalGB"),
            "memory_used_percent": memory.get("UsedPercent"),
            "network_latency_ms": ((network.get("Connectivity") or {}).get("AvgLatencyMS")),
            "network_status": ((network.get("Connectivity") or {}).get("Status")),
            "fullest_disk": fullest_disk,
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
                for finding in ensure_list(primary_driver.get("Findings") if primary_driver else [])[:top_n]
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
            "baseline_deviations": ensure_list(root_details.get("BaselineDeviations"))[:top_n],
        }

    if "remediation" in sections:
        summary["remediation"] = {
            "status": remediation.get("Status"),
            "timestamp": (
                remediation.get("Timestamp", {}).get("value")
                if isinstance(remediation.get("Timestamp"), dict)
                else remediation.get("Timestamp")
            ),
            "restore_point": remediation.get("RestorePoint"),
            "system_repair": remediation.get("SystemRepair"),
            "defender_scan": remediation.get("DefenderScan"),
        }

    if "data_quality" in sections:
        summary["data_quality"] = {
            "detected_issues": ensure_list(root_details.get("DetectedIssues"))[:top_n],
            "validation_issues": ensure_list(root_details.get("ValidationIssues"))[:top_n],
            "software_blank_rows": summary.get("inventory", {}).get("software", {}).get("blank_rows"),
            "software_duplicate_names": summary.get("inventory", {}).get("software", {}).get("duplicate_names"),
            "incomplete_driver_rows": summary.get("inventory", {}).get("drivers", {}).get("incomplete_rows"),
        }

    return summary


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
