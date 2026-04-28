"""
📄 extract_utils.py

Purpose:
    Contains file-type specific text extractors (DOCX, EML, MSG).

Key Features:
    - _extract_docx(): Parses Word documents and extracts text and tables.
    - _extract_eml(): Parses .eml email files using eml_parser.
    - _extract_msg(): Parses .msg Outlook files using extract_msg.
    - Each extractor also supports virtual tag detection via fts_core.

Usage:
    Called by `filetype_utils.py -> extract_text_from_file()` during indexing.
"""

# --- stdlib (safe) ---
import io
import re
import os
import json
import logging
import sqlite3
import shutil
import platform
from datetime import datetime
from collections import OrderedDict
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from .optional_deps import require_extra_dependency

# ---------------------------------------------------------------------
# External tool checks (boolean-returning for doctor / programmatic use)
# ---------------------------------------------------------------------
def check_exiftool_available() -> bool:
    """Return True if ExifTool is in PATH, else False"""
    return shutil.which("exiftool") is not None


def check_tesseract_available() -> bool:
    """Return True if Tesseract OCR is in PATH, else False"""
    return shutil.which("tesseract") is not None


def print_external_tools_info():
    """Existing print-based behavior (optional, for CLI)"""
    if not check_exiftool_available():
        print("⚠️ ExifTool not found. Install: https://exiftool.org/")

    if not check_tesseract_available():
        os_name = platform.system().lower()
        print("⚠️ Tesseract OCR not found. Install:")
        if "windows" in os_name:
            print("  choco install tesseract OR winget install tesseract")
        elif "darwin" in os_name:
            print("  brew install tesseract")
        elif "linux" in os_name:
            print("  sudo apt install tesseract-ocr")


# --- internal imports (unchanged) ---
from .config import DB_FILE, SEMANTIC_METADATA_KEYS
from .path_utils import normalize_path


_EMAIL_BOILERPLATE_FALLBACKS = [
    r"^\s*mit freundlichen gr[üu]ßen\b",
    r"^\s*freundliche gr[üu]ße\b",
    r"^\s*best regards\b",
    r"^\s*kind regards\b",
    r"^\s*_{5,}\s*$",
    r"^\s*-{5,}\s*$",
    r"^\s*von:\s",
    r"^\s*from:\s",
    r"^\s*gesendet:\s",
    r"^\s*sent:\s",
    r"^\s*this email and any attachments are confidential\b",
    r"^\s*please consider the environment before printing\b",
]

_DOCX_KEY_ALIASES = {
    "autor": "author",
    "author": "author",
    "erstellt von": "author",
    "created by": "author",
    "titel": "title",
    "title": "title",
    "dokument": "title",
    "dokumenttitel": "title",
    "betreff": "subject",
    "subject": "subject",
    "thema": "subject",
    "problem": "subject",
    "beschreibung": "subject",
    "erstellt am": "created",
    "created": "created",
    "created at": "created",
    "datum": "created",
    "geaendert am": "last_modified",
    "geändert am": "last_modified",
    "modified": "last_modified",
    "last modified": "last_modified",
    "zuletzt geändert von": "last_modified_by",
    "last modified by": "last_modified_by",
}

_DOCX_CANONICAL_TABLE_KEYS = {
    "kunde": "Kunde",
    "key-nr": "Key-Nr",
    "key nr": "Key-Nr",
    "call-nr": "Call-Nr",
    "call nr": "Call-Nr",
    "key-nr / call-nr": "Key-Nr",
    "key nr / call nr": "Key-Nr",
    "erstellt von": "Erstellt von",
    "erstellt am": "Erstellt am",
    "bereich": "Bereich",
    "version kunde": "Version Kunde",
    "version bletec": "Version BleTec",
    "patch": "Patch",
    "problem": "Problem",
    "bt-auftrags-nr": "BT-Auftrags-Nr",
    "kd geprüft von": "KD Geprüft von",
    "kd geprueft von": "KD Geprüft von",
    "kd geprüft am": "KD Geprüft am",
    "kd geprueft am": "KD Geprüft am",
    "email am": "eMail am",
    "bt-priorität": "BT-Priorität",
    "bt-prioritaet": "BT-Priorität",
    "kunde-priorität": "Kunde-Priorität",
    "kunde-prioritaet": "Kunde-Priorität",
}

