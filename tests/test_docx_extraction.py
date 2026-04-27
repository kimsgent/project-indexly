from pathlib import Path

import pytest


docx = pytest.importorskip("docx")


def _write_docx_with_metadata_table(path: Path) -> None:
    document = docx.Document()

    table = document.add_table(rows=3, cols=4)
    table.rows[0].cells[0].text = "Kunde:"
    table.rows[0].cells[1].text = "ACME GmbH, Frau"
    table.rows[0].cells[2].text = "Erstellt von:"
    table.rows[0].cells[3].text = "MEM"

    table.rows[1].cells[0].text = "Key-Nr.:"
    table.rows[1].cells[1].text = "48830"
    table.rows[1].cells[2].text = "Erstellt am:"
    table.rows[1].cells[3].text = "24.03.2026"

    table.rows[2].cells[0].text = "Problem:"
    table.rows[2].cells[1].text = "Invoices are not saved in the expected folder."
    table.rows[2].cells[2].text = "Patch:"
    table.rows[2].cells[3].text = "029"

    document.add_paragraph("Seite 1 von 1")
    document.add_paragraph("Please check document storage permissions.")
    document.add_paragraph("Please check document storage permissions.")
    document.save(path)


def test_docx_extraction_maps_table_metadata_and_reduces_text_noise(tmp_path):
    from indexly.db_utils import get_tags_for_file
    from indexly.extract_utils import _extract_docx

    path = tmp_path / "ticket.docx"
    _write_docx_with_metadata_table(path)

    result = _extract_docx(path)

    assert isinstance(result, dict)
    assert result["metadata"]["format"] == "DOCX"
    assert result["metadata"]["author"] == "MEM"
    assert result["metadata"]["created"] == "24.03.2026"
    assert result["metadata"]["subject"] == "Invoices are not saved in the expected folder."

    text = result["text"]
    assert "Invoices are not saved in the expected folder." in text
    assert "Please check document storage permissions." in text
    assert text.count("Please check document storage permissions.") == 1
    assert "Seite 1 von 1" not in text
    assert "ACME GmbH" not in text

    tags = get_tags_for_file(path)
    assert "kunde: acme gmbh frau" in tags
    assert "frau" not in tags
    assert "key-nr: 48830" in tags
    assert "patch: 029" in tags
    assert not any(tag.startswith("problem:") for tag in tags)


def test_extract_text_from_file_returns_docx_metadata(tmp_path):
    from indexly.filetype_utils import extract_text_from_file

    path = tmp_path / "ticket.docx"
    _write_docx_with_metadata_table(path)

    text, metadata = extract_text_from_file(path)

    assert text is not None
    assert "Invoices are not saved in the expected folder." in text
    assert metadata["format"] == "DOCX"
    assert metadata["author"] == "MEM"
