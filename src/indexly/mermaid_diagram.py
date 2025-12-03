# src/indexly/mermaid_diagram.py
from typing import Dict

def build_mermaid_from_schema(schema_summary: Dict[str, Dict]) -> str:
    """
    Build a simple Mermaid ER diagram from schema_summary.
    schema_summary is expected: {table: {"columns": [{"name":..., "type":..., "pk":bool}], "fks":[(col, ref_table, ref_col),...]}, ...}
    This function is defensive — if FK info missing it will still output tables + PK hints.
    """
    lines = ["erDiagram"]
    for tbl, info in schema_summary.items():
        # define entity with primary key hint
        cols = info.get("columns", [])
        pk_cols = [c["name"] for c in cols if c.get("pk")]
        if pk_cols:
            lines.append(f"    {tbl} {{")
            for c in cols[:8]:  # show up to 8 cols to keep diagram readable
                lines.append(f"        {c.get('type','string')} {c.get('name')}")
            lines.append("    }")
        # fks -> relationships
    # relationships
    for tbl, info in schema_summary.items():
        for fk in info.get("fks", []):
            # fk: (col, ref_table, ref_col)
            col, ref_table, ref_col = fk
            lines.append(f"    {tbl} ||--o{{ {ref_table} : \"{col} -> {ref_col}\"")
    return "\n".join(lines)
