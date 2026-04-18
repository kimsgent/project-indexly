from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from indexly.json_pipeline import (
    run_json_pipeline,
    run_record_list_json_pipeline,
)


def test_run_json_pipeline_reroutes_ndjson_record_list(tmp_path):
    file_path = tmp_path / "records.json"
    file_path.write_text('{"id":1,"name":"A"}\n{"id":2,"name":"B"}\n', encoding="utf-8")

    args = SimpleNamespace(treeview=False)
    df, stats_df, table_dict = run_json_pipeline(
        file_path=file_path,
        args=args,
        df=None,
        verbose=False,
    )

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert list(df["id"]) == [1, 2]
    assert isinstance(table_dict, dict)
    assert table_dict.get("rows") == 2
    assert table_dict.get("cols") == 2
    assert stats_df is None or not stats_df.empty


def test_record_list_pipeline_promotes_single_key_objects():
    records = [
        {"employee": {"id": 1, "name": "Ada"}},
        {"employee": {"id": 2, "name": "Bob"}},
    ]

    df, summary_dict, table_output, tree_dict = run_record_list_json_pipeline(
        records=records,
        file_path=Path("employees.json"),
        metadata={"json_mode": "ndjson"},
        show_treeview=False,
        verbose=False,
    )

    assert isinstance(df, pd.DataFrame)
    assert {"id", "name"}.issubset(set(df.columns))
    assert summary_dict["detected_type"] == "ndjson"
    assert summary_dict["rows"] == 2
    assert isinstance(table_output, dict)
    assert tree_dict == {}
