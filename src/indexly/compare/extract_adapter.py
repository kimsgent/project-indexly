from pathlib import Path
from typing import Optional
from ..extract_utils import (
    _extract_docx,
    _extract_pdf,
    _extract_odt,
    _extract_pptx,
    _extract_epub,
    _extract_xlsx,
    _extract_html,
)
from ..analyze_xml import summarize_generic_xml


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()

    try:
        if ext == ".docx":
            return _extract_docx(path)
        if ext == ".pdf":
            result = _extract_pdf(path)
            return result.get("text", "") if isinstance(result, dict) else result
        if ext == ".odt":
            return _extract_odt(path)
        if ext == ".pptx":
            return _extract_pptx(path)
        if ext == ".epub":
            return _extract_epub(path)
        if ext == ".xlsx":
            return _extract_xlsx(path)
        if ext in {".html", ".htm"}:
            return _extract_html(path)
        if ext == ".xml":
            # Use analyze_xml.py to normalize XML content for comparison
            summary, tree_str, df_preview = summarize_generic_xml(str(path), show_tree=False)
            # flatten preview DataFrame to string
            lines = [" | ".join(str(v) for v in row) for _, row in df_preview.iterrows()]
            return "\n".join(lines)

        # fallback: try plain text
        return path.read_text(encoding="utf-8", errors="ignore")

    except Exception:
        return ""
