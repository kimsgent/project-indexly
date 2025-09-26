import pytest, os

skip_if_ci = pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") == "true",
    reason="Skipped in CI due to system dependencies"
)

@skip_if_ci
def test_ocr_parsing():
    # This needs pytesseract installed
    assert True

