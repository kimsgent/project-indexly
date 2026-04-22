from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

from .autodoctor_summary import build_autodoctor_json_summary
from .universal_loader import _safe_read_json_text

console = Console()


def _summary_preview_dataframe(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"section": "identity", "metric": "display", "value": summary.get("identity")},
        {"section": "health", "metric": "numeric", "value": summary.get("health", {}).get("numeric")},
        {"section": "health", "metric": "display", "value": summary.get("health", {}).get("display")},
        {"section": "health", "metric": "main_concern", "value": summary.get("health", {}).get("main_concern")},
        {"section": "overview", "metric": "windows_product", "value": summary.get("overview", {}).get("windows_product")},
        {"section": "overview", "metric": "uptime_days", "value": summary.get("overview", {}).get("uptime_days")},
        {"section": "inventory", "metric": "software_count", "value": summary.get("inventory", {}).get("software", {}).get("count")},
        {"section": "inventory", "metric": "driver_count", "value": summary.get("inventory", {}).get("drivers", {}).get("count")},
    ]
    return pd.DataFrame([row for row in rows if row["value"] is not None])


def render_autodoctor_json_summary(summary: dict[str, Any], *, top_n: int = 5) -> None:
    variant = summary.get("autodoctor_variant") or "report"
    title = (
        "🩺 AutoDoctor Telemetry Summary"
        if variant == "telemetry"
        else "🩺 AutoDoctor Report Summary"
    )
    console.print(f"\n[bold cyan]{title}[/bold cyan]")

    health = summary.get("health", {})
    overview = summary.get("overview", {})
    system = summary.get("system", {})
    findings = summary.get("findings", {})
    inventory = summary.get("inventory", {})
    trends = summary.get("trends", {})
    remediation = summary.get("remediation", {})
    database_sync = summary.get("database_sync", {})

    header = Table(show_header=False, box=None)
    header.add_column("field", style="bold cyan")
    header.add_column("value")
    header.add_row("Identity", str(summary.get("identity") or summary.get("host_name") or "Unknown"))
    header.add_row("Health", str(health.get("display") or health.get("numeric") or "Unknown"))
    header.add_row("Main concern", str(health.get("main_concern") or "Unknown"))
    header.add_row("Root cause", str(health.get("summary") or "No summary available"))
    header.add_row("Generated", str(summary.get("generated_time") or "Unknown"))
    header.add_row("Runtime (s)", str(overview.get("runtime_seconds") or "Unknown"))
    if overview.get("module_success_text"):
        header.add_row("Modules", str(overview.get("module_success_text")))
    if database_sync.get("status"):
        header.add_row("DB sync", str(database_sync.get("status")))
    console.print(header)

    summary_only = bool(summary.get("render_options", {}).get("summary_only"))

    system_table = Table(title="System State", show_lines=False)
    system_table.add_column("Metric")
    system_table.add_column("Value")
    system_table.add_row("Windows", str(overview.get("windows_product") or "Unknown"))
    system_table.add_row("Version", str(overview.get("windows_version") or "Unknown"))
    system_table.add_row("CPU load %", str(system.get("cpu_load_percent") or "Unknown"))
    system_table.add_row("Memory used %", str(system.get("memory_used_percent") or "Unknown"))
    if system.get("network_latency_ms") is not None:
        system_table.add_row("Network latency ms", str(system.get("network_latency_ms")))
    elif system.get("network_status"):
        system_table.add_row("Network", str(system.get("network_status")))
    fullest_disk = system.get("fullest_disk") or {}
    if fullest_disk:
        disk_text = (
            f"{fullest_disk.get('name')} "
            f"(used {fullest_disk.get('used_gb')} GB, free {fullest_disk.get('free_gb')} GB)"
        )
        system_table.add_row("Fullest disk", disk_text)
    console.print(system_table)

    latest_findings = findings.get("latest_findings") or []
    if latest_findings:
        finding_table = Table(title="Dominant Findings", show_lines=False)
        finding_table.add_column("Category")
        finding_table.add_column("Severity")
        finding_table.add_column("Message")
        for finding in latest_findings[:top_n]:
            finding_table.add_row(
                str(finding.get("Category") or "General"),
                str(finding.get("Severity") or "Info"),
                str(finding.get("Message") or ""),
            )
        console.print(finding_table)

    if overview.get("run_id") or overview.get("user") or overview.get("autodoctor_version"):
        execution_table = Table(title="Execution Context", show_lines=False)
        execution_table.add_column("Field")
        execution_table.add_column("Value")
        if overview.get("run_id"):
            execution_table.add_row("Run ID", str(overview.get("run_id")))
        if overview.get("user"):
            execution_table.add_row("User", str(overview.get("user")))
        if overview.get("autodoctor_version"):
            execution_table.add_row("Version", str(overview.get("autodoctor_version")))
        if overview.get("module_count") is not None:
            execution_table.add_row("Module count", str(overview.get("module_count")))
        if overview.get("modules_failed") is not None:
            execution_table.add_row("Modules failed", str(overview.get("modules_failed")))
        console.print(execution_table)

    if database_sync:
        sync_table = Table(title="Database Sync", show_lines=False)
        sync_table.add_column("Field")
        sync_table.add_column("Value")
        sync_table.add_row("Status", str(database_sync.get("status") or "Unknown"))
        sync_table.add_row("Enabled", str(database_sync.get("enabled") or "Unknown"))
        sync_table.add_row(
            "Diagnostics written",
            str(database_sync.get("diagnostics_written") or False),
        )
        sync_table.add_row(
            "Alerts written",
            str(database_sync.get("alerts_written") or False),
        )
        if database_sync.get("last_write"):
            sync_table.add_row("Last write", str(database_sync.get("last_write")))
        if database_sync.get("error"):
            sync_table.add_row("Error", str(database_sync.get("error")))
        console.print(sync_table)

    if summary_only:
        return

    top_processes = system.get("top_processes") or []
    if top_processes:
        process_table = Table(title="Top CPU Processes", show_lines=False)
        process_table.add_column("Process")
        process_table.add_column("CPU")
        for proc in top_processes[:top_n]:
            process_table.add_row(str(proc.get("ProcessName") or "Unknown"), str(proc.get("CPU") or ""))
        console.print(process_table)

    has_report_inventory = any(
        [
            inventory.get("software", {}).get("count"),
            inventory.get("drivers", {}).get("count"),
            inventory.get("startup_program_count"),
            inventory.get("network_adapter_count"),
        ]
    )
    has_telemetry_inventory = inventory.get("module_count") is not None
    if has_report_inventory or has_telemetry_inventory:
        inventory_table = Table(title="Inventory Highlights", show_lines=False)
        inventory_table.add_column("Metric")
        inventory_table.add_column("Value")
        if has_report_inventory:
            inventory_table.add_row(
                "Installed software",
                str(inventory.get("software", {}).get("count") or 0),
            )
            inventory_table.add_row(
                "Software blank rows",
                str(inventory.get("software", {}).get("blank_rows") or 0),
            )
            inventory_table.add_row(
                "Drivers",
                str(inventory.get("drivers", {}).get("count") or 0),
            )
            inventory_table.add_row(
                "Incomplete drivers",
                str(inventory.get("drivers", {}).get("incomplete_rows") or 0),
            )
            inventory_table.add_row(
                "Startup programs",
                str(inventory.get("startup_program_count") or 0),
            )
            inventory_table.add_row(
                "Network adapters",
                str(inventory.get("network_adapter_count") or 0),
            )
        else:
            inventory_table.add_row(
                "Recorded modules",
                str(inventory.get("module_count") or 0),
            )
            inventory_table.add_row(
                "Failed modules",
                str(inventory.get("failed_module_count") or 0),
            )
        console.print(inventory_table)

    trend_window = trends.get("window") or {}
    metric_states = trends.get("metric_states") or []
    if metric_states:
        trend_table = Table(title="Trend Indicators", show_lines=False)
        trend_table.add_column("Metric")
        trend_table.add_column("State")
        trend_table.add_column("Current")
        trend_table.add_column("Baseline")
        for item in metric_states[:top_n]:
            trend_table.add_row(
                str(item.get("Metric") or ""),
                str(item.get("State") or ""),
                str(item.get("Current") or ""),
                str(item.get("Baseline") or ""),
            )
        if trend_window:
            trend_table.caption = (
                f"Window: {trend_window.get('label') or 'n/a'} | "
                f"Fallback: {trend_window.get('used_fallback')}"
            )
        console.print(trend_table)

    if remediation:
        remediation_table = Table(title="Automatic Remediation", show_lines=False)
        remediation_table.add_column("Field")
        remediation_table.add_column("Value")
        remediation_table.add_row("Status", str(remediation.get("status") or "Unknown"))
        remediation_table.add_row("Timestamp", str(remediation.get("timestamp") or "Unknown"))
        remediation_table.add_row("Restore point", str(remediation.get("restore_point") or "Unknown"))
        remediation_table.add_row("System repair", str(remediation.get("system_repair") or "Unknown"))
        remediation_table.add_row("Defender scan", str(remediation.get("defender_scan") or "Unknown"))
        console.print(remediation_table)


def analyze_autodoctor_json_file(
    file_path: Path,
    *,
    raw: dict[str, Any] | None = None,
    args: Any | None = None,
    verbose: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    if raw is None:
        raw_text = _safe_read_json_text(file_path)
        raw = json.loads(raw_text) if raw_text else {}

    section_filter = set(getattr(args, "sections", []) or [])
    summary = build_autodoctor_json_summary(
        raw,
        top_n=int(getattr(args, "top_n", 5) or 5),
        sections=section_filter or None,
    )
    summary["render_options"] = {
        "summary_only": bool(getattr(args, "summary_only", False))
        and not bool(getattr(args, "full", False))
    }
    preview_df = _summary_preview_dataframe(summary)
    summary["source_path"] = str(file_path)

    if verbose and getattr(args, "show_summary", True):
        render_autodoctor_json_summary(summary, top_n=int(getattr(args, "top_n", 5) or 5))

    return preview_df, summary, summary
