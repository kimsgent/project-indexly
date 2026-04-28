import sqlite3

from indexly import debug_tbl


def test_debug_cleaned_data_table_uses_db_utils_connection(monkeypatch, tmp_path):
    db_path = tmp_path / "cleaned.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE cleaned_data (
            id INTEGER PRIMARY KEY,
            file_name TEXT,
            file_type TEXT,
            source_path TEXT,
            cleaned_at TEXT,
            row_count INTEGER,
            col_count INTEGER,
            data_json TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO cleaned_data (
            id, file_name, file_type, source_path, cleaned_at,
            row_count, col_count, data_json
        )
        VALUES (1, 'sample.csv', 'csv', 'sample.csv', '2026-04-27T10:00:00',
                2, 2, '{"sample_data":[{"a":1},{"a":2}]}')
        """
    )
    conn.commit()
    conn.close()

    def open_test_db():
        test_conn = sqlite3.connect(db_path)
        test_conn.row_factory = sqlite3.Row
        return test_conn

    monkeypatch.setattr(debug_tbl, "_get_db_connection", open_test_db)

    debug_tbl.debug_cleaned_data_table(limit=1)
