"""
Debug tool for indexly database configuration and content.

Usage:
    python -m indexly.debug_tbl                          # ✅ default: debug metadata and file_index tables
    python -m indexly.debug_tbl --show-index              # ✅ show file_index with details (alias now in file_metadata)
    python -m indexly.debug_tbl --show-migrations         # ✅ show all migration history
    python -m indexly.debug_tbl --show-migrations --last 5  # ✅ show last 5 migrations
"""

import os
import json
import sqlite3
import argparse
from rich.console import Console
from rich.table import Table
from rich.json import JSON
from .config import DB_FILE
from .db_utils import connect_db

console = Console()


# =============================================================================
# FILE INDEX DEBUG (joins alias from file_metadata)
# =============================================================================
def debug_file_index_table():
    console.rule("[bold yellow]📁 file_index Debug[/bold yellow]")

    if not os.path.exists(DB_FILE):
        console.print(f"[red]❌ DB not found:[/red] {DB_FILE}")
        return

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Table check
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_index';")
    if not cur.fetchone():
        console.print("[red]❌ file_index table not found.[/red]")
        conn.close()
        return

    # Columns
    console.print("[cyan]📋 Columns:[/cyan]")
    cur.execute("PRAGMA table_info(file_index);")
    cols = [c["name"] for c in cur.fetchall()]
    console.print(", ".join(cols))

    # Row count
    cur.execute("SELECT COUNT(*) AS total FROM file_index;")
    total = cur.fetchone()["total"]
    console.print(f"[green]📊 Total rows:[/green] {total}")

    # Sample entries
    console.print("\n[bold]🔍 Sample entries (with alias):[/bold]")
    try:
        cur.execute(
            """
            SELECT fi.path, fm.alias, fi.tag, fi.modified, substr(fi.content, 1, 100) AS snippet
            FROM file_index fi
            LEFT JOIN file_metadata fm ON fi.path = fm.path
            ORDER BY fi.modified DESC
            LIMIT 5;
            """
        )
        rows = cur.fetchall()
        if not rows:
            console.print("[yellow]⚠️ No entries found.[/yellow]")
        else:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Path", overflow="fold")
            table.add_column("Alias")
            table.add_column("Tag")
            table.add_column("Modified")
            table.add_column("Snippet", overflow="fold")

            for r in rows:
                table.add_row(
                    r["path"] or "",
                    r["alias"] or "",
                    r["tag"] or "",
                    str(r["modified"] or ""),
                    r["snippet"] or "",
                )
            console.print(table)
    except Exception as e:
        console.print(f"[red]⚠️ Query error:[/red] {e}")

    # Alias summary
    console.print("\n[bold cyan]📦 Alias summary (file_metadata)[/bold cyan]")
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total_aliases, COUNT(DISTINCT alias) AS unique_aliases
            FROM file_metadata WHERE alias IS NOT NULL AND alias != '';
            """
        )
        stats = cur.fetchone()
        console.print(
            f"  Total aliases: [green]{stats['total_aliases']}[/green] | "
            f"Unique aliases: [green]{stats['unique_aliases']}[/green]"
        )
    except Exception as e:
        console.print(f"[red]⚠️ Alias stats error:[/red] {e}")

    conn.close()


# =============================================================================
# FILE METADATA + TAGS DEBUG
# =============================================================================
def debug_metadata_table():
    console.rule("[bold yellow]📂 Metadata Debug[/bold yellow]")

    if not os.path.exists(DB_FILE):
        console.print(f"[red]❌ DB not found:[/red] {DB_FILE}")
        return

    size = os.path.getsize(DB_FILE)
    console.print(f"[green]✅ DB:[/green] {DB_FILE} ({size/1024:.2f} KB)")

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r["name"] for r in cur.fetchall()]
    console.print(f"📋 Tables: [cyan]{', '.join(tables) if tables else 'None'}[/cyan]")

    # file_metadata
    if "file_metadata" in tables:
        console.print("\n[bold]🔹 file_metadata columns:[/bold]")
        cur.execute("PRAGMA table_info(file_metadata);")
        console.print(", ".join(c["name"] for c in cur.fetchall()))

        try:
            cur.execute(
                """
                SELECT path, alias, title, author, camera, created,
                       dimensions, format, gps
                FROM file_metadata
                ORDER BY created DESC LIMIT 3;
                """
            )
            rows = cur.fetchall()
            if not rows:
                console.print("[yellow]⚠️ No rows in file_metadata[/yellow]")
            else:
                table = Table(show_header=True, header_style="bold blue")
                table.add_column("Path", overflow="fold")
                table.add_column("Alias")
                table.add_column("Title")
                table.add_column("Author")
                table.add_column("Camera")
                table.add_column("Created")
                for r in rows:
                    table.add_row(
                        r["path"] or "",
                        r["alias"] or "",
                        r["title"] or "",
                        r["author"] or "",
                        r["camera"] or "",
                        str(r["created"] or ""),
                    )
                console.print(table)
        except Exception as e:
            console.print(f"[red]⚠️ Error reading metadata:[/red] {e}")
    else:
        console.print("[red]❌ file_metadata table missing[/red]")

    # file_tags
    if "file_tags" in tables:
        console.print("\n[bold]🏷️ file_tags preview:[/bold]")
        try:
            cur.execute("SELECT path, tags FROM file_tags LIMIT 3;")
            rows = cur.fetchall()
            for r in rows:
                console.print(f"• [green]{r['path']}[/green]: {r['tags']}")
        except Exception as e:
            console.print(f"[red]⚠️ file_tags error:[/red] {e}")
    else:
        console.print("[yellow]⚠️ file_tags table not found[/yellow]")

    conn.close()


# =============================================================================
# MIGRATION HISTORY
# =============================================================================
def show_migrations(db: str | None = None, last: int | None = None):
    db_path = db or DB_FILE
    if not os.path.exists(db_path):
        console.print(f"[red]❌ DB not found:[/red] {db_path}")
        return

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
    )
    if not cur.fetchone():
        console.print("[yellow]⚠️ No schema_migrations table found[/yellow]")
        conn.close()
        return

    query = "SELECT id, migration, applied_at FROM schema_migrations ORDER BY id DESC"
    if last:
        query += f" LIMIT {last}"

    cur.execute(query)
    rows = cur.fetchall()
    rows.reverse()

    if not rows:
        console.print("[yellow]⚠️ No migrations recorded[/yellow]")
    else:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", justify="right")
        table.add_column("Migration")
        table.add_column("Applied At")
        for r in rows:
            table.add_row(str(r["id"]), r["migration"], r["applied_at"])
        console.print(table)

    conn.close()


# =============================================================================
# CLEANED DATA
# =============================================================================
def debug_cleaned_data_table(limit: int = 10):
    """
    Enhanced cleaned_data debug:
    - Works for CSV and JSON sources
    - Handles legacy list-style JSON
    - Uses Rich JSON preview
    """
    from .cleaning.auto_clean import _get_db_connection

    console.rule("[bold yellow]🧹 Cleaned Data Debug[/bold yellow]")
    conn = _get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cleaned_data';"
    )
    if not cur.fetchone():
        console.print("[yellow]⚠️ cleaned_data table not found[/yellow]")
        conn.close()
        return

    # Columns
    cur.execute("PRAGMA table_info(cleaned_data);")
    console.print("📋 Columns:", ", ".join(c["name"] for c in cur.fetchall()))

    # Row count
    cur.execute("SELECT COUNT(*) AS total FROM cleaned_data;")
    console.print(f"📊 Total rows: {cur.fetchone()['total']}")

    # Samples
    cur.execute(
        f"SELECT * FROM cleaned_data ORDER BY cleaned_at DESC LIMIT {limit};"
    )
    for r in cur.fetchall():
        row = dict(r)
        console.print(f"\n[cyan]ID {row.get('id','?')}[/cyan] — {row.get('file_name','—')}")
        console.print(
            f"[dim]Cleaned at {row.get('cleaned_at','—')} | "
            f"Rows:{row.get('row_count','?')} | Cols:{row.get('col_count','?')} | "
            f"Src:{row.get('source_path','unknown')}[/dim]"
        )
        try:
            data = json.loads(row.get("data_json", "{}"))
            if isinstance(data, list):
                preview = data[:5]
            elif isinstance(data, dict):
                preview = (
                    data.get("sample_data")
                    or list(data.get("summary_statistics", {}).items())[:5]
                    or {k: data[k] for k in list(data.keys())[:5]}
                )
            else:
                preview = str(data)[:300]
            console.print(JSON.from_data(preview))
        except Exception as e:
            console.print(f"[red]❌ JSON parse error:[/red] {e}")
        console.rule()

    conn.close()


# =============================================================================
# MAIN CLI HANDLER
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Debug Indexly database tables and migrations"
    )
    parser.add_argument("--show-index", action="store_true",
                        help="Show file_index table with alias stats")
    parser.add_argument("--show-migrations", action="store_true",
                        help="Show migration history")
    parser.add_argument("--last", type=int,
                        help="Limit to last N migrations (requires --show-migrations)")
    parser.add_argument("--show-cleaned", action="store_true",
                        help="Show cleaned_data table entries")

    args = parser.parse_args()

    if args.show_migrations:
        show_migrations(last=args.last)
    elif args.show_index:
        debug_file_index_table()
    elif args.show_cleaned:
        debug_cleaned_data_table()
    else:
        debug_metadata_table()
        debug_file_index_table()
