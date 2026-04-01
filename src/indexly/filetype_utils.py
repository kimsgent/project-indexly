"""
📄 filetype_utils.py

Purpose:
    Determines supported filetypes and dispatches extraction logic.

Key Features:
    - SUPPORTED_EXTENSIONS(): provides lists of extensions support and can be extended.
    - extract_text_from_file(): Delegates to specific extractors in extract_utils.

Usage:
    Called during file indexing in `indexly.py` or `fts_core.py`.
"""

"""
filetype_utils.py

Central place for supported file types and extraction.
"""

import os
import importlib.util
from pathlib import Path
from .extract_utils import (
    _extract_docx,
    _extract_msg,
    _extract_eml,
    _extract_html,
    _extract_pdf,
    _extract_xlsx,
    _extract_epub,
    _extract_odt,
    _extract_pptx,
    extract_image_metadata,
)
from .utils import clean_text

# ✅ Single source of truth
SUPPORTED_EXTENSIONS = {
    ".txt",
    ".json",
    ".md",
    ".xml",
    ".docx",
    ".xlsx",
    ".pdf",
    ".py",
    ".html",
    ".htm",
    ".csv",
    ".log",
    ".js",
    ".css",
    ".msg",
    ".eml",
    ".pptx",
    ".epub",
    ".odt",
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".bmp",
    ".mtw",
}


DOCUMENT_DEPENDENCY_MAP = {
    ".pdf": [("fitz", "pymupdf"), ("pytesseract", "pytesseract"), ("PIL", "Pillow")],
    ".docx": [("docx", "python-docx")],
    ".xlsx": [("openpyxl", "openpyxl")],
    ".msg": [("extract_msg", "extract_msg")],
    ".eml": [("eml_parser", "eml-parser")],
    ".pptx": [("pptx", "python-pptx")],
    ".epub": [("ebooklib", "ebooklib")],
    ".odt": [("odf", "odfpy")],
    ".jpg": [("PIL", "Pillow")],
    ".jpeg": [("PIL", "Pillow")],
    ".png": [("PIL", "Pillow")],
    ".bmp": [("PIL", "Pillow")],
    ".tiff": [("PIL", "Pillow")],
}


def get_missing_documents_dependencies(file_paths: list[str]) -> list[str]:
    """
    Return missing Python packages required by detected document/image file types.
    """
    required_modules: dict[str, str] = {}
    for path in file_paths:
        ext = Path(path).suffix.lower()
        for module_name, package_name in DOCUMENT_DEPENDENCY_MAP.get(ext, []):
            required_modules[module_name] = package_name

    missing_packages = []
    for module_name, package_name in required_modules.items():
        try:
            installed = importlib.util.find_spec(module_name) is not None
        except Exception:
            installed = False
        if not installed:
            missing_packages.append(package_name)

    return sorted(set(missing_packages))


def extract_text_from_file(
    file_path,
    force_ocr: bool = False,
    disable_ocr: bool = False,
):
    """
    Extract text + metadata.
    Returns: (text_content, metadata) or (None, None)
    """
    ext = Path(file_path).suffix.lower()
    raw_text = None
    metadata = None

    if ext not in SUPPORTED_EXTENSIONS:
        return None, None

    try:
        if ext in [".html", ".htm"]:
            raw_text = _extract_html(file_path)

        elif ext in [
            ".txt",
            ".md",
            ".json",
            ".xml",
            ".py",
            ".csv",
            ".log",
            ".js",
            ".css",
        ]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()

        elif ext == ".docx":
            raw_text = _extract_docx(file_path)
        elif ext == ".xlsx":
            raw_text = _extract_xlsx(file_path)
        elif ext == ".pdf":
            result = _extract_pdf(
                file_path,
                ocr_enabled=not disable_ocr,
                force_ocr=force_ocr,
            )
            raw_text = result.get("text")
            metadata = result.get("metadata")
        elif ext == ".pptx":
            raw_text = _extract_pptx(file_path)
        elif ext == ".epub":
            raw_text = _extract_epub(file_path)
        elif ext == ".odt":
            raw_text = _extract_odt(file_path)
        elif ext == ".msg":
            raw_text = _extract_msg(file_path)
        elif ext == ".eml":
            raw_text = _extract_eml(file_path)
        elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
            metadata = extract_image_metadata(file_path)
        elif ext in [".zip", ".exe", ".bin"]:
            return None, None  # skip binaries

        elif ext == ".mtw":
            from .mtw_extractor import _extract_mtw

            # Special handling for MTW
            print(f"📂 Extracting .mtw file: {file_path} ...")
            extracted_files = _extract_mtw(file_path, os.path.dirname(file_path))
            print("✅ Extraction complete. Indexing extracted contents...")

            combined_text = []
            for f in extracted_files:
                try:
                    with open(f, "r", encoding="utf-8") as ef:
                        combined_text.append(ef.read())
                except Exception as e:
                    print(f"⚠️ Failed to read extracted file {f}: {e}")

            raw_text = "\n".join(combined_text) if combined_text else ""

        text_content = clean_text(raw_text) if raw_text else None
        return text_content, metadata

    except Exception as e:
        print(f"⚠️ Error extracting text from {file_path}: {e}")
        return None, None
