#!/usr/bin/env python3
from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

from .db_inspector import inspect_db
from .table_profiler import profile_table
from .db_schema_utils import (
    normalize_schema,
    summarize_schema,
)
from .persist import save_json
from .export_utils import save_json, save_markdown, save_html

console = Console()


def _print_unified_table(inspect_res, schema_summary):
    t = Table(title="DB Tables Overview")
    t.add_column("Table")
    t.add_column("Rows", justify="right")
    t.add_column("Cols", justify="right")
    t.add_column("PK", justify="left")

    for tbl in inspect_res["tables"]:
        rows = inspect_res["counts"].get(tbl)
        cols = len(inspect_res["schemas"].get(tbl, []))
        pk_list = schema_summary.get(tbl, {}).get("primary_keys", [])
        pks = ", ".join(pk_list) if pk_list else "-"
        t.add_row(tbl, str(rows), str(cols), pks)

    console.print(t)


def analyze_db(args):
    """Entry point for indexly analyze-db subcommand."""

    db_path = args.db_path

    if not Path(db_path).exists():
        console.print(f"[red]Database not found: {db_path}[/red]")
        return

    # --------------------------------------------------------------
    # 1) Inspect DB
    # --------------------------------------------------------------
    inspect_res = inspect_db(db_path)

    # Normalize schemas
    normalized_schemas = {
        tbl: normalize_schema(raw_schema)
        for tbl, raw_schema in inspect_res["schemas"].items()
    }

    # Produce schema summary (PKs + relations)
    schema_summary = summarize_schema(normalized_schemas)

    # --------------------------------------------------------------
    # 2) Decide which tables to profile
    # --------------------------------------------------------------
    if args.table:
        if args.table not in inspect_res["tables"]:
            console.print(
                f"[yellow]Table '{args.table}' not found. "
                f"Available: {inspect_res['tables']}[/yellow]"
            )
            return
        tables_to_profile = [args.table]
    elif args.all_tables:
        tables_to_profile = list(inspect_res["tables"])
    else:
        tables_to_profile = [inspect_res["tables"][0]] if inspect_res["tables"] else []

    # --------------------------------------------------------------
    # 3) Profile tables
    # --------------------------------------------------------------
    profiles = {
        tbl: profile_table(db_path, tbl, sample_size=args.sample_size)
        for tbl in tables_to_profile
    }

    # --------------------------------------------------------------
    # 4) Unified Summary (for persist/export)
    # --------------------------------------------------------------
    summary = {
        "meta": {
            "db_path": str(inspect_res["path"]),
            "db_size_bytes": inspect_res.get("db_size_bytes"),
            "tables": inspect_res["tables"],
        },
        "schemas": normalized_schemas,
        "schema_summary": schema_summary,
        "counts": inspect_res.get("counts", {}),
        "profiles": profiles,
    }

    # --------------------------------------------------------------
    # 5) Persist (if enabled)
    # --------------------------------------------------------------
    if not args.no_persist and args.persist_level != "none":
        saved = save_json(summary, db_path)
        console.print(f"[green]✔ Persisted summary to {saved}[/green]")

    # --------------------------------------------------------------
    # 6) Show summary to terminal
    # --------------------------------------------------------------
    if args.show_summary:
        console.print()
        console.rule("[bold]Dataset Summary Preview")

        _print_unified_table(inspect_res, schema_summary)

        # Sample rows preview
        first_tbl = tables_to_profile[0] if tables_to_profile else None
        if first_tbl:
            try:
                from pandas import read_sql_query
                conn = sqlite3.connect(db_path)
                preview = read_sql_query(
                    f"SELECT * FROM '{first_tbl}' LIMIT 10", conn
                )
                conn.close()
                console.print("\n[bold]📊 Sample Rows[/bold]")
                console.print(preview)
            except Exception:
                pass

        # Per-table profile metrics
        for tbl, prof in profiles.items():
            t = Table(title=f"Profile: {tbl}", show_lines=False)
            t.add_column("Metric")
            t.add_column("Value")
            t.add_row("rows", str(prof.get("rows")))
            t.add_row("cols", str(len(prof.get("columns", []))))
            t.add_row("key_hints", ", ".join(prof.get("key_hints", [])))
            console.print(t)

        # ----------------------------------------------------------
        # 7) EXPORT (JSON, MD, HTML)
        # ----------------------------------------------------------
        out_base = Path(args.db_path)

        if args.export == "json":
            saved = save_json(summary, out_base)
            console.print(f"[green]Exported JSON -> {saved}[/green]")

        elif args.export == "md":
            saved = save_markdown(
                summary, 
                out_base, 
                include_diagram=(getattr(args, "diagram", None) == "mermaid")
            )
            console.print(f"[green]Exported MD -> {saved}[/green]")

        elif args.export == "html":
            saved = save_html(
                summary, 
                out_base, 
                include_diagram=(getattr(args, "diagram", None) == "mermaid")
            )
            console.print(f"[green]Exported HTML -> {saved}[/green]")


