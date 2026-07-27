# src/indexly/migration_manager.py
import os
import time
import sqlite3
import logging
from rich.console import Console
from typing import Optional
from .config import BASE_DIR, DB_FILE
from .db_update import (
    FILE_INDEX_FTS_SPEC,
    FTS5RebuildError,
    _rebuild_fts5_table,
    inspect_fts5_definition,
)

logger = logging.getLogger(".migrate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

console = Console()

# Expected FTS definition
EXPECTED_SCHEMA = {
    "file_index": {
        "fts5": True,
        "columns": list(FILE_INDEX_FTS_SPEC.columns),
        "prefix": " ".join(str(value) for value in FILE_INDEX_FTS_SPEC.prefix),
        "tokenize": " ".join(FILE_INDEX_FTS_SPEC.tokenizer),
    },
    "file_index_vocab": {
        "fts5vocab": True,  # special marker to create fts5vocab table
        "source": "file_index",
        "mode": "row",
    },
    "file_tags": {
        "columns": ["path TEXT PRIMARY KEY", "tags TEXT"],
    },
    "file_metadata": {
        "columns": [
            "path TEXT PRIMARY KEY",
            "title TEXT",
            "author TEXT",
            "subject TEXT",
            "created TEXT",
            "last_modified TEXT",
            "last_modified_by TEXT",
            "alias TEXT",
            "camera TEXT",
            "image_created TEXT",
            "dimensions TEXT",
            "format TEXT",
            "gps TEXT",
            "metadata TEXT"
        ]
    },
}

def resolve_db_path(db_path: str | None) -> str:
    if not db_path:
        return DB_FILE
    if os.path.isabs(db_path):
        return db_path
    # make it relative to BASE_DIR
    return os.path.join(BASE_DIR, db_path)

# ----------------- helpers -----------------
def backup_database(db_path: str) -> Optional[str]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.bak_{ts}"
    source = sqlite3.connect(db_path)
    backup = sqlite3.connect(backup_path)
    try:
        source.backup(backup)
        result = backup.execute("PRAGMA integrity_check").fetchall()
        if not result or any(row[0] != "ok" for row in result):
            raise FTS5RebuildError("migration backup failed integrity verification")
    finally:
        backup.close()
        source.close()
    logger.info(f"📦 Backup created: {backup_path}")
    return backup_path

def _normalize_prefix(pref) -> str:
    if pref is None:
        return ""
    if isinstance(pref, (list, tuple)):
        return " ".join(str(int(x)) for x in pref)
    return " ".join(p for p in str(pref).replace(",", " ").split() if p.strip())

# ----------------- migration history -----------------
def ensure_migration_history(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    console.print("[green]✅ Migration history table ensured[/green]")


def record_migration(conn: sqlite3.Connection, migration_name: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO schema_migrations (migration) VALUES (?)", (migration_name,))
    conn.commit()
    console.print(f"[green]📜 Recorded migration:[/green] {migration_name}")


def backfill_migrations(conn: sqlite3.Connection):
    """Fill migration history with baseline entries if missing."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM schema_migrations")
    count = cur.fetchone()[0]
    if count > 0:
        console.print(f"[cyan]ℹ️ Migration history already populated ({count} rows)[/cyan]")
        return

    baseline = [
        "baseline_file_index",
        "baseline_file_index_vocab",
        "baseline_file_tags",
        "baseline_file_metadata",
    ]
    for m in baseline:
        cur.execute("INSERT INTO schema_migrations (migration) VALUES (?)", (m,))
        console.print(f"[green]📜 Backfilled migration:[/green] {m}")
    conn.commit()


def list_migrations(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT id, migration, applied_at FROM schema_migrations ORDER BY id")
    return cur.fetchall()


def last_migration(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT migration, applied_at FROM schema_migrations ORDER BY id DESC LIMIT 1")
    return cur.fetchone()


def migration_applied(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM schema_migrations WHERE migration=?", (name,))
    return cur.fetchone() is not None


# ----------------- FTS rebuild -----------------
def rebuild_fts5(conn: sqlite3.Connection, spec: dict, dry_run: bool = False):
    pref_str = _normalize_prefix(spec.get("prefix"))

    console.print(f"[bold cyan]🔁 Preparing to rebuild FTS5 table 'file_index' with prefix='{pref_str}'[/bold cyan]")

    if dry_run:
        console.print(
            "[yellow][DRY-RUN][/yellow] Would run the verified, "
            "snapshot-backed file_index rebuild"
        )
        return

    result = _rebuild_fts5_table(conn, "file_index")
    console.print(
        "[green]✅ Rebuilt and verified FTS5 table file_index "
        f"({result.rows_preserved} rows, generation {result.generation})[/green]"
    )
    record_migration(conn, "rebuild_file_index_with_prefix")


# ----------------- ensure functions -----------------
def ensure_fts5(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    allow_fts_rebuild: bool = False,
):
    spec = EXPECTED_SCHEMA["file_index"]
    desired_pref = _normalize_prefix(spec.get("prefix"))
    tokenize = spec.get("tokenize", "porter")
    cur = conn.cursor()

    cur.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','view') AND name='file_index'")
    row = cur.fetchone()
    if not row:
        if dry_run:
            console.print(f"[yellow][DRY-RUN][/yellow] Would CREATE virtual table file_index with prefix '{desired_pref}'")
        else:
            pref_clause = f", prefix='{desired_pref}'" if desired_pref else ""
            cur.execute(
                f"CREATE VIRTUAL TABLE file_index USING fts5({', '.join(spec['columns'])}, tokenize='{tokenize}'{pref_clause});"
            )
            conn.commit()
            console.print("[green]✅ Created missing FTS5 file_index[/green]")
            record_migration(conn, "create_file_index")
    else:
        create_sql = row[0] or ""
        inspection = inspect_fts5_definition(create_sql)
        if inspection.state == "uninspectable":
            raise FTS5RebuildError(
                f"refusing uninspectable file_index definition: {inspection.reason}"
            )
        if inspection.state == "drift":
            console.print(
                "[yellow]⚠️ Semantic FTS5 definition drift detected in "
                f"file_index ({inspection.reason})[/yellow]"
            )
            if allow_fts_rebuild:
                rebuild_fts5(conn, spec, dry_run=dry_run)
            else:
                console.print(
                    "[yellow]⏭️ FTS5 rebuild not authorized. Use "
                    "`indexly doctor --fix-db --rebuild-fts` for explicit repair."
                    "[/yellow]"
                )
        else:
            console.print("[green]✅ file_index semantic definition OK[/green]")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_index_vocab'")
    if not cur.fetchone():
        if dry_run:
            console.print("[yellow][DRY-RUN][/yellow] Would CREATE file_index_vocab USING fts5vocab(file_index,'row')")
        else:
            cur.execute("CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row');")
            conn.commit()
            console.print("[green]✅ Created file_index_vocab[/green]")
            record_migration(conn, "create_file_index_vocab")


def ensure_normal_tables(conn: sqlite3.Connection, dry_run: bool = False):
    cur = conn.cursor()
    for name, spec in EXPECTED_SCHEMA.items():
        if spec.get("fts5") or spec.get("fts5vocab"):
            continue
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        if not cur.fetchone():
            cols_sql = ", ".join(spec["columns"])
            if dry_run:
                console.print(f"[yellow][DRY-RUN][/yellow] Would CREATE table {name} ({cols_sql})")
            else:
                cur.execute(f"CREATE TABLE {name} ({cols_sql})")
                conn.commit()
                console.print(f"[green]✅ Created missing table {name}[/green]")
                record_migration(conn, f"create_{name}")


# ----------------- run migrations -----------------
def run_migrations(db_path: str, dry_run: bool = False, no_backup: bool = False):
    db_path = resolve_db_path(db_path)
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    console.print(f"[bold cyan]Starting migration:[/bold cyan] db={db_path} dry_run={dry_run} no_backup={no_backup}")
    if not dry_run and not no_backup:
        backup_database(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not dry_run:
            ensure_migration_history(conn)
            backfill_migrations(conn)
        ensure_normal_tables(conn, dry_run=dry_run)
        ensure_fts5(conn, dry_run=dry_run)
        console.print(f"[green]✅ Migration run complete (dry_run={dry_run})[/green]")
    except Exception as e:
        console.print(f"[red]✖ Migration failed:[/red] {e}")
        raise
    finally:
        conn.close()
