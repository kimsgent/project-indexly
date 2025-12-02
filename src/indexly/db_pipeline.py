# src/indexly/db_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import sqlite3
from rich.console import Console
from rich.table import Table

from .datetime_utils import normalize_datetime_columns

console = Console()



def generate_numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return pd.DataFrame()
    stats_list = []
    for col in numeric_cols:
        vals = df[col].dropna()
        q1, q3 = (vals.quantile(0.25), vals.quantile(0.75)) if not vals.empty else (None, None)
        iqr_val = (q3 - q1) if q1 is not None and q3 is not None else None
        stats_list.append({
            "column": col,
            "count": int(vals.count()),
            "nulls": int(df[col].isna().sum()),
            "mean": float(vals.mean()) if not vals.empty else None,
            "median": float(vals.median()) if not vals.empty else None,
            "std": float(vals.std()) if not vals.empty else None,
            "min": float(vals.min()) if not vals.empty else None,
            "max": float(vals.max()) if not vals.empty else None,
            "q1": float(q1) if q1 is not None else None,
            "q3": float(q3) if q3 is not None else None,
            "iqr": float(iqr_val) if iqr_val is not None else None,
        })
    return pd.DataFrame(stats_list).set_index("column")

def summarize_indexly_db(path: Path, raw: dict) -> Tuple[None, None, Dict[str, Any], Dict[str, Any]]:
    """Summarize an Indexly database with limited tag output (top 10)"""
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM file_index;")
    total_docs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM file_metadata;")
    total_meta = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM file_metadata
        WHERE path NOT IN (SELECT path FROM file_index);
    """)
    orphaned = cur.fetchone()[0]

    # Tag distributions: top 10 tags only
    cur.execute("""
        SELECT tags, COUNT(*) AS cnt FROM file_tags
        WHERE tags IS NOT NULL AND tags != ''
        GROUP BY tags
        ORDER BY cnt DESC
        LIMIT 10;
    """)
    tag_rows = cur.fetchall()

    cur.execute("SELECT MIN(modified), MAX(modified) FROM file_index;")
    oldest, newest = cur.fetchone()

    # ----------- PRINT TABLE ----------------
    tbl = Table(title="Indexly DB Summary", show_lines=True)
    tbl.add_column("Metric")
    tbl.add_column("Value")

    tbl.add_row("Indexed files", str(total_docs))
    tbl.add_row("Metadata entries", str(total_meta))
    tbl.add_row("Orphaned metadata", str(orphaned))
    tbl.add_row("Top tag groups", str(len(tag_rows)))
    tbl.add_row("Oldest modification", str(oldest))
    tbl.add_row("Newest modification", str(newest))

    console.print(tbl)

    # ----------- TAG DISTRIBUTION TABLE --------------
    tag_tbl = Table(title="Top 10 Tag Distribution")
    tag_tbl.add_column("Tag")
    tag_tbl.add_column("Count")
    for tag, cnt in tag_rows:
        tag_tbl.add_row(tag or "(untagged)", str(cnt))

    console.print(tag_tbl)
    conn.close()

    extra = {
        "total_docs": total_docs,
        "total_meta": total_meta,
        "orphaned": orphaned,
        "top_tags": tag_rows,
        "oldest_modified": oldest,
        "newest_modified": newest,
    }

    return None, None, {"pretty_text": "Indexly DB summary printed above", "meta": {}}, extra



def run_db_pipeline(
    db_path: Path,
    args,
    raw: dict | None = None,
    df: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict | None]:
    """
    Analyze an SQLite database file. Auto-select first table if none provided.
    Returns: df, df_stats, table_output, extra (optional)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        console.print(f"[red]❌ Database file not found: {db_path}[/red]")
        return pd.DataFrame(), pd.DataFrame(), {}, None

    console.print(f"🔍 Loading SQLITE via loader: [bold]{db_path}[/bold]")

    # --- Connect
    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to {db_path}: {e}[/red]")
        return pd.DataFrame(), pd.DataFrame(), {}, None

    try:
        # --- Raw info
        if raw is None:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row[0] for row in cur.fetchall()]

            schemas = {}
            counts = {}
            for t in tables:
                cur.execute(f"PRAGMA table_info('{t}');")
                schemas[t] = cur.fetchall()
                cur.execute(f"SELECT COUNT(*) FROM '{t}';")
                counts[t] = cur.fetchone()[0]

            raw = {"tables": tables, "schemas": schemas, "counts": counts}

        # Detect Indexly DB
        INDEXLY_REQUIRED = {
            "file_index", "file_metadata", "file_tags",
            "file_index_content", "file_index_idx", "file_index_vocab"
        }

        if raw and INDEXLY_REQUIRED.issubset(set(raw.get("tables", []))):
            # Correctly unpack the tuple returned by summarize_indexly_db
            _, _, _, indexly_extra = summarize_indexly_db(db_path, raw)

            # Prepare table output
            table_output = {
                "pretty_text": "Indexly DB summary printed above",
                "meta": {"rows": indexly_extra["total_docs"], "cols": len(indexly_extra["top_tags"])},
                "indexly_summary": indexly_extra,
            }

            # Use a preview df of 'file_index' for stats
            df_preview = pd.read_sql_query("SELECT * FROM file_index LIMIT 1000", sqlite3.connect(db_path))
            df_stats = generate_numeric_summary(df_preview)

            # Return 4 values to signal Indexly DB
            return df_preview, df_stats, table_output, {"is_indexly_db": True}


        # --- Generic DB fallback
        tables = raw.get("tables", [])
        if not tables:
            console.print(f"[yellow]⚠️ No tables found in {db_path}[/yellow]")
            return pd.DataFrame(), pd.DataFrame(), {}, None

        table_name = getattr(args, "table", None) or tables[0]
        console.print(f"📋 Reading table: [cyan]{table_name}[/cyan]")

        df = pd.read_sql_query(f"SELECT * FROM '{table_name}'", conn)

    except Exception as e:
        console.print(f"[red]❌ Failed to read from {db_path}: {e}[/red]")
        return pd.DataFrame(), pd.DataFrame(), {}, None
    finally:
        conn.close()

    if df.empty:
        console.print(f"[yellow]⚠️ Table '{table_name}' is empty.[/yellow]")
        return df, pd.DataFrame(), {"pretty_text": "Empty table", "meta": {"rows": 0, "cols": 0}}, None

    # --- Normalize datetime columns ---
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="db")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Build numeric summary ---
    df_stats = generate_numeric_summary(df)

    # --- Build pretty output ---
    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1]), "table": table_name}
    lines = [f"Rows: {meta['rows']}, Columns: {meta['cols']}", "\nColumn overview:"]
    for c in df.columns:
        dtype = str(df[c].dtype)
        n_unique = int(df[c].nunique(dropna=True))
        sample = df[c].dropna().astype(str).head(3).tolist()
        lines.append(f" - {c} : {dtype} | unique={n_unique} | sample={sample}")
    lines.append("\nNumeric summary:")
    lines.append(str(df_stats) if not df_stats.empty else "No numeric columns detected.")

    table_output = {"pretty_text": "\n".join(lines), "meta": meta, "datetime_summary": dt_summary}
    return df, df_stats, table_output, None




