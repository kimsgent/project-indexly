import json
import sqlite3

import indexly.observers.csv.csv_observer as csv_observer_module
from indexly.observers.csv.csv_observer import CSVObserver


def test_csv_observer_extracts_cleaned_record_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "cleaned.db"
    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE cleaned_data (
            source_path TEXT,
            file_name TEXT,
            summary_json TEXT,
            sample_json TEXT,
            cleaned_at TEXT,
            row_count INTEGER,
            col_count INTEGER,
            cleaned_data_json TEXT
        )
        """)
    conn.execute(
        """
        INSERT INTO cleaned_data (
            source_path, file_name, summary_json, sample_json, cleaned_at,
            row_count, col_count, cleaned_data_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(source.resolve()),
            source.name,
            json.dumps({"a": {"count": 1}}),
            json.dumps([{"a": 1, "b": 2}]),
            "2024-01-01T00:00:00Z",
            1,
            2,
            json.dumps([{"a": 1, "b": 2}]),
        ),
    )
    conn.commit()
    conn.close()

    def open_test_db():
        test_conn = sqlite3.connect(db_path)
        test_conn.row_factory = sqlite3.Row
        return test_conn

    monkeypatch.setattr(csv_observer_module, "_get_db_connection", open_test_db)

    state = CSVObserver().extract(source, {"hash": "abc"})

    assert state["hash"] == "abc"
    assert state["columns"] == ["a", "b"]
    assert state["row_count"] == 1
    assert state["summary"] == {"a": {"count": 1}}