_DOCX_BODY_TABLE_KEYS = {
    "problem",
    "beschreibung",
    "lösung",
    "loesung",
    "hinweis",
    "notiz",
    "bemerkung",
}

_DOCX_TAG_SKIP_KEYS = {
    "Problem",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")

_GENERIC_PDF_TITLES = {"", "title", "titel", "untitled", "document", "dokument"}
_PDF_PAGE_MARKER_RE = re.compile(
    r"^(?:seite|page)\s+\d+\s+(?:von|of|/)\s+\d+$",
    re.IGNORECASE,
)
_PDF_PAGE_MARKER_ANY_RE = re.compile(
    r"\b(?:seite|page)\s+\d+\s+(?:von|of|/)\s+\d+\b",
    re.IGNORECASE,
)


def _clean_docx_text(value) -> str:
    """Normalize Word text while keeping content readable."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)
    text = re.sub(r"[\u00a0\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \u2013-").strip()


def _normalize_docx_key(value: str) -> str:
    key = _clean_docx_text(value).lower()
    key = key.replace("‐", "-").replace("–", "-").replace("—", "-")
    key = key.replace(".", "").replace(":", "")
    key = re.sub(r"\s*/\s*", " / ", key)
    key = re.sub(r"\s+", " ", key)
    return key.strip()


def _canonical_docx_table_key(value: str) -> str:
    key = _normalize_docx_key(value)
    if key in _DOCX_CANONICAL_TABLE_KEYS:
        return _DOCX_CANONICAL_TABLE_KEYS[key]
    for prefix, canonical in _DOCX_CANONICAL_TABLE_KEYS.items():
        if key.startswith(prefix + " /") or key.startswith(prefix + " "):
            return canonical
    return _clean_docx_text(value)


def _clean_docx_table_value(value: str) -> str:
    text = _clean_docx_text(value)
    text = re.sub(r"^[\\/|:;\-\s]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :;/-")


def _is_docx_table_key(value: str) -> bool:
    text = _clean_docx_text(value)
    if not text or len(text) > 80:
        return False
    normalized = _normalize_docx_key(text)
    return (
        text.endswith(":")
        or normalized in _DOCX_CANONICAL_TABLE_KEYS
        or normalized in _DOCX_KEY_ALIASES
    )


def _dedupe_consecutive(values: list[str]) -> list[str]:
    deduped = []
    previous = object()
    for value in values:
        if value != previous:
            deduped.append(value)
        previous = value
    return deduped


def _extract_docx_table_metadata(doc) -> OrderedDict[str, str]:
    metadata = OrderedDict()

    for table in doc.tables:
        for row in table.rows:
            cells = _dedupe_consecutive([_clean_docx_text(cell.text) for cell in row.cells])

            for index, cell_text in enumerate(cells[:-1]):
                if not _is_docx_table_key(cell_text):
                    continue

                value = _clean_docx_table_value(cells[index + 1])
                if not value or _is_docx_table_key(value):
                    continue

                key = _canonical_docx_table_key(cell_text)
                if key and value and key not in metadata:
                    metadata[key] = value

    return metadata


def _docx_table_metadata_for_structured_storage(
    table_metadata: OrderedDict[str, str],
) -> dict:
    metadata = {"format": "DOCX"}

    for key, value in table_metadata.items():
        mapped_key = _DOCX_KEY_ALIASES.get(_normalize_docx_key(key))
        if mapped_key and value and mapped_key not in metadata:
            metadata[mapped_key] = value

    return metadata


def _is_noisy_docx_line(line: str) -> bool:
    normalized = _clean_docx_text(line)
    if not normalized:
        return True
    if re.fullmatch(r"[\W_]+", normalized):
        return True
    if re.fullmatch(r"\d{1,4}", normalized):
        return True
    if re.fullmatch(r"seite\s+\d+\s+(von|/)\s+\d+", normalized, re.IGNORECASE):
        return True
    return False


def _dedupe_repeated_docx_lines(lines: list[str]) -> list[str]:
    seen = set()
    cleaned = []

    for line in lines:
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)

    return cleaned


def _extract_docx(path):
    from .fts_core import extract_virtual_tags
    docx = require_extra_dependency("docx", "python-docx", "documents")

    doc = docx.Document(path)

    table_metadata = _extract_docx_table_metadata(doc)
    metadata = _docx_table_metadata_for_structured_storage(table_metadata)

    paragraphs = [
        _clean_docx_text(p.text)
        for p in doc.paragraphs
        if not _is_noisy_docx_line(p.text)
    ]

    table_body_lines = []
    for key, value in table_metadata.items():
        if _normalize_docx_key(key) in _DOCX_BODY_TABLE_KEYS and value:
            table_body_lines.append(value)

    full_text = "\n".join(
        _dedupe_repeated_docx_lines([*table_body_lines, *paragraphs])
    )

    tag_meta = {
        key: value
        for key, value in table_metadata.items()
        if key not in _DOCX_TAG_SKIP_KEYS
    }
    extract_virtual_tags(path, text=full_text, meta=tag_meta)
    return {"text": full_text, "metadata": metadata}


# safe_get helper for .msg and.eml to clean stings


def safe_get(obj, key, fallback=""):
    """Safe getter for dicts, objects, and lists with fallback."""
    try:
        if isinstance(obj, dict):
            value = obj.get(key, fallback)
        else:
            value = getattr(obj, key, fallback)

        if value is None:
            return fallback
        if isinstance(value, (list, tuple)):
            return ", ".join(map(str, value))
        return str(value)
    except Exception:
        return fallback


def _clean_email_text(value) -> str:
    text = safe_get({"value": value}, "value", "")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00a0\r\n\t]+", " ", text)
    text = re.sub(r"<mailto:[^>]+>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"mailto:", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_email_party(value) -> str:
    text = _clean_email_text(value).strip("'\" ")
    if not text:
        return ""

    emails = _EMAIL_RE.findall(text)
    if not emails:
        return text

    email = emails[-1].lower()
    display = re.sub(r"<[^>]*>", " ", text)
    display = _EMAIL_RE.sub(" ", display)
    display = display.replace("'", " ").replace('"', " ")
    display = re.sub(r"\s+", " ", display).strip(" ,;")

    if display and display.casefold() != email.casefold():
        return f"{display} <{email}>"
    return email


def _email_cutoff_patterns() -> list[re.Pattern]:
    try:
        from .config import EMAIL_BOILERPLATE_CUTOFFS
        patterns = EMAIL_BOILERPLATE_CUTOFFS or _EMAIL_BOILERPLATE_FALLBACKS
    except Exception:
        patterns = _EMAIL_BOILERPLATE_FALLBACKS

    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            continue
    return compiled


def _clean_email_body(value) -> str:
    text = safe_get({"value": value}, "value", "")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00a0\t]+", " ", text)
    text = re.sub(r"<mailto:[^>]+>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"mailto:", "", text, flags=re.IGNORECASE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ""

    lines = []
    candidates = text.splitlines() if "\n" in text else re.split(r"(?<=\.)\s+", text)
    cutoff_patterns = _email_cutoff_patterns()
    for raw_line in candidates:
        line = _clean_email_text(raw_line)
        if not line:
            continue
        if any(pattern.search(line) for pattern in cutoff_patterns):
            break
        lines.append(line)

    cleaned = " ".join(lines) if lines else text
    cleaned = re.sub(r"<https?://[^>]+>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_msg(path):
    from .fts_core import extract_virtual_tags

    logging.getLogger("extract_msg").setLevel(logging.ERROR)
    extract_msg = require_extra_dependency("extract_msg", "extract_msg", "documents")

    try:
        msg = extract_msg.Message(path)

        subject = safe_get(msg, "subject", "(no subject)")
        sender = _normalize_email_party(safe_get(msg, "sender", "(unknown sender)"))
        to = _normalize_email_party(safe_get(msg, "to", ""))
        date = safe_get(msg, "date", "")
        # Prioritize plain > RTF > HTML body
        body = (
            safe_get(msg, "body")
            or safe_get(msg, "bodyRTF")
            or safe_get(msg, "bodyHTML")
        )
        body = _clean_email_body(body)

        meta = {
            "From": sender,
            "To": to,
            "Subject": _clean_email_text(subject),
            "Date": _clean_email_text(date),
        }
        extract_virtual_tags(path, meta=meta)

        metadata = {
            "format": "MSG",
            "author": sender,
            "subject": meta["Subject"],
            "created": meta["Date"],
        }

        return {"text": body, "metadata": metadata}
    except Exception as e:
        print(f"❌ Failed to extract .msg: {e}")
        return ""


def _extract_eml_body(parsed: dict) -> str:
    body = parsed.get("body", "")
    if isinstance(body, list):
        parts = []
        for item in body:
            if isinstance(item, dict):
                parts.append(
                    safe_get(item, "content")
                    or safe_get(item, "body")
                    or safe_get(item, "text")
                )
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(body, dict):
        return safe_get(body, "content") or safe_get(body, "body") or safe_get(body, "text")
    return safe_get(parsed, "body", "")


def _extract_eml(path):
    from .fts_core import extract_virtual_tags
    eml_parser = require_extra_dependency("eml_parser", "eml-parser", "documents")

    try:
        with open(path, "rb") as f:
            raw_email = f.read()

        ep = eml_parser.EmlParser()
        parsed = ep.decode_email_bytes(raw_email)

        header = parsed.get("header", {})
        subject = safe_get(header, "subject", "(no subject)")
        sender = _normalize_email_party(safe_get(header, "from", ["(unknown sender)"]))
        to = _normalize_email_party(safe_get(header, "to", []))
        date = safe_get(header, "date", "(no date)")
        body = _clean_email_body(_extract_eml_body(parsed))

        meta = {
            "From": sender,
            "To": to,
            "Subject": _clean_email_text(subject),
            "Date": _clean_email_text(date),
        }
        extract_virtual_tags(path, meta=meta)

        metadata = {
            "format": "EML",
            "author": sender,
            "subject": meta["Subject"],
            "created": meta["Date"],
        }

        return {"text": body, "metadata": metadata}
    except Exception as e:
        print(f"❌ Failed to extract .eml: {e}")
        return ""


def _extract_pptx(path):
    Presentation = require_extra_dependency(
        "pptx", "python-pptx", "documents"
    ).Presentation
    try:
        prs = Presentation(path)
        text = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text.append(shape.text)
        return "\n".join(text)
    except Exception as e:
        print(f"❌ Failed to extract .pptx: {e}")
        return ""


def _extract_epub(path):
    epub = require_extra_dependency("ebooklib.epub", "ebooklib", "documents")
    try:
        book = epub.read_epub(path)
        text = []
        for item in book.get_items():
            if item.get_type() == epub.EpubHtml:
                soup = BeautifulSoup(item.get_body_content(), "html.parser")
                text.append(soup.get_text())
        return "\n".join(text)
    except Exception as e:
        print(f"❌ Failed to extract .epub: {e}")
        return ""


def _extract_odt(path):
    load = require_extra_dependency("odf.opendocument", "odfpy", "documents").load
    P = require_extra_dependency("odf.text", "odfpy", "documents").P
    try:
        doc = load(path)
        text = []
        for elem in doc.getElementsByType(P):
            if elem.firstChild:
                text.append(str(elem.firstChild.data))
        return "\n".join(text)
    except Exception as e:
        print(f"❌ Failed to extract .odt: {e}")
        return ""


def _extract_xlsx(path):
    openpyxl = require_extra_dependency("openpyxl", "openpyxl", "documents")
    wb = openpyxl.load_workbook(path, data_only=True)
    text = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            row_text = " ".join([str(cell) for cell in row if cell is not None])
            if row_text.strip():
                text.append(row_text)
    return "\n\n".join(text)


def _clean_pdf_line(value: str) -> str:
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00a0\r\t]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_noise_pdf_line(line: str) -> bool:
    if not line:
        return True
    if _PDF_PAGE_MARKER_RE.match(line):
        return True
    if len(line) <= 100 and _PDF_PAGE_MARKER_ANY_RE.search(line):
        return True
    if re.fullmatch(r"\d{1,4}", line):
        return True
    return False


def _clean_pdf_text_pages(text_pages: list[str]) -> str:
    page_lines = []
    repeated_candidates = {}

    for page in text_pages:
        lines = [
            _clean_pdf_line(line)
            for line in str(page or "").splitlines()
            if not _is_noise_pdf_line(_clean_pdf_line(line))
        ]
        page_lines.append(lines)

        seen_on_page = set()
        edge_lines = lines[:4] + lines[-4:]
        for line in edge_lines:
            if not line or len(line) > 120:
                continue
            if line in seen_on_page:
                continue
            repeated_candidates[line] = repeated_candidates.get(line, 0) + 1
            seen_on_page.add(line)

    repeat_threshold = max(2, len(page_lines) // 2 + 1)
    repeated = {
        line
        for line, count in repeated_candidates.items()
        if count >= repeat_threshold and len(line.split()) <= 8
    }

    cleaned_pages = []
    for lines in page_lines:
        cleaned = []
        seen_on_page = set()
        for line in lines:
            if line in repeated or line in seen_on_page:
                continue
            cleaned.append(line)
            seen_on_page.add(line)
        if cleaned:
            cleaned_pages.append("\n".join(cleaned))

    full_text = "\n\n".join(cleaned_pages)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    return full_text.strip()


def _infer_pdf_title(full_text: str) -> str | None:
    for line in full_text.splitlines():
        line = _clean_pdf_line(line)
        if not line:
            continue
        if _PDF_PAGE_MARKER_RE.match(line):
            continue
        if len(line) < 4 or re.fullmatch(r"\d+(?:\.\d+)*", line):
            continue
        return line[:180]
    return None


def _pdf_page_has_images(page) -> bool:
    try:
        return bool(page.get_images(full=True))
    except Exception:
        try:
            return bool(page.get_image_info())
        except Exception:
            return False


def _should_ocr_pdf_page(
    page,
    page_text: str,
    *,
    ocr_enabled: bool,
    force_ocr: bool,
    page_num: int,
    max_ocr_pages: int,
    min_text_chars_for_ocr: int,
) -> bool:
    if not ocr_enabled:
        return False
    if force_ocr:
        return True
    if page_num > max_ocr_pages:
        return False

    cleaned_text = _clean_pdf_line(page_text)
    if not cleaned_text:
        return True

    return len(cleaned_text) < min_text_chars_for_ocr and _pdf_page_has_images(page)


def _normalize_pdf_compare_text(value: str) -> str:
    tokens = re.findall(r"\w{3,}", str(value or "").casefold())
    return " ".join(tokens)


def _is_distinct_pdf_ocr_text(page_text: str, ocr_text: str) -> bool:
    ocr_norm = _normalize_pdf_compare_text(ocr_text)
    if not ocr_norm:
        return False

    page_norm = _normalize_pdf_compare_text(page_text)
    if not page_norm:
        return True

    if len(ocr_norm) >= 40 and ocr_norm in page_norm:
        return False
    if len(page_norm) >= 40 and page_norm in ocr_norm:
        return True

    similarity = SequenceMatcher(None, page_norm[:2000], ocr_norm[:2000]).ratio()
    return similarity < 0.86


def _ocr_pdf_page(page, pytesseract, Image, *, dpi: int, lang: str) -> str:
    pix = page.get_pixmap(dpi=dpi)
    with Image.open(io.BytesIO(pix.tobytes("png"))) as img:
        ocr_text = pytesseract.image_to_string(img, lang=lang)
    return ocr_text.strip() if ocr_text else ""


def _extract_pdf(
    path: str,
    ocr_enabled: bool = True,
    force_ocr: bool = False,
    lang: str = "deu+eng",
    max_ocr_pages: int = 3,
    max_pages_for_ocr: int = 10,
    max_size_for_ocr_mb: float = 50.0,
    min_text_chars_for_ocr: int = 80,
    ocr_dpi: int = 200,
):
    """
    Extract text and metadata from a PDF file.
    Uses PyMuPDF (fitz) for text, with OCR fallback for image-only or sparse image-heavy pages.
    With force_ocr=True, OCR is run for every page and merged with embedded text.
    Stores extracted metadata into file_metadata table.
    Smart OCR: skips OCR for large PDFs automatically unless force_ocr=True.
    """
    text_pages = []
    metadata = {
        "title": None,
        "author": None,
        "subject": None,
        "created": None,
        "last_modified": None,
        "last_modified_by": None,
        "camera": None,
        "image_created": None,
        "dimensions": None,
        "format": "PDF",
        "gps": None,
    }

    try:
        fitz = require_extra_dependency("fitz", "pymupdf", "documents")
        pytesseract = None
        Image = None
        file_size_mb = os.path.getsize(path) / (1024 * 1024)

        with fitz.open(path) as doc:
            num_pages = len(doc)

            # --- Extract metadata from PDF info dictionary ---
            pdf_info = doc.metadata or {}
            metadata.update(
                {
                    "title": pdf_info.get("title"),
                    "author": pdf_info.get("author"),
                    "subject": pdf_info.get("subject"),
                    "created": _normalize_pdf_date(pdf_info.get("creationDate")),
                    "last_modified": _normalize_pdf_date(pdf_info.get("modDate")),
                    "last_modified_by": pdf_info.get("creator")
                    or pdf_info.get("producer"),
                }
            )

            # --- Smart OCR decision ---
            if not ocr_enabled:
                ocr_enabled = False

            elif not force_ocr and (
                num_pages > max_pages_for_ocr or file_size_mb > max_size_for_ocr_mb
            ):
                ocr_enabled = False
                print(
                    f"Skipping OCR for large PDF "
                    f"({num_pages} pages, {file_size_mb:.1f} MB): {path}"
                )

            elif force_ocr:
                print(f"OCR enabled (forced): {path}")

            # --- Page text + OCR fallback/merge ---
            for page_num, page in enumerate(doc, start=1):
                page_text = page.get_text("text")
                page_parts = []

                if page_text.strip():
                    page_parts.append(page_text.strip())

                should_ocr = _should_ocr_pdf_page(
                    page,
                    page_text,
                    ocr_enabled=ocr_enabled,
                    force_ocr=force_ocr,
                    page_num=page_num,
                    max_ocr_pages=max_ocr_pages,
                    min_text_chars_for_ocr=min_text_chars_for_ocr,
                )

                if should_ocr:
                    if pytesseract is None:
                        pytesseract = require_extra_dependency(
                            "pytesseract", "pytesseract", "documents"
                        )
                    if Image is None:
                        Image = require_extra_dependency("PIL.Image", "Pillow", "documents")

                    reason = "forced" if force_ocr else "fallback"
                    print(f"OCR page {page_num}/{num_pages} ({reason}): {path}")

                    try:
                        ocr_text = _ocr_pdf_page(
                            page,
                            pytesseract,
                            Image,
                            dpi=ocr_dpi,
                            lang=lang,
                        )
                        if _is_distinct_pdf_ocr_text(page_text, ocr_text):
                            page_parts.append(ocr_text)
                    except Exception as e:
                        print(f"OCR failed page {page_num}: {e}")

                text_pages.append("\n".join(part for part in page_parts if part))

            # --- Fallback to filesystem timestamps ---
            stat = os.stat(path)
            metadata.setdefault(
                "created", datetime.fromtimestamp(stat.st_ctime).isoformat()
            )
            metadata.setdefault(
                "last_modified", datetime.fromtimestamp(stat.st_mtime).isoformat()
            )

            # --- Store metadata in DB ---
            store_metadata(path, metadata)

            # --- Return cleaned text and metadata ---
            raw_pdf_text = "\n\n".join(text_pages)
            full_text = _clean_pdf_text_pages(text_pages)
            title = _clean_email_text(metadata.get("title"))
            if title.casefold() in _GENERIC_PDF_TITLES:
                metadata["title"] = _infer_pdf_title(raw_pdf_text) or _infer_pdf_title(
                    full_text
                )
            return {"text": full_text, "metadata": metadata}

    except RuntimeError:
        raise
    except Exception as e:
        print(f"Error extracting text from {path}: {e}")
        return {"text": "", "metadata": metadata}


def _normalize_pdf_date(date_str):
    """Normalize PDF date strings like 'D:20240512143000Z' to ISO 8601."""
    if not date_str:
        return None
    try:
        date_str = date_str.strip()
        if date_str.startswith("D:"):
            date_str = date_str[2:]
        # Remove timezone or trailing junk
        date_str = date_str.rstrip("Z").split("+")[0].split("-")[0]
        # Parse common PDF formats
        return datetime.strptime(date_str[:14], "%Y%m%d%H%M%S").isoformat()
    except Exception:
        return None


def _extract_html(path):

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # Remove scripts, styles, hidden navs
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()

    # Title
    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Extract headings and paragraphs
    elements = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p"]):
        txt = tag.get_text(" ", strip=True)
        if txt:
            elements.append(txt)

    combined = f"{title}\n" + "\n".join(elements)
    combined = re.sub(r"\s+", " ", combined)  # collapse whitespace
    return combined.strip()


def store_metadata(path, metadata):
    from .db_utils import connect_db

    if not metadata:
        return
    conn = connect_db()
    cursor = conn.cursor()
    columns = [
        "title",
        "author",
        "subject",
        "created",
        "last_modified",
        "last_modified_by",
        "camera",
        "image_created",
        "dimensions",
        "format",
        "gps",
    ]
    values = [metadata.get(col) for col in columns]
    cursor.execute(
        f"""
        INSERT OR REPLACE INTO file_metadata (path, {', '.join(columns)})
        VALUES (?, {', '.join(['?']*len(columns))})
    """,
        [path] + values,
    )
    conn.commit()
    conn.close()


def _gps_to_decimal(coord, ref):
    try:
        d, m, s = coord

        def to_float(x):
            if hasattr(x, "numerator") and hasattr(x, "denominator"):  # IFDRational
                return float(x.numerator) / float(x.denominator)
            elif isinstance(x, tuple):  # (num, den)
                return float(x[0]) / float(x[1])
            elif isinstance(x, (int, float)):  # already float
                return float(x)
            else:
                print(f"⚠️ Unknown EXIF GPS format: {x} ({type(x)})")
                return 0.0

        val = to_float(d) + to_float(m) / 60.0 + to_float(s) / 3600.0
        return -val if ref in ("S", "W") else val

    except Exception as e:
        print(f"⚠️ Failed to parse GPS coord {coord}: {e}")
        return None


def extract_image_metadata(path: str) -> dict:
    """Extract image metadata including EXIF + GPS if present."""
    Image = require_extra_dependency("PIL.Image", "Pillow", "documents")
    ExifTags = require_extra_dependency("PIL.ExifTags", "Pillow", "documents")
    md = {}
    try:
        with Image.open(path) as img:
            md["dimensions"] = f"{img.width}x{img.height}"
            md["format"] = img.format

            exif = img._getexif()
            if exif:
                exif_data = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                md["camera"] = exif_data.get("Model") or None
                md["image_created"] = exif_data.get("DateTimeOriginal") or None
                md["title"] = exif_data.get("ImageDescription") or None
                md["author"] = exif_data.get("Artist") or None

                gps = exif_data.get("GPSInfo")
                if isinstance(gps, dict):
                    gps_tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
                    lat = lon = None
                    if all(
                        k in gps_tags
                        for k in (
                            "GPSLatitude",
                            "GPSLatitudeRef",
                            "GPSLongitude",
                            "GPSLongitudeRef",
                        )
                    ):
                        lat = _gps_to_decimal(
                            gps_tags["GPSLatitude"], gps_tags["GPSLatitudeRef"]
                        )
                        lon = _gps_to_decimal(
                            gps_tags["GPSLongitude"], gps_tags["GPSLongitudeRef"]
                        )
                        md["gps"] = f"{lat:.6f},{lon:.6f}"

        stat = os.stat(path)
        md.setdefault("created", datetime.fromtimestamp(stat.st_ctime).isoformat())
        md.setdefault(
            "last_modified", datetime.fromtimestamp(stat.st_mtime).isoformat()
        )
    except Exception as e:
        print(f"⚠️ Failed to extract image metadata: {path} ({e})")
    return md


def update_file_metadata(
    file_path: str,
    metadata: dict,
    conn: sqlite3.Connection | None = None,
) -> str:
    """
    Update the file_metadata table with structured columns and a full JSON column.
    Returns Tier-2-only semantic text (for FTS).

    Internal flags (e.g. content_changed) are persisted but never indexed.
    """
    if not metadata:
        return f"File:{os.path.basename(file_path)}"

    # -------------------------
    # Exclude internal / control flags from FTS semantics
    # -------------------------
    INTERNAL_KEYS = {"content_changed"}

    semantic_parts = [
        f"{k}:{v}"
        for k, v in metadata.items()
        if (
            k in SEMANTIC_METADATA_KEYS
            and k not in INTERNAL_KEYS
            and v not in (None, "", [])
        )
    ]

    semantic_text = (
        " ".join(semantic_parts)
        if semantic_parts
        else f"File:{os.path.basename(file_path)}"
    )

    # -------------------------
    # Structured columns (unchanged)
    # -------------------------
    columns = [
        "title",
        "author",
        "subject",
        "created",
        "last_modified",
        "last_modified_by",
        "camera",
        "image_created",
        "dimensions",
        "format",
        "gps",
    ]
    values = [metadata.get(col) for col in columns]

    close_conn = False
    if conn is None:
        conn = sqlite3.connect(DB_FILE)
        close_conn = True

    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT OR REPLACE INTO file_metadata
            (path, {', '.join(columns)}, metadata)
            VALUES (?, {', '.join(['?'] * len(columns))}, ?)
            """,
            [file_path, *values, json.dumps(metadata)],
        )

        if close_conn:
            conn.commit()
            conn.close()

    except sqlite3.OperationalError as e:
        print(f"⚠️ Failed to update metadata for {file_path} (SQLite error): {e}")
    except Exception as e:
        print(f"⚠️ Failed to update metadata for {file_path}: {e}")

    return semantic_text
