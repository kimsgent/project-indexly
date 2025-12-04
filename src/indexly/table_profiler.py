# table_profiler.py

from typing import Dict, Any, Optional
import pandas as pd
import sqlite3
from collections import Counter
from . import profiler_utils




def profile_table(
    db_path: str,
    table: str,
    sample_size: int = 1000,
    full_stats: bool = False,
    fast_mode: bool = False
) -> Dict[str, Any]:
    """Profile a table including numeric, non-numeric, nulls, duplicates, keys."""
    import sqlite3
    import pandas as pd
    from .profiler_utils import profile_dataframe

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
    # Sampling
    # -------------------------
    try:
        if full_stats and row_count and row_count <= sample_size * 2:
            df = pd.read_sql_query(f"SELECT * FROM '{table}'", conn)
        else:
            df = pd.read_sql_query(
                f"SELECT * FROM '{table}' LIMIT {int(sample_size)}", conn
            )

        # Safe numeric inference (no deprecated errors="ignore")
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except Exception:
                pass

    except Exception:
        df = pd.DataFrame()

    conn.close()

    # -------------------------
    # Run full unified profiling
    # -------------------------
    profile = profile_dataframe(df)
    out.update(profile)

    # -------------------------
    # Flatten numeric for printing
    # -------------------------
    numeric_flat = {}
    numeric_summary = profile.get("numeric_summary", {})
    for col, stats in numeric_summary.items():
        for stat_name, value in stats.items():
            numeric_flat[f"{col} ({stat_name})"] = value
    out["numeric_flat"] = numeric_flat

    # -------------------------
    # Restore non-numeric printing
    # -------------------------
    out["non_numeric"] = profile.get("extra", {}).get("non_numeric_summary", {})

    return out

