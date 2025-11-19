# tests/helpers.py

def assert_passthrough(result, expected_type: str):
    """
    Ensures the detect_and_load passthrough logic is correct.
    Used for CSV / JSON passthrough modes.
    """
    assert result["file_type"] == expected_type
    assert result["loader_spec"] == "passthrough"
    assert result["df"] is None
    assert result["raw"] is None
    assert result["metadata"]["validated"] is True
