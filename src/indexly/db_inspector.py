from pathlib import Path
import sqlite3
from typing import Dict, Any

def inspect_db(db_path: str) -> Dict[str, Any]:
    p = Path(db_path)
    conn = sqlite3.connect(str(p))
    cur = conn.cursor()

    # tables (exclude sqlite_ internal)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cur.fetchall()]

    schemas = {}
    counts = {}
    for t in tables:
        try:
            cur.execute(f"PRAGMA table_info('{t}')")
            schemas[t] = cur.fetchall()
        except Exception:
            schemas[t] = []
        try:
            cur.execute(f"SELECT COUNT(*) FROM '{t}'")
            counts[t] = cur.fetchone()[0]
        except Exception:
            counts[t] = None

    # db size (bytes)
    try:
        db_size = p.stat().st_size
    except Exception:
        db_size = None

    conn.close()
    return {
        "path": str(p),
        "tables": tables,
        "schemas": schemas,
        "counts": counts,
        "db_size_bytes": db_size,
    }
