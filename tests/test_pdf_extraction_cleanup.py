from indexly.extract_utils import (
    _clean_pdf_text_pages,
    _infer_pdf_title,
    _is_distinct_pdf_ocr_text,
    _should_ocr_pdf_page,
)


class _PageWithImages:
    def __init__(self, has_images=True):
        self._has_images = has_images

    def get_images(self, full=True):
        return [object()] if self._has_images else []


def test_clean_pdf_text_pages_removes_repeated_headers_and_page_markers():
    pages = [
        "IT-Blech Startprobleme nach Update\nSeite 1 von 2\n1.1 Start\nText A\n1.1 Start",
        "IT-Blech Startprobleme nach Update\nIT-Blech Seite 2 von 2\n1.2 Lösung\nText B",
    ]

    cleaned = _clean_pdf_text_pages(pages)

    assert "Seite 1 von 2" not in cleaned
    assert "IT-Blech Seite 2 von 2" not in cleaned
    assert "IT-Blech Startprobleme nach Update" not in cleaned
    assert cleaned.count("1.1 Start") == 1
    assert "1.1 Start" in cleaned
    assert "1.2 Lösung" in cleaned


def test_infer_pdf_title_uses_first_meaningful_line():
    text = "\n\nIT-Blech Startprobleme nach Update\n1.1 Start\n"

    assert _infer_pdf_title(text) == "IT-Blech Startprobleme nach Update"


def test_force_ocr_runs_even_when_page_has_embedded_text():
    assert _should_ocr_pdf_page(
        _PageWithImages(has_images=False),
        "Some selectable text",
        ocr_enabled=True,
        force_ocr=True,
        page_num=20,
        max_ocr_pages=3,
        min_text_chars_for_ocr=80,
    )


def test_default_ocr_runs_for_sparse_image_heavy_page_only_within_limits():
    assert _should_ocr_pdf_page(
        _PageWithImages(has_images=True),
        "Header",
        ocr_enabled=True,
        force_ocr=False,
        page_num=1,
        max_ocr_pages=3,
        min_text_chars_for_ocr=80,
    )
    assert not _should_ocr_pdf_page(
        _PageWithImages(has_images=True),
        "Header",
        ocr_enabled=True,
        force_ocr=False,
        page_num=4,
        max_ocr_pages=3,
        min_text_chars_for_ocr=80,
    )


def test_pdf_ocr_merge_skips_duplicate_text_but_keeps_distinct_text():
    assert not _is_distinct_pdf_ocr_text(
        "The application starts after update",
        "The application starts after update",
    )
    assert _is_distinct_pdf_ocr_text(
        "The application starts after update",
        "Screenshot error code E315512812",
    )
