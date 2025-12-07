from __future__ import annotations
from typing import Dict, Any, List, Union, Optional
from pathlib import Path
import sqlite3

# Relation helpers
from .relation_detector import (
    analyze_relations,
    detect_heuristic_relations,
    detect_fts_shadow_tables,
    build_relation_graph,
)
from .mermaid_diagram import build_mermaid_from_schema

def normalize_schema(raw_schema: List[tuple], table_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Convert raw PRAGMA table_info() rows into a normalized schema list.

    Raw row format: (cid, name, type, notnull, dflt_value, pk)

    table_name: optional, used for heuristic PK detection (TableId pattern)
    """
    schema: List[Dict[str, Any]] = []
    for cid, name, col_type, notnull, default, pk in raw_schema:
        is_pk = bool(pk)
        if not is_pk and table_name and name.lower() == f"{table_name.lower()}id":
            is_pk = True

        schema.append(
            {
                "cid": cid,
                "name": name,
                "type": col_type,
                "not_null": bool(notnull),
                "default": default,
                "primary_key": is_pk,
            }
        )
    return schema


def _open_conn_if_needed(conn_or_path: Optional[Union[sqlite3.Connection, str, Path]]):
    """
    Return (conn, opened_here: bool). If input is a path, open connection.
    """
    if conn_or_path is None:
        return None, False
    if isinstance(conn_or_path, sqlite3.Connection):
        return conn_or_path, False
    conn = sqlite3.connect(str(conn_or_path))
    return conn, True


def load_schemas(conn: sqlite3.Connection, filter_table: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load normalized schemas for all tables, optionally filtering a single table.
    """
    schemas: Dict[str, List[Dict[str, Any]]] = {}
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    for table in tables:
        if filter_table and table.lower() != filter_table.lower():
            continue
        cur.execute(f"PRAGMA table_info('{table}')")
        raw = cur.fetchall()
        schemas[table] = normalize_schema(raw, table_name=table)
    return schemas


def summarize_schema(
    schemas: Dict[str, List[Dict[str, Any]]],
    conn: Optional[Union[sqlite3.Connection, str, Path]] = None,
    filter_table: Optional[str] = None,
) -> Dict[str, Any]:

    # -----------------------------------------
    # 1) PROFILES / TABLE INFO (expected by save_markdown)
    # -----------------------------------------
    profiles: Dict[str, Any] = {}
    for table, cols in schemas.items():
        if filter_table and table.lower() != filter_table.lower():
            continue

        profiles[table] = {
            "rows": None,            # (row estimation added later or externally)
            "columns": cols,         # store raw column objects for flexibility
            "non_numeric": {},       # placeholder for profiling results
        }

    # -----------------------------------------
    # 2) RELATIONS
    # -----------------------------------------
    conn_obj, opened_here = _open_conn_if_needed(conn)
    try:
        if conn_obj is not None:
            # Full FK/heuristic/fts detection
            rel_block = analyze_relations(conn_obj, schemas).get("relations", {})
        else:
            # No DB handle → fallback mode (still universal)
            heuristics = detect_heuristic_relations(schemas)
            fts_rel = detect_fts_shadow_tables(schemas)
            foreign_keys: List[Dict[str, Any]] = []
            graph = build_relation_graph(foreign_keys, heuristics, fts_rel)
            rel_block = {
                "foreign_keys": foreign_keys,
                "heuristic_relations": heuristics,
                "fts_relations": fts_rel,
                "graph": graph,
            }
    finally:
        if opened_here and conn_obj is not None:
            conn_obj.close()

    # -----------------------------------------
    # 3) BUILD SCHEMA SUMMARY (universal for Mermaid)
    # -----------------------------------------
    schema_summary = {}
    for table, cols in schemas.items():
        schema_summary[table] = {
            "columns": [
                {
                    "name": c["name"],
                    "type": c.get("type", "string"),
                    "pk": bool(c.get("primary_key")),
                }
                for c in cols
            ],
            "fks": [],
        }

    # Normalize FK formats
    for fk in rel_block.get("foreign_keys", []):
        if isinstance(fk, dict) and {
            "from_table", "from_column", "to_table", "to_column"
        } <= fk.keys():
            schema_summary[fk["from_table"]]["fks"].append(
                (fk["from_column"], fk["to_table"], fk["to_column"])
            )

    # -----------------------------------------
    # 4) GENERATE MERMAID DIAGRAM
    # -----------------------------------------
    rel_block["mermaid"] = build_mermaid_from_schema(schema_summary, rel_block)

    # -----------------------------------------
    # 5) META (universal, safe)
    # -----------------------------------------
    meta = {
        "tables_count": len(schemas),
        "has_connection": conn_obj is not None,
    }

    # -----------------------------------------
    # 6) FINAL SUMMARY (compatible with save_markdown)
    # -----------------------------------------
    summary = {
        "meta": meta,
        "profiles": profiles,
        "relations": rel_block,
        "schema_summary": schema_summary,
        "adjacency_graph": rel_block.get("graph", {}),
    }

    return summary

