import sqlite3

from indexly.analyze_db import _parse_export_formats
from indexly.mermaid_diagram import build_mermaid_from_schema
from indexly.table_profiler import profile_table


def _make_numbers_db(path, rows=100):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE parent (ParentId INTEGER PRIMARY KEY, name TEXT)")
    cur.execute(
        "CREATE TABLE child (ChildId INTEGER PRIMARY KEY, ParentId INTEGER, value REAL, "
        "FOREIGN KEY(ParentId) REFERENCES parent(ParentId))"
    )
    cur.executemany(
        "INSERT INTO parent (ParentId, name) VALUES (?, ?)",
        [(idx, f"parent-{idx}") for idx in range(1, rows + 1)],
    )
    cur.executemany(
        "INSERT INTO child (ChildId, ParentId, value) VALUES (?, ?, ?)",
        [(idx, idx, idx * 1.5) for idx in range(1, rows + 1)],
    )
    conn.commit()
    conn.close()


def test_profile_table_honors_sample_size_without_all_data(tmp_path):
    db_path = tmp_path / "sample.db"
    _make_numbers_db(db_path)

    profile = profile_table(
        str(db_path),
        "child",
        sample_size=10,
        full_stats=False,
        fast_mode=True,
    )

    assert profile["rows"] == 100
    assert profile["profiled_rows"] == 10
    assert profile["sampled"] is True
    assert profile["sample_strategy"] == "limit"
    assert profile["numeric_summary"]["value"]["std"] is None
    assert "ChildId" in profile["identifier_columns"]


def test_profile_table_all_data_overrides_sampling(tmp_path):
    db_path = tmp_path / "full.db"
    _make_numbers_db(db_path)

    profile = profile_table(
        str(db_path),
        "child",
        sample_size=10,
        full_stats=True,
        fast_mode=False,
    )

    assert profile["rows"] == 100
    assert profile["profiled_rows"] == 100
    assert profile["sampled"] is False
    assert profile["numeric_summary"]["value"]["std"] is not None


def test_mermaid_renders_tables_from_schema_summary_wrapper():
    schema_summary = {
        "tables": {
            "parent": {
                "columns": [
                    {"name": "ParentId", "type": "INTEGER", "pk": True},
                    {"name": "name", "type": "TEXT", "pk": False},
                ]
            },
            "child": {
                "columns": [
                    {"name": "ChildId", "type": "INTEGER", "pk": True},
                    {"name": "ParentId", "type": "INTEGER", "pk": False},
                ]
            },
        }
    }
    relations = {
        "foreign_keys": [
            {
                "from_table": "child",
                "from_column": "ParentId",
                "to_table": "parent",
                "to_column": "ParentId",
            }
        ],
        "heuristic_relations": [],
        "fts_relations": [],
        "graph": {},
    }

    mermaid = build_mermaid_from_schema(schema_summary, relations)

    assert "parent {" in mermaid
    assert "child {" in mermaid
    assert 'parent ||--o{ child : "ParentId' in mermaid


def test_analyze_db_export_parser_accepts_multiple_formats():
    assert _parse_export_formats("json,md,json") == ["json", "md"]
