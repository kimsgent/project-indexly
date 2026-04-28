from indexly import extract_utils


class _FakePixmap:
    def tobytes(self, fmt):
        return b"fake-image"


class _FakePage:
    def __init__(self, text="", images=False):
        self._text = text
        self._images = images

    def get_text(self, kind):
        assert kind == "text"
        return self._text

    def get_images(self, full=True):
        assert full is True
        return [object()] if self._images else []

    def get_pixmap(self, dpi=200):
        return _FakePixmap()


class _FakeDoc:
    metadata = {}

    def __init__(self, pages):
        self.pages = pages

    def __len__(self):
        return len(self.pages)

    def __iter__(self):
        return iter(self.pages)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeFitz:
    def __init__(self, doc):
        self.doc = doc

    def open(self, path):
        return self.doc


class _FakeImageHandle:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeImage:
    @staticmethod
    def open(stream):
        return _FakeImageHandle()


class _FakeTesseract:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def image_to_string(self, img, lang):
        self.calls += 1
        return self.outputs.pop(0)


def _patch_pdf_dependencies(monkeypatch, pages, ocr_outputs):
    tesseract = _FakeTesseract(ocr_outputs)
    fitz = _FakeFitz(_FakeDoc(pages))

    def fake_require(module_name, package_name, extra_name):
        if module_name == "fitz":
            return fitz
        if module_name == "pytesseract":
            return tesseract
        if module_name == "PIL.Image":
            return _FakeImage
        raise AssertionError(module_name)

    monkeypatch.setattr(extract_utils, "require_extra_dependency", fake_require)
    monkeypatch.setattr(extract_utils.os.path, "getsize", lambda path: 1024)
    monkeypatch.setattr(extract_utils, "store_metadata", lambda path, metadata: None)
    return tesseract


def _sample_pdf_path(tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.7")
    return str(path)


def test_force_ocr_runs_even_when_pdf_page_has_embedded_text(monkeypatch, tmp_path):
    tesseract = _patch_pdf_dependencies(
        monkeypatch,
        [_FakePage("Embedded text", images=True)],
        ["Embedded text Extra scanned label"],
    )

    result = extract_utils._extract_pdf(_sample_pdf_path(tmp_path), force_ocr=True)

    assert tesseract.calls == 1
    assert "Embedded text" in result["text"]
    assert "Extra scanned label" in result["text"]


def test_default_ocr_supplements_sparse_image_heavy_pages(monkeypatch, tmp_path):
    tesseract = _patch_pdf_dependencies(
        monkeypatch,
        [
            _FakePage("Short", images=True),
            _FakePage(
                "This page already has enough embedded text to index well without "
                "running OCR for the same page.",
                images=True,
            ),
        ],
        ["Short Scanned form field"],
    )

    result = extract_utils._extract_pdf(_sample_pdf_path(tmp_path))

    assert tesseract.calls == 1
    assert "Scanned form field" in result["text"]
    assert "enough embedded text" in result["text"]


def test_no_ocr_never_loads_ocr_dependencies(monkeypatch, tmp_path):
    fitz = _FakeFitz(_FakeDoc([_FakePage("", images=True)]))

    def fake_require(module_name, package_name, extra_name):
        if module_name == "fitz":
            return fitz
        raise AssertionError(f"OCR dependency should not load: {module_name}")

    monkeypatch.setattr(extract_utils, "require_extra_dependency", fake_require)
    monkeypatch.setattr(extract_utils.os.path, "getsize", lambda path: 1024)
    monkeypatch.setattr(extract_utils, "store_metadata", lambda path, metadata: None)

    result = extract_utils._extract_pdf(_sample_pdf_path(tmp_path), ocr_enabled=False)

    assert result["text"] == ""


def test_duplicate_ocr_text_is_not_added_twice(monkeypatch, tmp_path):
    _patch_pdf_dependencies(
        monkeypatch,
        [_FakePage("Embedded text only", images=True)],
        ["Embedded text only"],
    )

    result = extract_utils._extract_pdf(_sample_pdf_path(tmp_path), force_ocr=True)

    assert result["text"].count("Embedded text only") == 1
