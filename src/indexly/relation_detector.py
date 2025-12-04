# relation_detector.py
from __future__ import annotations
from typing import Dict, Any, List
import sqlite3
import re


# -------------------------------------------------------------------
# FTS5 SHADOW TABLE MAPPING (Indexly-specific enhancement)
# -------------------------------------------------------------------
FTS_SHADOW_PATTERNS = {
    r"(.+)_data$": "{base}",
    r"(.+)_idx$": "{base}",
    r"(.+)_content$": "{base}",
    r"(.+)_docsize$": "{base}",
    r"(.+)_config$": "{base}",
    r"(.+)_vocab$": "{base}",
}


def detect_fts_shadow_relation(table: str) -> str | None:
    """
    Detect whether a table is a shadow table for an FTS5 virtual table.
    """
    for pattern, base_fmt in FTS_SHADOW_PATTERNS.items():
        m = re.match(pattern, table)
        if m:
            base = m.group(1)
            return base
    return None


# -------------------------------------------------------------------
# FOREIGN KEY DETECTOR
# -------------------------------------------------------------------
def detect_foreign_keys(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    out = []
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    for table in tables:
        try:
            cur.execute(f"PRAGMA foreign_key_list('{table}')")
            fks = cur.fetchall()
        except Exception:
            continue

        for cid, seq, ref_table, from_col, to_col, on_update, on_delete, match in fks:
            out.append(
                {
                    "from_table": table,
                    "from_column": from_col,
                    "to_table": ref_table,
                    "to_column": to_col,
                    "on_delete": on_delete,
                    "on_update": on_update,
                }
            )
    return out


# -------------------------------------------------------------------
# HEURISTIC DETECTOR (Indexly-specific — path-based & _id-based)
# -------------------------------------------------------------------
def detect_heuristic_relations(
    schemas: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:

    out = []
    lower_map = {t.lower(): t for t in schemas.keys()}

    for table, cols in schemas.items():
        for col in cols:
            name = col["name"].lower()

            # 1) *_id pattern
            if name.endswith("_id") and len(name) > 3:
                base = name[:-3]
                confidence = "high" if base in lower_map else "low"
                out.append(
                    {
                        "from_table": table,
                        "from_column": col["name"],
                        "possible_target": lower_map.get(base),
                        "confidence": confidence,
                    }
                )

            # 2) Indexly-specific: path → file_index/file_metadata/file_tags
            if name == "path":
                for target in ["file_index", "file_metadata", "file_tags", "files"]:
                    if target != table:  # avoid self-loop
                        out.append(
                            {
                                "from_table": table,
                                "from_column": col["name"],
                                "possible_target": target,
                                "confidence": "medium",
                            }
                        )

    return out


# -------------------------------------------------------------------
# GRAPH BUILDER
# -------------------------------------------------------------------
def build_relation_graph(
    foreign_keys: List[Dict[str, Any]],
    heuristics: List[Dict[str, Any]],
    fts_relations: List[Dict[str, str]]
) -> Dict[str, List[str]]:
    graph = {}

    def add_edge(a: str, b: str):
        if a not in graph:
            graph[a] = []
        if b not in graph[a]:
            graph[a].append(b)

    # Hard relations (FK)
    for fk in foreign_keys:
        add_edge(fk["from_table"], fk["to_table"])

    # Soft relations (heuristics)
    for h in heuristics:
        if h["possible_target"]:
            add_edge(h["from_table"], h["possible_target"])

    # FTS shadow table relations
    for rel in fts_relations:
        add_edge(rel["shadow"], rel["base"])

    return graph


# -------------------------------------------------------------------
# FTS SHADOW SCAN
# -------------------------------------------------------------------
def detect_fts_shadow_tables(schemas: Dict[str, Any]) -> List[Dict[str, str]]:
    out = []
    for table in schemas.keys():
        base = detect_fts_shadow_relation(table)
        if base and base in schemas:
            out.append({"shadow": table, "base": base})
    return out


# -------------------------------------------------------------------
# MAIN ENTRY
# -------------------------------------------------------------------
def analyze_relations(
    conn: sqlite3.Connection,
    schemas: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:

    foreign_keys = detect_foreign_keys(conn)
    heuristics = detect_heuristic_relations(schemas)
    fts_rel = detect_fts_shadow_tables(schemas)

    graph = build_relation_graph(foreign_keys, heuristics, fts_rel)

    return {
        "relations": {
            "foreign_keys": foreign_keys,
            "heuristic_relations": heuristics,
            "fts_relations": fts_rel,
            "graph": graph,
        }
    }
