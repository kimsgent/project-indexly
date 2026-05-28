import json

import pandas as pd
import pytest


def configure_analysis_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("INDEXLY_ANALYSIS_DB", raising=False)


def insert_legacy_dataset(file_name, source_path=None, cleaned=None, raw=None):
    from indexly.db_utils import _get_db_connection

    conn = _get_db_connection()
    conn.execute(
        """
        INSERT INTO cleaned_data(
            file_name, file_type, source_path, cleaned_data_json, raw_data_json
        )
        VALUES (?, 'csv', ?, ?, ?)
        """,
        (
            file_name,
            source_path,
            json.dumps(cleaned or [{"id": 1, "value": 10}]),
            json.dumps(raw or [{"id": 1, "value": 99}]),
        ),
    )
    conn.commit()
    conn.close()


def test_resolver_preserves_legacy_cleaned_data_file_name(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    insert_legacy_dataset("steps.csv", cleaned=[{"id": 1, "steps": 100}])

    from indexly.inference.loader import load_dataframe

    df = load_dataframe("steps.csv")

    assert df.to_dict(orient="records") == [{"id": 1, "steps": 100}]


def test_resolver_finds_legacy_source_path(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "data" / "sleepday.csv"
    source.parent.mkdir()
    insert_legacy_dataset(
        "sleepday.csv",
        source_path=str(source),
        cleaned=[{"Id": 1, "TotalMinutesAsleep": 420}],
    )

    from indexly.datasets.resolver import resolve_dataset

    resolved = resolve_dataset(str(source))

    assert resolved.resolution == "cleaned_data.source_path"
    assert list(resolved.df.columns) == ["Id", "TotalMinutesAsleep"]


def test_existing_csv_path_loads_ephemerally_without_registering(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "fresh.csv"
    source.write_text("id,value\n1,10\n2,20\n", encoding="utf-8")

    from indexly.datasets.resolver import resolve_dataset
    from indexly.db_utils import _get_db_connection

    resolved = resolve_dataset(str(source), columns=["id", "value"])

    conn = _get_db_connection()
    registry_count = conn.execute("SELECT COUNT(*) FROM dataset_registry").fetchone()[0]
    legacy_count = conn.execute("SELECT COUNT(*) FROM cleaned_data").fetchone()[0]
    conn.close()

    assert resolved.resolution == "ephemeral.csv"
    assert len(resolved.df) == 2
    assert registry_count == 0
    assert legacy_count == 0


def test_save_analysis_result_registers_catalog_and_keeps_legacy_fallback(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "registered.csv"
    source.write_text("id,value\n1,10\n2,20\n", encoding="utf-8")

    from indexly.analyze_utils import save_analysis_result
    from indexly.datasets.resolver import resolve_dataset
    from indexly.db_utils import _get_db_connection

    save_analysis_result(
        file_path=str(source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "value": [10]}),
        raw_df=pd.DataFrame({"id": [1, 2], "value": [10, 20]}),
        cleaned_df=pd.DataFrame({"id": [1, 2], "value": [10, 20]}),
        row_count=2,
        col_count=2,
    )

    resolved = resolve_dataset("registered")
    conn = _get_db_connection()
    catalog_row = conn.execute(
        "SELECT dataset_name, file_name, source_path, row_count FROM dataset_registry"
    ).fetchone()
    conn.close()

    assert resolved.record is not None
    assert catalog_row["row_count"] == 2
    assert catalog_row["dataset_name"] == "registered"
    assert catalog_row["file_name"] == "registered.csv"


def test_missing_dataset_error_is_actionable_without_csv_guess(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)

    from indexly.datasets.resolver import DatasetResolutionError, resolve_dataset

    with pytest.raises(DatasetResolutionError) as exc_info:
        resolve_dataset("unknown")

    message = str(exc_info.value)
    assert "Did you mean" not in message
    assert "existing CSV path" in message
