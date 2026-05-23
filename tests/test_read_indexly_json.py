import json

import pytest

from indexly.read_indexly_json import (
    load_indexly_json,
    read_indexly_json,
    summarize_indexly_json,
)


def _db_summary():
    return {
        "meta": {
            "db_path": "chinook.db",
            "db_size_bytes": 4096,
            "tables": ["artists"],
        },
        "global": {
            "db_path": "chinook.db",
            "db_size_bytes": 4096,
            "table_count": 1,
            "total_rows_estimated": 2,
        },
        "schemas": {
            "artists": [
                {
                    "name": "ArtistId",
                    "type": "INTEGER",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "Name",
                    "type": "NVARCHAR(120)",
                    "not_null": False,
                    "primary_key": False,
                },
            ]
        },
        "schema_summary": {
            "tables": {
                "artists": {
                    "columns": [
                        {"name": "ArtistId", "type": "INTEGER", "pk": True},
                        {"name": "Name", "type": "NVARCHAR(120)", "pk": False},
                    ],
                    "primary_keys": ["ArtistId"],
                }
            }
        },
        "relations": {
            "foreign_keys": [
                {
                    "from_table": "albums",
                    "from_column": "ArtistId",
                    "to_table": "artists",
                    "to_column": "ArtistId",
                }
            ]
        },
        "counts": {"artists": 2},
        "profiles": {},
    }


def test_summarize_indexly_json_renders_column_count_not_column_list(capsys):
    summarize_indexly_json(_db_summary(), preview=1)

    output = capsys.readouterr().out

    assert "artists" in output
    assert "ArtistId, Name, ArtistId" not in output
    assert "Persisted Foreign Keys" in output
    assert "albums.ArtistId" in output


def test_read_indexly_json_warns_for_non_db_summary_without_analysis(tmp_path, capsys):
    path = tmp_path / "csv.analysis.json"
    path.write_text(json.dumps({"metadata": {"rows": 2}, "sample_data": []}))

    data = read_indexly_json(path, show_summary=True)

    output = capsys.readouterr().out
    assert data["metadata"]["rows"] == 2
    assert "will not re-analyze" in output
    assert "Indexly JSON Preview" in output


def test_load_indexly_json_rejects_non_object_json(tmp_path):
    path = tmp_path / "not-summary.json"
    path.write_text(json.dumps([{"rows": 2}]))

    with pytest.raises(ValueError):
        load_indexly_json(path)
