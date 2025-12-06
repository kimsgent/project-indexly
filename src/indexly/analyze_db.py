#!/usr/bin/env python3
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError
import sqlite3
import json
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from .db_inspector import inspect_db
from .table_profiler import profile_table
from .db_schema_utils import normalize_schema, summarize_schema
from .export_utils import save_json, save_markdown, save_html
from .relation_detector import build_relation_graph
from .table_profiler import _profile_table_worker
from .indexly_detector import build_indexly_block

console = Console()


def _print_unified_table(inspect_res, schema_summary, profiles=None, filter_table: str | None = None):
    """Print unified table overview with rows, columns, PKs, and skipped tables."""
    t = Table(title="DB Tables Overview")
    t.add_column("Table")
    t.add_column("Rows", justify="right")
    t.add_column("Cols", justify="right")
    t.add_column("PK", justify="left")
    t.add_column("Status", justify="left")  # New column to show skipped/failure

    tables = inspect_res["tables"]
    if filter_table:
        tables = [filter_table] if filter_table in tables else []

    for tbl in tables:
        rows = inspect_res.get("counts", {}).get(tbl, 0)
        cols = len(inspect_res.get("schemas", {}).get(tbl, []))
        pk_list = schema_summary.get("tables", {}).get(tbl, {}).get("primary_keys", [])
        pks = ", ".join(pk_list) if pk_list else "-"

        status = "OK"
        if profiles:
            prof = profiles.get(tbl, {})
            if prof.get("skipped"):
                status = "[yellow]SKIPPED[/yellow]"
            elif not prof:
                status = "[red]FAILED[/red]"

        t.add_row(tbl, str(rows), str(cols), pks, status)

    console.print(t)



