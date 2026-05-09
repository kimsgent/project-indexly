import struct

from indexly.mtw_extractor import _extract_column_names, _worksheet_payload


def _doubles(*values):
    return b"".join(struct.pack("<d", value) for value in values)


def test_worksheet_payload_extracts_clean_numeric_table():
    raw = (
        b"MTB12   WIN     \x00"
        b"Target data. The column <range> stores feet and <miss> stores inches.\x00"
        b"\xff\x00\x13"
        + _doubles(9.0, 6.0, 2.0)
        + b"\x00" * 24
        + _doubles(1.5, 0.35, 0.675)
    )

    names, rows, notes = _worksheet_payload(raw)

    assert names == ["range", "miss"]
    assert rows == [["9", "1.5"], ["6", "0.35"], ["2", "0.675"]]
    assert notes == ["Target data. The column <range> stores feet and <miss> stores inches."]


def test_extract_column_names_falls_back_to_stream_labels():
    raw = b"\x00Arial\x00normal\x00low\x00medium\x00high\x00"

    assert _extract_column_names(raw) == ["normal", "low", "medium", "high"]
