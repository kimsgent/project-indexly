import sqlite3
import pandas as pd
from rich.console import Console
from collections import Counter
from .profiler_utils import profile_dataframe
from rich.table import Table
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, Any




console = Console()

# Worker wrapper for parallel profiling
def _profile_table_worker(db_path, tbl, sample_size, full_stats, fast_mode):
    try:
        result = profile_table(
            db_path,
            tbl,
            sample_size=sample_size,
            full_stats=full_stats,
            fast_mode=fast_mode
        )
        return tbl, result
    except Exception as e:
        console.print(f"[red]⚠ Profiling failed for {tbl}: {e}[/red]")
        return tbl, {}

def profile_table(
    db_path: str,
    table: str,
    sample_size: int | None = None,
    full_stats: bool = False,
    fast_mode: bool = False
) -> Dict[str, Any]:
    """Profile a table including numeric, non-numeric, nulls, duplicates, keys."""

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    out = {"table": table}

    # -------------------------
    # Row count
    # -------------------------
    try:
        cur.execute(f"SELECT COUNT(*) FROM '{table}'")
        row_count = cur.fetchone()[0]
    except Exception:
        row_count = None
    out["rows"] = row_count

    # -------------------------
    # Columns
    # -------------------------
    try:
        cur.execute(f"PRAGMA table_info('{table}')")
        cols = [c[1] for c in cur.fetchall()]
    except Exception:
        cols = []
    out["columns"] = cols
    out["cols"] = len(cols)

    # -------------------------
    # Load table
    # -------------------------
    try:
        df = pd.read_sql_query(f"SELECT * FROM '{table}'", conn)
    except Exception:
        df = pd.DataFrame()

    conn.close()

    # -------------------------
    # Unified profiling (sampling handled inside)
    # REMOVED: fast_mode (not supported by profile_dataframe)
    # -------------------------
    profile = profile_dataframe(
        df=df,
        sample_size=sample_size,
        full_data=full_stats
    )

    out.update(profile)

    # -------------------------
    # Flatten numeric stats
    # -------------------------
    numeric_flat = {}
    numeric_summary = profile.get("numeric_summary", {})
    for col, stats in numeric_summary.items():
        for stat_name, value in stats.items():
            numeric_flat[f"{col} ({stat_name})"] = value
    out["numeric_flat"] = numeric_flat

    # -------------------------
    # Non-numeric printing format
    # -------------------------
    out["non_numeric"] = profile.get("extra", {}).get("non_numeric_summary", {})

    return out
