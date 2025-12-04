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
from .relation_detector import build_relation_graph


console = Console()


def _print_unified_table(inspect_res, schema_summary, filter_table: str | None = None):
    t = Table(title="DB Tables Overview")
    t.add_column("Table")
    t.add_column("Rows", justify="right")
    t.add_column("Cols", justify="right")
    t.add_column("PK", justify="left")

    tables = inspect_res["tables"]
    if filter_table:
        tables = [filter_table] if filter_table in tables else []

    for tbl in tables:
        rows = inspect_res.get("counts", {}).get(tbl, 0)
        cols = len(inspect_res.get("schemas", {}).get(tbl, []))
        pk_list = schema_summary.get("tables", {}).get(tbl, {}).get("primary_keys", [])
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

    # Normalize schemas with table names for PK heuristics
    normalized_schemas = {
        tbl: normalize_schema(raw_schema, table_name=tbl)
        for tbl, raw_schema in inspect_res["schemas"].items()
    }

    # Summarize schema with relations
    schema_summary = summarize_schema(
        normalized_schemas, db_path, filter_table=args.table
    )
    relations = schema_summary.get("relations", {})
    adj_graph = build_relation_graph(
        relations.get("foreign_keys", []),
        relations.get("heuristics", []),
        relations.get("fts_relations", []),
    )
    # --------------------------------------------------------------
    # 2) Decide which tables to profile
    # --------------------------------------------------------------
    if args.table:
        if args.table not in inspect_res["tables"]:
            console.print(
                f"[yellow]Table '{args.table}' not found. Available: {inspect_res['tables']}[/yellow]"
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
    # 4) Unified Summary
    # --------------------------------------------------------------
    summary = {
        "meta": {
            "db_path": str(inspect_res["path"]),
            "db_size_bytes": inspect_res.get("db_size_bytes"),
            "tables": inspect_res["tables"],
        },
        "schemas": normalized_schemas,  # <- pass dict, not function
        "schema_summary": schema_summary,
        "relations": schema_summary.get("relations"),
        "adjacency_graph": adj_graph,
        "counts": inspect_res.get("counts", {}),
        "profiles": profiles,
    }

    # --------------------------------------------------------------
    # 5) Persist
    # --------------------------------------------------------------
    if not args.no_persist and args.persist_level != "none":
        out_base = Path(db_path)
        saved = save_json(summary, out_base)
        console.print(f"[green]✔ Persisted summary to {saved}[/green]")

    # --------------------------------------------------------------
    # 6) Show summary to terminal
    # --------------------------------------------------------------
    if args.show_summary:
        console.print()
        console.rule("[bold]Dataset Summary Preview")
        _print_unified_table(inspect_res, schema_summary)

        # Relations
        rels = schema_summary.get("relations", {})
        if rels:
            console.print("\n[bold]🔗 Detected Relations[/bold]")

            fk = rels.get("foreign_keys", [])
            if fk:
                t_fk = Table(title="Foreign Keys")
                t_fk.add_column("From")
                t_fk.add_column("→")
                t_fk.add_column("To")
                for r in fk:
                    t_fk.add_row(
                        f"{r['from_table']}.{r['from_column']}",
                        "→",
                        f"{r['to_table']}.{r['to_column']}",
                    )
                console.print(t_fk)

            heur = rels.get("heuristic_relations", [])
            if heur:
                t_h = Table(title="Heuristic Relations")
                t_h.add_column("From")
                t_h.add_column("Possible Target")
                t_h.add_column("Confidence")
                for r in heur:
                    t_h.add_row(
                        f"{r['from_table']}.{r['from_column']}",
                        r["possible_target"],
                        r["confidence"],
                    )
                console.print(t_h)

        # Sample rows preview
        first_tbl = tables_to_profile[0] if tables_to_profile else None
        if first_tbl:
            try:
                from pandas import read_sql_query

                conn = sqlite3.connect(db_path)
                preview = read_sql_query(f"SELECT * FROM '{first_tbl}' LIMIT 10", conn)
                conn.close()
                console.print("\n[bold]📊 Sample Rows[/bold]")
                console.print(preview)
            except Exception:
                pass

        # Table profile metrics
        for tbl, prof in profiles.items():
            t = Table(title=f"Profile: {tbl}", show_lines=False)
            t.add_column("Metric")
            t.add_column("Value")
            t.add_row("rows", str(prof.get("rows")))
            t.add_row("cols", str(len(prof.get("columns", []))))
            t.add_row("key_hints", ", ".join(prof.get("key_hints", [])))
            console.print(t)

    # --------------------------------------------------------------
    # 7) Export
    # --------------------------------------------------------------
    out_base = Path(args.db_path)
    if args.export == "json":
        saved = save_json(summary, out_base)
        console.print(f"[green]Exported JSON -> {saved}[/green]")
    elif args.export == "md":
        saved = save_markdown(
            summary,
            out_base,
            include_diagram=(getattr(args, "diagram", None) == "mermaid"),
        )
        console.print(f"[green]Exported MD -> {saved}[/green]")
    elif args.export == "html":
        saved = save_html(
            summary,
            out_base,
            include_diagram=(getattr(args, "diagram", None) == "mermaid"),
        )
        console.print(f"[green]Exported HTML -> {saved}[/green]")
