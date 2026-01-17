# read_indexly_json_summary_v5.py - COMPLETE VERSION
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()


# ---------------- JSON Loader ----------------
def load_indexly_json(file_path: str | Path) -> dict:
    file_path = Path(file_path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(file_path)
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------- Human-readable size ----------------
def _human_readable_size(n_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


# ---------------- DB-style JSON Detection ----------------
def _is_db_style_json(obj: dict) -> bool:
    return isinstance(obj, dict) and {"global", "schemas", "meta"}.issubset(obj.keys())


# ---------------- Schema Analyzer ----------------
def _summarize_schemas(schemas: Dict[str, List[Dict]]) -> None:
    console.print("\n[bold]🔹 Detailed Schema[/bold]")

    console.print("\n[italic]Column Types by Table[/italic]")
    table1 = Table(show_header=True, header_style="bold cyan")
    table1.add_column("Table", style="magenta", no_wrap=True)
    table1.add_column("Total")
    table1.add_column("PK")
    table1.add_column("INTEGER")
    table1.add_column("NVARCHAR")
    table1.add_column("Nullable")

    for tname, cols in sorted(schemas.items()):
        total = len(cols)
        pks = sum(1 for col in cols if col.get("primary_key"))
        integer = sum(1 for col in cols if "INTEGER" in col.get("type", ""))
        nvarchar = sum(1 for col in cols if "NVARCHAR" in col.get("type", ""))
        nullable = sum(1 for col in cols if not col.get("not_null"))
        table1.add_row(
            tname, str(total), str(pks), str(integer), str(nvarchar), str(nullable)
        )
    console.print(table1)

    console.print("\n[italic]Likely Foreign Key Columns[/italic]")
    table2 = Table(show_header=True, header_style="bold green")
    table2.add_column("Table", style="cyan")
    table2.add_column("Column")
    table2.add_column("Type")
    table2.add_column("Nullable")

    fk_candidates = []
    for tname, cols in schemas.items():
        for col in cols:
            col_name = col.get("name", "")
            if col_name.endswith("Id") and not col.get("primary_key"):
                fk_candidates.append(
                    (
                        tname,
                        col_name,
                        col.get("type", "?"),
                        "Yes" if not col.get("not_null") else "No",
                    )
                )
    for tname, col, typ, nullable in sorted(fk_candidates)[:12]:
        table2.add_row(tname, col, typ, nullable)
    console.print(table2)


# ---------------- Sample Data Preview ----------------
def _preview_sample_data(
    schemas: Dict[str, List[Dict]], counts: Dict, preview: int = 3
):
    console.print("\n[bold]🔹 Sample Data Preview[/bold]")

    console.print("\n[italic]Top Tables by Size[/italic]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Table", style="cyan")
    table.add_column("Rows")
    table.add_column("Sample Columns")
    table.add_column("Data Preview")

    table_data = []
    for tname, row_count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        if tname in schemas:
            cols = schemas[tname]
            sample_cols = []
            pk_col = next((c["name"] for c in cols if c.get("primary_key")), None)
            if pk_col:
                sample_cols.append(pk_col)

            text_cols = [c for c in cols if "NVARCHAR" in c.get("type", "")]
            num_cols = [
                c
                for c in cols
                if "INTEGER" in c.get("type", "") or "NUMERIC" in c.get("type", "")
            ]
            if text_cols:
                sample_cols.append(text_cols[0]["name"])
            if num_cols and len(sample_cols) < 3:
                sample_cols.append(num_cols[0]["name"])

            col_names = ", ".join(sample_cols[:3])
            preview_str = f"{row_count} rows × {len(cols)} cols"
            table_data.append((tname, row_count, col_names, preview_str))

    for tname, rows, cols, preview in table_data[:8]:
        table.add_row(tname, str(rows), cols, preview)
    console.print(table)

    console.print("\n[italic]Business Entities[/italic]")
    entities = {
        "customers": f"📧 {counts.get('customers', '?')} customers",
        "employees": f"👥 {counts.get('employees', '?')} employees",
        "invoices": f"💰 {counts.get('invoices', '?')} invoices",
        "tracks": f"🎵 {counts.get('tracks', '?')} tracks",
        "albums": f"💿 {counts.get('albums', '?')} albums",
    }
    for entity, desc in entities.items():
        console.print(f"  {desc}")


# ---------------- Full Summary Renderer ----------------
def summarize_indexly_json(data: dict, preview: int = 3):
    console.print("\n[bold]🔹 Global Info[/bold]")
    global_info = data.get("global", {})
    console.print(f"- DB Path: {global_info.get('db_path', 'unknown')}")
    console.print(
        f"- DB Size: {_human_readable_size(int(global_info.get('db_size_bytes', 0)))}"
    )
    console.print(f"- Tables: {global_info.get('table_count', 'unknown')}")
    console.print(f"- Total Rows: {global_info.get('total_rows_estimated', 'unknown')}")

    console.print("\n[bold]🔹 Tables & Schema[/bold]")
    schema_summary = data.get("schema_summary", {}).get("tables", {})
    counts = data.get("counts", {})
    table = Table(show_header=True, header_style="bold green")
    table.add_column("Table")
    table.add_column("Columns")
    table.add_column("Primary Keys")
    table.add_column("Rows")
    for tname in sorted(schema_summary.keys() or counts.keys()):
        meta = schema_summary.get(tname, {})
        cols = meta.get("columns", "?")
        pk_list = meta.get("primary_keys", [])
        pk_str = ", ".join(pk_list) if isinstance(pk_list, list) else str(pk_list or "")
        row_count = counts.get(tname, "?")
        table.add_row(tname, str(cols), pk_str, str(row_count))
    console.print(table)

    schemas = data.get("schemas", {})
    if schemas:
        _summarize_schemas(schemas)
        _preview_sample_data(schemas, counts, preview)

    profiles = data.get("profiles", {})
    if profiles:
        console.print("\n[bold]🔹 Column Profiles[/bold]")
        for tname, prof in profiles.items():
            console.print(f"\n[cyan]{tname}[/cyan]")
            numeric = prof.get("numeric_summary", {})
            for col, stats in numeric.items():
                stats_str = ", ".join(
                    f"{k}={v:.1f}" if isinstance(v, float) else f"{k}={v}"
                    for k, v in stats.items()
                    if k != "is_numeric"
                )
                console.print(f"  - {col}: {stats_str}")
            non_numeric = prof.get("non_numeric", {})
            for col, info in non_numeric.items():
                unique = info.get("unique", "?")
                nulls = info.get("nulls", "?")
                sample = (
                    info.get("sample", ["-"])[0][:40] + "..."
                    if info.get("sample")
                    else "-"
                )
                console.print(
                    f"  - {col}: unique={unique}, nulls={nulls}, sample={sample}"
                )
    else:
        console.print("\n[bold yellow]⚠️ No detailed profiles available[/bold yellow]")


# ---------------- Optional Tree Viewer ----------------
def build_tree(obj, name="root") -> Tree:
    node = Tree(f"[bold]{name}[/bold]")

    def _walk(o, n):
        if isinstance(o, dict):
            for k, v in o.items():
                _walk(v, n.add(f"[cyan]{k}[/cyan]"))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                _walk(v, n.add(f"[green][{i}][/green]"))
        else:
            n.add(f"[white]{o}[/white]")

    _walk(obj, node)
    return node


def render_tree(obj):
    console.print("\n🌳 [bold cyan]JSON Structure[/bold cyan]")
    console.print(build_tree(obj))


# ---------------- Main Reader ----------------
def read_indexly_json(
    file_path: str | Path,
    treeview: bool = False,
    preview: int = 3,
    show_summary: bool = True,
):
    try:
        data = load_indexly_json(file_path)
    except FileNotFoundError as e:
        print(
            f"❌ Error: JSON file not found: {e}\n"
            f"👉 Hint: Check the path or run the analysis command first."
        )
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(
            f"❌ Error: Invalid JSON format in file: {file_path}\n" f"👉 Details: {e}"
        )
        sys.exit(1)

    db_mode = _is_db_style_json(data)
    if db_mode and show_summary:
        summarize_indexly_json(data, preview=preview)
    if treeview:
        render_tree(data)
    return data
