from typing import Dict, Any, Optional
import pandas as pd
import sqlite3
from collections import Counter

def _numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return pd.DataFrame()

    stats = numeric.agg(['count', 'mean', 'std', 'min', 'max']).transpose()

    # Proper NaN → None conversion
    stats = stats.where(pd.notnull(stats), None)

    return stats


def profile_table(db_path: str, table: str, sample_size: int = 1000, full_stats: bool = False) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    out: Dict[str, Any] = {"table": table}

    # row count
    try:
        cur.execute(f"SELECT COUNT(*) FROM '{table}'")
        out["rows"] = cur.fetchone()[0]
    except Exception:
        out["rows"] = None

    # columns/schema
    try:
        cur.execute(f"PRAGMA table_info('{table}')")
        cols = [c[1] for c in cur.fetchall()]
        out["columns"] = cols
    except Exception:
        out["columns"] = []

    # sample rows (fallback)
    try:
        sample_q = f"SELECT * FROM '{table}' LIMIT {int(sample_size)}"
        df = pd.read_sql_query(sample_q, conn)
    except Exception:
        df = pd.DataFrame()

    # numeric summary (sample or full if requested and small)
    if full_stats and out.get("rows") and out["rows"] <= sample_size * 2:
        try:
            df_full = pd.read_sql_query(f"SELECT * FROM '{table}'", conn)
            num_stats = _numeric_summary(df_full)
        except Exception:
            num_stats = _numeric_summary(df)
    else:
        num_stats = _numeric_summary(df)

    out["numeric_summary"] = num_stats.to_dict() if not num_stats.empty else {}

    # non-numeric summary: top values, unique, nulls, sample
    non_numeric = {}
    if not df.empty:
        for col in df.select_dtypes(exclude="number").columns:
            ser = df[col].dropna().astype(str)
            try:
                vc = ser.value_counts()
                top = vc.head(10).to_dict()
                non_numeric[col] = {
                    "unique": int(ser.nunique()),
                    "nulls": int(df[col].isna().sum()),
                    "sample": ser.head(3).tolist(),
                    "top": top,
                }
            except Exception:
                non_numeric[col] = {"unique": None, "nulls": None, "sample": [], "top": {}}
    out["non_numeric"] = non_numeric

    # quick heuristics: potential key candidates and duplicates
    key_hints = []
    for c in out.get("columns", []):
        if c.lower().endswith("_id") or c.lower() == "id" or c.lower().endswith("id"):
            key_hints.append(c)
    out["key_hints"] = key_hints

    conn.close()
    return out
