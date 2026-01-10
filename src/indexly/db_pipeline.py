# src/indexly/db_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import sqlite3
from rich.console import Console

from .datetime_utils import normalize_datetime_columns
from .db_detect import IndexlyDBDetector
from .db_summary_indexly import IndexlySummaryBuilder

console = Console()


def generate_numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return pd.DataFrame()
    stats_list = []
    for col in numeric_cols:
        vals = df[col].dropna()
        q1, q3 = (
            (vals.quantile(0.25), vals.quantile(0.75))
            if not vals.empty
            else (None, None)
        )
        iqr_val = (q3 - q1) if q1 is not None and q3 is not None else None
        stats_list.append(
            {
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
            }
        )
    return pd.DataFrame(stats_list).set_index("column")


def run_db_pipeline(
    db_path: Path, args, raw: dict | None = None, df: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict | None]:
    """
    Analyze an SQLite database file. Auto-select first table if none provided.
    Returns: df, df_stats, table_output, extra (optional)
    """
    db_path = Path(db_path)
    extra: dict | None = None

    if not db_path.exists():
        console.print(f"[red]❌ Database file not found: {db_path}[/red]")
        return pd.DataFrame(), pd.DataFrame(), {}, None

    console.print(f"🔍 Loading SQLITE via loader: [bold]{db_path}[/bold]")

    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to {db_path}: {e}[/red]")
        return pd.DataFrame(), pd.DataFrame(), {}, None

    try:
        # --- Build raw DB info
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

        # --- Detect Indexly DB
        detector = IndexlyDBDetector(raw)
        is_indexly = detector.is_indexly_db()

        if is_indexly:
            builder = IndexlySummaryBuilder(db_path, raw)
            indexly_summary = builder.build()

            table_output = {
                "pretty_text": "Indexly database summary",
                "meta": {
                    "rows": indexly_summary["core"]["total_rows_file_index"],
                    "cols": len(indexly_summary.get("tags", {})),
                },
                "indexly_summary": indexly_summary,
            }

            # Use preview df for numeric stats
            df_preview = pd.read_sql_query(
                "SELECT * FROM file_index LIMIT 1000", conn
            )
            df_stats = generate_numeric_summary(df_preview)

            extra = {"is_indexly_db": True}
            return df_preview, df_stats, table_output, extra

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
        return (
            df,
            pd.DataFrame(),
            {"pretty_text": "Empty table", "meta": {"rows": 0, "cols": 0}},
            None,
        )

    # --- Normalize datetime columns
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="db")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Numeric summary
    df_stats = generate_numeric_summary(df)

    # --- Pretty output for generic table
    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1]), "table": table_name}
    lines = [f"Rows: {meta['rows']}, Columns: {meta['cols']}", "\nColumn overview:"]
    for c in df.columns:
        dtype = str(df[c].dtype)
        n_unique = int(df[c].nunique(dropna=True))
        sample = df[c].dropna().astype(str).head(3).tolist()
        lines.append(f" - {c} : {dtype} | unique={n_unique} | sample={sample}")
    lines.append("\nNumeric summary:")
    lines.append(str(df_stats) if not df_stats.empty else "No numeric columns detected.")

    table_output = {
        "pretty_text": "\n".join(lines),
        "meta": meta,
        "datetime_summary": dt_summary,
    }

    return df, df_stats, table_output, extra
