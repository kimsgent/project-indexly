import json
import pandas as pd
from indexly.universal_loader import detect_and_load

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
    assert result["file_type"] == "csv"
    assert isinstance(result["df"], pd.DataFrame)
    assert result["metadata"]["rows"] == 2


def test_json_fallback(tmp_path):
    import json
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"records": [{"x": 1}, {"x": 2}]}))
    result = detect_and_load(p)
    assert result["file_type"] == "json"
    assert isinstance(result["raw"], dict)
    assert isinstance(result["df"], pd.DataFrame)
    assert result["metadata"]["rows"] >= 1

