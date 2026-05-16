from dataclasses import dataclass
from pathlib import Path
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


@dataclass(slots=True)
class ExtractionResult:
    success: bool
    text: str
    error: str | None = None


def extract_text(path: Path) -> ExtractionResult:
    """Extract comparable text and preserve extraction failures for callers."""
    ext = path.suffix.lower()

    try:
        if ext == ".docx":
            result = _extract_docx(path)
            text = result.get("text", "") if isinstance(result, dict) else result
            return ExtractionResult(success=True, text=str(text or ""))
        if ext == ".pdf":
            result = _extract_pdf(str(path))
            text = result.get("text", "") if isinstance(result, dict) else result
            return ExtractionResult(success=True, text=str(text or ""))
        if ext == ".odt":
            return ExtractionResult(success=True, text=str(_extract_odt(path) or ""))
        if ext == ".pptx":
            return ExtractionResult(success=True, text=str(_extract_pptx(path) or ""))
        if ext == ".epub":
            return ExtractionResult(success=True, text=str(_extract_epub(path) or ""))
        if ext == ".xlsx":
            return ExtractionResult(success=True, text=str(_extract_xlsx(path) or ""))
        if ext in {".html", ".htm"}:
            return ExtractionResult(success=True, text=str(_extract_html(path) or ""))
        if ext == ".xml":
            # Use the structured tree view instead of flattening the preview table.
            summary, tree_str, _df_preview = summarize_generic_xml(str(path), show_tree=True)
            if "error" in summary:
                return ExtractionResult(
                    success=False,
                    text="",
                    error=f"{path}: {summary['error']}",
                )
            return ExtractionResult(success=True, text=tree_str)

        # fallback: try plain text
        return ExtractionResult(
            success=True,
            text=path.read_text(encoding="utf-8", errors="ignore"),
        )

    except Exception as exc:
        return ExtractionResult(success=False, text="", error=f"{path}: {exc}")
