import json
import gzip
import builtins
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from indexly.universal_loader import detect_and_load
from tests.helpers import assert_passthrough


def test_yaml_loading(tmp_path):
    p = tmp_path / "data.yaml"
    p.write_text("""
    items:
      - id: 1
        name: alpha
      - id: 2
        name: beta
    """)
    result = detect_and_load(p)
    assert result["file_type"] == "yaml"
    assert result["metadata"]["validated"]
    assert isinstance(result["raw"], dict)
    assert isinstance(result["df"], pd.DataFrame)
    assert result["metadata"]["rows"] >= 1


def test_xml_loading(tmp_path):
    p = tmp_path / "data.xml"
    p.write_text("""
    <root>
    <entry><id>1</id><val>10</val></entry>
    <entry><id>2</id><val>20</val></entry>
 </root>
    """)
    result = detect_and_load(p)
    assert result["file_type"] == "xml"
    assert result["metadata"]["validated"]
    if result["file_type"] == "xml":
        assert isinstance(result["df_preview"], pd.DataFrame)
    else:
        assert isinstance(result["df"], pd.DataFrame)


def test_csv_fallback(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n3,4\n")
    result = detect_and_load(p)

    # Passthrough mode?
    if result["loader_spec"] == "passthrough":
        assert_passthrough(result, "csv")
        return

    # Loader mode
    assert isinstance(result["df"], pd.DataFrame)
    assert result["metadata"]["rows"] == 2


def test_json_fallback(tmp_path):
    import pandas as pd
    import json
    from indexly.universal_loader import detect_and_load
    from indexly.json_pipeline import run_json_generic_pipeline

    # Prepare a simple record-list JSON (NDJSON style)
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"records": [{"x": 1}, {"x": 2}]}))

    result = detect_and_load(p)

    # Loader spec must exist
    assert "loader_spec" in result
    assert result["loader_spec"] is not None

    # Raw JSON must be returned as dict or list
    assert isinstance(result["raw"], dict) or isinstance(result["raw"], list)

    # df is not guaranteed at this stage
    assert result["df"] is None

    # Metadata checks
    metadata = result.get("metadata", {})
    assert metadata.get("rows", 0) >= 1
    assert "loader_used" in metadata

    # Optional: test DataFrame creation using the generic pipeline
    df, summary_dict, tree_dict = run_json_generic_pipeline(
        file_path=p,
        args={
            "verbose": False,
            "treeview": False,
            "meta": metadata,
            "raw": result["raw"],
        },
    )

    assert isinstance(df, pd.DataFrame)

    # For record-list JSON, check flattened column
    if isinstance(result["raw"], dict) and "records" in result["raw"]:
        assert not df.empty
        assert "records.x" in df.columns


def test_ndjson_loader_uses_chunk_size_without_dropping_valid_rows(tmp_path):
    p = tmp_path / "records.json"
    p.write_text(
        '{"id": 1, "name": "A"}\n{"id": 2, "name": "B"}\n{"id": 3, "name": "C"}\n',
        encoding="utf-8",
    )

    class Args:
        chunk_size = 2

    result = detect_and_load(p, Args())

    assert result["raw"] == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    struct = result["metadata"]["json_structure"]
    assert struct["json_mode"] == "ndjson"
    assert struct["sampled"] is True
    assert struct["rows_sampled"] == 2


def test_ndjson_loader_rejects_malformed_lines(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"id": 1}\nnot json\n{"id": 2}\n', encoding="utf-8")

    result = detect_and_load(p)
    assert result["metadata"]["validated"] is False
    assert result["metadata"]["error_code"] == "json_load_failed"
    assert "Invalid NDJSON" in result["metadata"]["error"]


def test_ndjson_loader_rejects_invalid_trailing_lines_after_sampling(tmp_path):
    p = tmp_path / "bad_trailing.ndjson"
    p.write_text(
        '{"id": 1}\n{"id": 2}\n{"id": 3}\nnot json\n',
        encoding="utf-8",
    )

    class Args:
        chunk_size = 2

    result = detect_and_load(p, Args())
    assert result["metadata"]["validated"] is False
    assert result["metadata"]["error_code"] == "json_load_failed"
    assert "Invalid NDJSON" in result["metadata"]["error"]


def test_json_gz_loader_supports_standard_json(tmp_path):
    p = tmp_path / "records.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump([{"id": 1}, {"id": 2}], fh)

    result = detect_and_load(p)

    assert result["file_type"] == "json"
    assert result["raw"] == [{"id": 1}, {"id": 2}]
    assert result["metadata"]["json_structure"]["is_record_list"] is True


def test_large_socrata_streaming_respects_chunk_size(monkeypatch, tmp_path):
    p = tmp_path / "socrata_large.json"
    payload = {
        "columns": [{"fieldName": "id"}, {"fieldName": "value"}],
        "data": [[idx, idx * 10] for idx in range(100)],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")

    real_stat = Path.stat

    def _fake_stat(self):
        if str(self) == str(p):
            return SimpleNamespace(st_size=40 * 1024 * 1024)
        return real_stat(self)

    monkeypatch.setattr(Path, "stat", _fake_stat)

    class Args:
        chunk_size = 5

    result = detect_and_load(p, Args())
    assert result["metadata"]["validated"] is True
    assert result["metadata"]["json_structure"]["json_mode"] == "socrata"
    assert result["metadata"]["json_structure"]["rows_sampled"] == 5
    assert len(result["raw"]["data"]) == 5


def test_large_socrata_streaming_fails_on_row_parse_error(monkeypatch, tmp_path):
    p = tmp_path / "socrata_bad.json"
    p.write_text(
        '{"columns":[{"fieldName":"id"}],"data":[[1],[2],oops,[4]]}',
        encoding="utf-8",
    )

    real_stat = Path.stat

    def _fake_stat(self):
        if str(self) == str(p):
            return SimpleNamespace(st_size=40 * 1024 * 1024)
        return real_stat(self)

    monkeypatch.setattr(Path, "stat", _fake_stat)

    class Args:
        chunk_size = 5

    result = detect_and_load(p, Args())
    assert result["metadata"]["validated"] is False
    assert result["metadata"]["error_code"] == "json_load_failed"
    assert "Invalid Socrata data row" in result["metadata"]["error"]


def test_universal_loader_module_import_does_not_eagerly_import_pandas(monkeypatch):
    sys.modules.pop("indexly.universal_loader", None)
    real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pandas" or name.startswith("pandas."):
            raise AssertionError("universal_loader imported pandas at module import time")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    module = importlib.import_module("indexly.universal_loader")
    assert hasattr(module, "detect_and_load")


def test_detect_and_load_reports_unsupported_compressed_sqlite(tmp_path):
    p = tmp_path / "sample.sqlite.gz"
    with gzip.open(p, "wb") as fh:
        fh.write(b"sqlite-data")

    result = detect_and_load(p)
    assert result["file_type"] == "sqlite"
    assert result["metadata"]["validated"] is False
    assert result["metadata"]["error_code"] == "unsupported_compressed_binary"
    assert "Decompress" in result["metadata"]["error"]
