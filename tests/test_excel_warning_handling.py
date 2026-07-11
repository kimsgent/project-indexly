import warnings

import pytest

openpyxl = pytest.importorskip("openpyxl")


def _write_workbook(path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet["A1"] = "alpha"
    sheet["B1"] = "beta"
    sheet["A2"] = "gamma"
    workbook.save(path)


def test_xlsx_extraction_suppresses_known_openpyxl_feature_warnings(
    tmp_path, monkeypatch
):
    from indexly.filetype_utils import extract_text_from_file

    path = tmp_path / "feature-warnings.xlsx"
    _write_workbook(path)

    original_load_workbook = openpyxl.load_workbook

    def noisy_load_workbook(*args, **kwargs):
        warnings.warn(
            "Unknown extension is not supported and will be removed",
            UserWarning,
        )
        warnings.warn(
            "Cannot parse header or footer so it will be ignored",
            UserWarning,
        )
        warnings.warn(
            "Conditional Formatting extension is not supported and will be removed",
            UserWarning,
        )
        return original_load_workbook(*args, **kwargs)

    monkeypatch.setattr(openpyxl, "load_workbook", noisy_load_workbook)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        text, metadata = extract_text_from_file(path)

    assert metadata is None
    assert text == "alpha beta gamma"
    assert [str(warning.message) for warning in caught] == []


def test_openpyxl_warning_scope_leaves_unrelated_warnings_visible():
    from indexly.excel_warning_utils import suppress_openpyxl_feature_warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with suppress_openpyxl_feature_warnings():
            warnings.warn("Workbook appears damaged", UserWarning)

    assert [str(warning.message) for warning in caught] == ["Workbook appears damaged"]
