import sqlite3
import time
import pandas as pd
from rich.console import Console
from .profiler_utils import determine_sample_size, profile_dataframe
from typing import Dict, Any

console = Console()


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


# Worker wrapper for parallel profiling
def _profile_table_worker(db_path, tbl, sample_size, full_stats, fast_mode, timeout=None):
    try:
        result = profile_table(
            db_path,
            tbl,
            sample_size=sample_size,
            full_stats=full_stats,
            fast_mode=fast_mode,
            timeout=timeout,
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
    fast_mode: bool = False,
    timeout: int | None = None,
) -> Dict[str, Any]:
    """Profile a table including numeric, non-numeric, nulls, duplicates, keys."""

    conn = sqlite3.connect(db_path)
    if timeout:
        deadline = time.monotonic() + timeout

        def _abort_if_timed_out():
            return 1 if time.monotonic() > deadline else 0

        conn.set_progress_handler(_abort_if_timed_out, 10_000)

    cur = conn.cursor()
    out = {"table": table}
    quoted_table = _quote_identifier(table)

    # -------------------------
    # Row count
    # -------------------------
    try:
        cur.execute(f"SELECT COUNT(*) FROM {quoted_table}")
        row_count = cur.fetchone()[0]
    except Exception:
        row_count = None
    out["rows"] = row_count

    # -------------------------
    # Columns
    # -------------------------
    try:
        cur.execute(f"PRAGMA table_info({quoted_table})")
        cols = [c[1] for c in cur.fetchall()]
    except Exception:
        cols = []
    out["columns"] = cols
    out["cols"] = len(cols)

    # -------------------------
    # Load table, bounded unless full_stats/--all-data is explicit.
    # -------------------------
    load_error = None
    sample_n = None
    should_sample = False
    sample_strategy = "full"
    if not full_stats and row_count is not None:
        sample_n = determine_sample_size(row_count, sample_size)
        should_sample = sample_n is not None and sample_n < row_count

    try:
        if should_sample:
            if fast_mode:
                query = f"SELECT * FROM {quoted_table} LIMIT {int(sample_n)}"
                sample_strategy = "limit"
            else:
                query = (
                    f"SELECT * FROM {quoted_table} "
                    f"ORDER BY RANDOM() LIMIT {int(sample_n)}"
                )
                sample_strategy = "random"
            df = pd.read_sql_query(query, conn)
        else:
            df = pd.read_sql_query(f"SELECT * FROM {quoted_table}", conn)
    except Exception as e:
        load_error = e
        df = pd.DataFrame()

    conn.close()

    # -------------------------
    # Unified profiling (sampling handled inside)
    # REMOVED: fast_mode (not supported by profile_dataframe)
    # -------------------------
    profile = profile_dataframe(
        df=df,
        sample_size=None,
        full_data=True,
        fast_mode=fast_mode,
    )

    out.update(profile)
    out["sample_size_requested"] = sample_size
    out["profiled_rows"] = int(len(df))
    out["sample_strategy"] = sample_strategy
    out["sampled"] = bool(should_sample)
    if load_error is not None:
        out["warning"] = f"Table load failed: {load_error}"

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
    out["key_hints"] = [
        col for col, role in profile.get("key_candidates", {}).items() if role
    ]

    return out
