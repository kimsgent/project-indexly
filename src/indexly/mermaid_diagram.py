# src/indexly/mermaid_diagram.py
from typing import Dict

def build_mermaid_from_schema(schema_summary: dict, relations: dict) -> str:
    lines = ["erDiagram"]

    #
    # 1. Render real tables only
    #
    for tbl, info in schema_summary.items():
        cols = info.get("columns", [])
        if not cols:
            continue

        lines.append(f"    {tbl} {{")
        for col in cols[:8]:  # still limit to first 8 for readability
            col_type = col.get("type", "string")
            lines.append(f"        {col_type} {col['name']}")
        lines.append("    }")

    #
    # 2. Relation collector to avoid duplicates
    #
    seen = set()

    def add_edge(src, dst, label):
        key = (src, dst, label)
        if key not in seen:
            lines.append(f"    {src} ||--o{{ {dst} : \"{label}\"")
            seen.add(key)

    #
    # 3. Foreign key relations
    #
    for fk in relations.get("foreign_keys", []):
        add_edge(
            fk["from_table"],
            fk["to_table"],
            f"{fk['from_column']} → {fk['to_column']}"
        )

    #
    # 4. Heuristic relations (only when an actual target was inferred)
    #
    for h in relations.get("heuristic_relations", []):
        tgt = h.get("possible_target")
        if tgt:
            add_edge(
                h["from_table"],
                tgt,
                f"{h['from_column']} (heuristic)"
            )

    #
    # 5. FTS virtual / shadow tables (SQLite only)
    #
    for r in relations.get("fts_relations", []):
        add_edge(r["shadow"], r["base"], "fts-shadow")

    #
    # 6. Adjacency graph (only add nodes not already FK-connected)
    #
    graph = relations.get("graph", {})
    fk_pairs = {(fk["from_table"], fk["to_table"]) for fk in relations.get("foreign_keys", [])}

    for a, targets in graph.items():
        for b in targets:
            if (a, b) not in fk_pairs:
                add_edge(a, b, "adj")

    return "\n".join(lines)
