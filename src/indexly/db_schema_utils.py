from typing import Dict, Any, List


def normalize_schema(raw_schema: List[tuple]) -> List[Dict[str, Any]]:
    """
    Convert raw PRAGMA table_info() rows into a normalized dict schema list.

    Raw row format:
        (cid, name, type, notnull, dflt_value, pk)
    """
    schema = []
    for cid, name, col_type, notnull, default, pk in raw_schema:
        schema.append(
            {
                "cid": cid,
                "name": name,
                "type": col_type,
                "not_null": bool(notnull),
                "default": default,
                "primary_key": bool(pk),
            }
        )
    return schema


def detect_relationship_hints(
    schemas: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Simple heuristic: find columns ending in *_id and map to possible tables.
    """
    rels = {}
    lower_tables = {t.lower(): t for t in schemas.keys()}

    for table, cols in schemas.items():
        hints = []
        for col in cols:
            name = col["name"].lower()

            if name.endswith("_id") and len(name) > 3:
                base = name[:-3]  # remove "_id"
                if base in lower_tables:
                    hints.append(
                        {
                            "column": col["name"],
                            "references": lower_tables[base],
                            "confidence": "high",
                        }
                    )
                else:
                    hints.append(
                        {
                            "column": col["name"],
                            "references": None,
                            "confidence": "low",
                        }
                    )

        if hints:
            rels[table] = hints

    return rels


def summarize_schema(schemas: Dict[str, Any]) -> Dict[str, Any]:
    """
    High-level schema summary:
    - column counts
    - primary key presence
    - relationship hints
    """
    summary = {}
    for table, cols in schemas.items():
        info = {
            "columns": len(cols),
            "primary_keys": [
                c["name"] for c in cols if c.get("primary_key")
            ],
        }
        summary[table] = info

    summary["relationships"] = detect_relationship_hints(schemas)
    return summary
