# read_indexly_json.py
import json
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
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
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
    if not isinstance(obj, dict):
        return False
    required_keys = {"global", "schemas", "meta"}
    return required_keys.issubset(obj.keys())


# ---------------- Database Summary ----------------
def show_db_summary(data: Dict[str, Any]):
    global_info = data.get("global", {})
    schema_summary = data.get("schema_summary", {})
    table_meta = schema_summary.get("tables", {})
    counts = data.get("counts", {})

    db_path = global_info.get("db_path", "unknown")
    db_size_bytes = int(global_info.get("db_size_bytes", 0))
    db_size_hr = _human_readable_size(db_size_bytes)

    table_count = global_info.get("table_count", len(table_meta) or len(counts))
    total_rows = global_info.get(
        "total_rows_estimated",
        sum(counts.values()) if isinstance(counts, dict) else "unknown",
    )

    largest_table = global_info.get("largest_table", {})
    largest_name = largest_table.get("name", "unknown")
    largest_rows = largest_table.get("rows", "unknown")

    console.print("\n[bold]Database Summary[/bold]")
    console.print(f"DB Path: {db_path}")
    console.print(f"DB Size: {db_size_hr}")
    console.print(f"Tables: {table_count}")
    console.print(f"Total Rows: {total_rows}")
    console.print(f"Largest Table: {largest_name} ({largest_rows} rows)\n")

    console.print("[bold]Table Overview[/bold]")
    table = Table(show_header=True, header_style="bold green")
    table.add_column("Table")
    table.add_column("Columns")
    table.add_column("Primary Keys")
    table.add_column("Rows")

    table_names = list(table_meta.keys()) or list(counts.keys())
    for tname in sorted(table_names):
        meta = table_meta.get(tname, {})
        cols = meta.get("columns", "?")
        pk_list = meta.get("primary_keys", [])
        pk_str = ", ".join(pk_list) if isinstance(pk_list, list) else str(pk_list or "")
        row_count = counts.get(tname, "?")
        table.add_row(tname, str(cols), pk_str, str(row_count))

    console.print(table)
    console.print()


# ---------------- Database Tree ----------------
def build_db_tree(data: Dict[str, Any]) -> Tree:
    global_info = data.get("global", {})
    relations = data.get("relations", {})
    graph = relations.get("graph") or data.get("adjacency_graph") or {}
    foreign_keys = relations.get("foreign_keys", [])

    db_path = global_info.get("db_path", "Database")
    root_label = Path(db_path).name if isinstance(db_path, str) else "Database"
    root = Tree(f"[bold]{root_label}[/bold]")

    fk_by_from_table: Dict[str, List[Dict[str, Any]]] = {}
    for fk in foreign_keys:
        from_table = fk.get("from_table")
        if from_table:
            fk_by_from_table.setdefault(from_table, []).append(fk)

    for tname in sorted(graph.keys()):
        table_node = root.add(f"[cyan]{tname}[/cyan]")
        for fk in fk_by_from_table.get(tname, []):
            table_node.add(f"{fk.get('from_column', '?')} → {fk.get('to_table', '?')}")

    return root


def render_db_tree(data: Dict[str, Any]):
    tree = build_db_tree(data)
    console.print("\n🌳 [bold cyan]Database Tree[/bold cyan]")
    console.print(tree)


# ---------------- Generic Compact Viewer ----------------
def render_compact(obj, max_preview=3, level=0):
    indent = "  " * level
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:max_preview]:
            console.print(f"{indent}- [cyan]{k}[/cyan]: {type(v).__name__}")
            if isinstance(v, (dict, list)):
                render_compact(v, max_preview=max_preview, level=level + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:max_preview]):
            console.print(f"{indent}- [{i}]: {type(v).__name__}")
            if isinstance(v, (dict, list)):
                render_compact(v, max_preview=max_preview, level=level + 1)
    else:
        console.print(f"{indent}- {obj}")


# ---------------- Generic Tree Viewer ----------------
def build_tree(obj, name="root"):
    node = Tree(f"[bold]{name}[/bold]")
    _walk_tree(obj, node)
    return node


def _walk_tree(obj, node):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = node.add(f"[cyan]{k}[/cyan]")
            _walk_tree(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            child = node.add(f"[green][{i}][/green]")
            _walk_tree(v, child)
    else:
        node.add(f"[white]{obj}[/white]")


def render_tree(obj):
    console.print("\n🌳 [bold cyan]JSON Structure[/bold cyan]")
    console.print(build_tree(obj))


# ---------------- Main Reader ----------------
def read_indexly_json(
    file_path: str | Path,
    treeview: bool = False,
    preview: int = 3,
    show_summary: bool = False,
):
    data = load_indexly_json(file_path)
    db_mode = _is_db_style_json(data)

    if db_mode and show_summary:
        if treeview:
            render_db_tree(data)
        show_db_summary(data)
    else:
        if treeview:
            render_tree(data)
        else:
            render_compact(data, max_preview=preview)

    return data
