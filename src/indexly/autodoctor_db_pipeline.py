from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

from .autodoctor_summary import build_autodoctor_db_summary

console = Console()


def _query_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def _query_all(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _build_preview_df(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"section": "health", "metric": "numeric", "value": summary.get("health", {}).get("numeric")},
        {"section": "health", "metric": "summary", "value": summary.get("health", {}).get("summary")},
        {"section": "system", "metric": "hostname", "value": summary.get("system", {}).get("hostname")},
        {"section": "system", "metric": "cpu_load_percent", "value": summary.get("system", {}).get("cpu_load_percent")},
        {"section": "system", "metric": "memory_free_gb", "value": summary.get("system", {}).get("memory_free_gb")},
        {"section": "system", "metric": "disk_free_gb", "value": summary.get("system", {}).get("disk_free_gb")},
    ]
    return pd.DataFrame([row for row in rows if row["value"] is not None])


def render_autodoctor_db_summary(summary: dict[str, Any], *, top_n: int = 5) -> None:
    console.print("\n[bold cyan]🩺 AutoDoctor Database Summary[/bold cyan]")
    summary_only = bool(summary.get("render_options", {}).get("summary_only"))

    header = Table(show_header=False, box=None)
    header.add_column("field", style="bold cyan")
    header.add_column("value")
    header.add_row("Hostname", str(summary.get("system", {}).get("hostname") or "Unknown"))
    header.add_row("Health score", str(summary.get("health", {}).get("numeric") or "Unknown"))
    header.add_row("Root cause", str(summary.get("health", {}).get("summary") or "Unknown"))
    header.add_row("Latest run", str(summary.get("health", {}).get("timestamp") or summary.get("system", {}).get("timestamp") or "Unknown"))
    console.print(header)

    system_table = Table(title="Latest System Snapshot", show_lines=False)
    system_table.add_column("Metric")
    system_table.add_column("Value")
    system_table.add_row("CPU load %", str(summary.get("system", {}).get("cpu_load_percent") or "Unknown"))
    system_table.add_row("Memory free GB", str(summary.get("system", {}).get("memory_free_gb") or "Unknown"))
    system_table.add_row("Disk free GB", str(summary.get("system", {}).get("disk_free_gb") or "Unknown"))
    system_table.add_row("Network latency ms", str(summary.get("system", {}).get("network_latency_ms") or "Unknown"))
    console.print(system_table)

    alerts = summary.get("findings", {}).get("alert_summary") or []
    if alerts:
        alert_table = Table(title="Alert Summary", show_lines=False)
        alert_table.add_column("Severity")
        alert_table.add_column("Count")
        for item in alerts[:top_n]:
            alert_table.add_row(str(item.get("severity") or "Unknown"), str(item.get("count") or 0))
        console.print(alert_table)

    if summary_only:
        return

    module_status = summary.get("modules", {}).get("status") or []
    if module_status:
        module_table = Table(title="Module Status", show_lines=False)
        module_table.add_column("Module")
        module_table.add_column("Success")
        module_table.add_column("Failed")
        for item in module_status[:top_n]:
            module_table.add_row(
                str(item.get("module_name") or "Unknown"),
                str(item.get("success") or 0),
                str(item.get("failed") or 0),
            )
        console.print(module_table)

    baselines = summary.get("trends", {}).get("baselines") or []
    if baselines:
        baseline_table = Table(title="Metric Baselines", show_lines=False)
        baseline_table.add_column("Metric")
        baseline_table.add_column("Avg")
        baseline_table.add_column("Min")
        baseline_table.add_column("Max")
        baseline_table.add_column("Samples")
        for item in baselines[:top_n]:
            baseline_table.add_row(
                str(item.get("metric") or "Unknown"),
                str(item.get("avg_value") or "Unknown"),
                str(item.get("min_value") or "Unknown"),
                str(item.get("max_value") or "Unknown"),
                str(item.get("sample_count") or 0),
            )
        console.print(baseline_table)

    remediation = summary.get("remediation") or {}
    if remediation:
        remediation_table = Table(title="Remediation", show_lines=False)
        remediation_table.add_column("Field")
        remediation_table.add_column("Value")
        remediation_table.add_row("Status", str(remediation.get("status") or "Unknown"))
        remediation_table.add_row("Timestamp", str(remediation.get("timestamp") or "Unknown"))
        console.print(remediation_table)


def analyze_autodoctor_db_file(
    db_path: Path,
    *,
    args: Any | None = None,
    verbose: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    history_limit = int(getattr(args, "history_limit", 100) or 100)
    top_n = int(getattr(args, "top_n", 5) or 5)

    conn = sqlite3.connect(db_path)
    try:
        latest_system = _query_one(
            conn,
            """
            SELECT hostname, cpu_load, memory_free_gb, disk_free_gb, network_latency_ms, timestamp
            FROM system_info
            ORDER BY timestamp DESC
            LIMIT 1
            """,
        )
        alert_summary = _query_all(
            conn,
            """
            SELECT severity, COUNT(*) AS count
            FROM alerts
            GROUP BY severity
            ORDER BY count DESC
            """,
        )
        module_status = _query_all(
            conn,
            """
            SELECT module_name,
                   SUM(CASE WHEN status='Success' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN status!='Success' THEN 1 ELSE 0 END) AS failed
            FROM telemetry_modules
            GROUP BY module_name
            ORDER BY failed DESC, success DESC, module_name ASC
            """,
        )
        health_trend = _query_all(
            conn,
            f"""
            SELECT timestamp, health_score
            FROM diagnostics
            WHERE health_score IS NOT NULL
              AND module_name = 'Root Cause Analysis'
            ORDER BY timestamp ASC
            LIMIT {history_limit}
            """,
        )
        baselines = _query_all(
            conn,
            """
            SELECT hostname, metric, window_hours, sample_count, avg_value, min_value, max_value, stddev, updated_at
            FROM telemetry_baselines
            ORDER BY updated_at DESC
            """,
        )
        remediation_status = _query_one(
            conn,
            """
            SELECT status, timestamp
            FROM remediation
            ORDER BY timestamp DESC
            LIMIT 1
            """,
        )
        latest_root_cause = _query_one(
            conn,
            """
            SELECT hostname, health_score, summary, timestamp
            FROM diagnostics
            WHERE module_name = 'Root Cause Analysis'
            ORDER BY timestamp DESC
            LIMIT 1
            """,
        )
    finally:
        conn.close()

    summary = build_autodoctor_db_summary(
        latest_system=latest_system,
        alert_summary=alert_summary,
        module_status=module_status,
        health_trend=health_trend,
        remediation_status=remediation_status,
        baselines=baselines,
        latest_root_cause=latest_root_cause,
        top_n=top_n,
    )
    summary["render_options"] = {
        "summary_only": bool(getattr(args, "summary_only", False))
        and not bool(getattr(args, "full", False))
    }
    summary["source_path"] = str(db_path)
    preview_df = _build_preview_df(summary)

    if verbose and getattr(args, "show_summary", True):
        render_autodoctor_db_summary(summary, top_n=top_n)

    return preview_df, summary, summary