def analyze_db(args):
    """Entry point for indexly analyze-db with Phase 2 profiler."""

    db_path = args.db_path
    if not Path(db_path).exists():
        console.print(f"[red]Database not found: {db_path}[/red]")
        return

    # --------------------------------------------------------------
    # 1) Inspect DB
    # --------------------------------------------------------------
    inspect_res = inspect_db(db_path)

    normalized_schemas = {
        tbl: normalize_schema(raw_schema, table_name=tbl)
        for tbl, raw_schema in inspect_res["schemas"].items()
    }

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
    # 2) Tables to profile
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
        tables_to_profile = (
            [inspect_res["tables"][0]] if inspect_res["tables"] else []
        )

    # --------------------------------------------------------------
    # 3) Profile tables using Phase 2 profiler (parallel + timeout)
    # --------------------------------------------------------------
    profiles = {}
    table_warnings: dict[str, str] = {}
    timeout_sec = getattr(args, "timeout", 300)  # default 5 min per table
    max_workers = getattr(args, "max_workers", os.cpu_count())

    if getattr(args, "parallel", False) and len(tables_to_profile) > 1:


        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _profile_table_worker,
                    db_path,
                    tbl,
                    args.sample_size,
                    True,  # full_stats
                    getattr(args, "fast_mode", False),
                ): tbl
                for tbl in tables_to_profile
            }

            for future in as_completed(futures):
                tbl = futures[future]
                try:
                    tbl, result = future.result(timeout=timeout_sec)
                    profiles[tbl] = result
                except TimeoutError:
                    warning = f"Profiling timed out after {timeout_sec}s"
                    console.print(f"[yellow]⚠ {tbl}: {warning}[/yellow]")
                    profiles[tbl] = {}
                    table_warnings[tbl] = warning
                except Exception as e:
                    warning = f"Profiling failed: {e}"
                    console.print(f"[red]⚠ {tbl}: {warning}[/red]")
                    profiles[tbl] = {}
                    table_warnings[tbl] = warning
    else:
        for tbl in tables_to_profile:
            try:
                profiles[tbl] = profile_table(
                    db_path,
                    tbl,
                    sample_size=args.sample_size,
                    full_stats=True,
                    fast_mode=getattr(args, "fast_mode", False),
                )
            except Exception as e:
                warning = f"Profiling failed: {e}"
                console.print(f"[red]⚠ {tbl}: {warning}[/red]")
                profiles[tbl] = {}
                table_warnings[tbl] = warning

    # --------------------------------------------------------------
    # 4) Global + indexly summary
    # --------------------------------------------------------------

    # Initialize warnings list
    warnings: list[str] = []

    # Merge table-specific warnings into profiles and global warnings
    for tbl, w in table_warnings.items():
        profiles.setdefault(tbl, {})["warning"] = w
        warnings.append(f"{tbl}: {w}")

    # Add generic database warnings
    if not inspect_res.get("tables"):
        warnings.append("No tables discovered in database.")
    if not inspect_res.get("counts", {}):
        warnings.append("Row counts missing; using profile-based estimates where available.")

    counts = inspect_res.get("counts", {}) or {}
    row_estimates = {
        tbl: int(counts.get(tbl) or profiles.get(tbl, {}).get("rows") or 0)
        for tbl in inspect_res.get("tables", [])
    }

    total_rows = sum(row_estimates.values())
    largest_table = (
        max(row_estimates.items(), key=lambda x: x[1]) if row_estimates else None
    )

    if total_rows > 5_000_000:
        warnings.append(
            f"Database appears large (≈{total_rows} rows). Consider --sample-size or --fast."
        )

    global_block = {
        "db_path": str(inspect_res["path"]),
        "db_size_bytes": inspect_res.get("db_size_bytes"),
        "table_count": len(inspect_res.get("tables", [])),
        "total_rows_estimated": int(total_rows),
        "largest_table": (
            {"name": largest_table[0], "rows": int(largest_table[1])}
            if largest_table
            else None
        ),
        "warnings": warnings,
    }

    conn = sqlite3.connect(db_path)
    try:
        indexly_block = build_indexly_block(conn, normalized_schemas).get("indexly", {})
    finally:
        conn.close()

    summary = {
        "meta": {
            "db_path": str(inspect_res["path"]),
            "db_size_bytes": inspect_res.get("db_size_bytes"),
            "tables": inspect_res["tables"],
        },
        "global": global_block,
        "schemas": normalized_schemas,
        "schema_summary": schema_summary,
        "relations": schema_summary.get("relations"),
        "adjacency_graph": adj_graph,
        "counts": counts,
        "row_estimates": row_estimates,
        "profiles": profiles,
        "indexly": indexly_block,
        "visual": {},
        "warnings": warnings,
    }


    # --------------------------------------------------------------
    # 5) Persist output
    # --------------------------------------------------------------
    if not args.no_persist and args.persist_level != "none":
        out_base = Path(db_path)
        saved = save_json(summary, out_base)
        console.print(f"[green]✔ Persisted summary to {saved}[/green]")

    # --------------------------------------------------------------
    # 6) Terminal preview
    # --------------------------------------------------------------
    if args.show_summary:
        console.print()
        console.rule("[bold]Dataset Summary Preview")
        _print_unified_table(inspect_res, schema_summary)

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

        # Sample rows
        if tables_to_profile:
            first_tbl = tables_to_profile[0]
            try:
                import pandas as pd
                conn = sqlite3.connect(db_path)
                preview = pd.read_sql_query(
                    f"SELECT * FROM '{first_tbl}' LIMIT 10", conn
                )
                conn.close()
                console.print("\n[bold]📊 Sample Rows[/bold]")
                console.print(preview)
            except Exception:
                pass

        # Print profiles
        for tbl, prof in profiles.items():
            t = Table(title=f"Profile: {tbl}", show_lines=False)
            t.add_column("Metric")
            t.add_column("Value")

            t.add_row("rows", str(prof.get("rows")))
            t.add_row("cols", str(len(prof.get("columns", []))))
            t.add_row("key_hints", ", ".join(prof.get("key_hints", [])))

            for col, stats in prof.get("numeric_summary", {}).items():
                for k, v in stats.items():
                    t.add_row(f"{col} ({k})", str(v))

            for col, info in prof.get("non_numeric", {}).items():
                for k, v in info.items():
                    t.add_row(f"{col} ({k})", str(v))

            console.print(t)

    # --------------------------------------------------------------
    # 7) Export
    # --------------------------------------------------------------
    out_base = Path(args.db_path)

    if args.export == "json":
        saved = save_json(summary, out_base)
        console.print(f"[green]Exported JSON → {saved}[/green]")

    elif args.export == "md":
        saved = save_markdown(
            summary,
            out_base,
            include_diagram=(getattr(args, "diagram", None) == "mermaid"),
        )
        console.print(f"[green]Exported Markdown → {saved}[/green]")

    elif args.export == "html":
        saved = save_html(
            summary,
            out_base,
            include_diagram=(getattr(args, "diagram", None) == "mermaid"),
        )
        console.print(f"[green]Exported HTML → {saved}[/green]")
