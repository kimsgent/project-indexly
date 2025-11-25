import json
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
            "raw": result["raw"]
        }
    )

    assert isinstance(df, pd.DataFrame)

    # For record-list JSON, check flattened column
    if isinstance(result["raw"], dict) and "records" in result["raw"]:
        assert not df.empty
        assert "records.x" in df.columns






