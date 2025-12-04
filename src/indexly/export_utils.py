"""
📄 export_utils.py

Purpose:
    Handles exporting of search results to TXT, PDF, and JSON formats.

Key Features:
    - export_results_to_txt(): Outputs plain text.
    - export_results_to_json(): Outputs JSON with search metadata.
    - export_results_to_pdf(): Outputs styled PDF using FPDF2 with DejaVu fonts.

Usage Example:
    export_results_to_pdf(results, "output.pdf", "search term")

Used by:
    `indexly.py` for export-related CLI flags.
"""

import os
import html
import json
import logging
import pandas as pd
from typing import Any, Dict
from datetime import datetime
from fpdf import FPDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from fpdf.errors import FPDFException
from pathlib import Path
from typing import Any, Optional
from .db_utils import get_tags_for_file
from .mermaid_diagram import build_mermaid_from_schema


def export_results_to_pdf(results, search_term, output_file="search_results.pdf"):
    from .utils import safe_text, format_tags, _safe_multicell
    from . import indexly

    """
    Export results to PDF using FPDF. 
    Falls back to ReportLab if FPDF fails.
    """

    try:
        # --- FPDF Export ---
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(15, 15, 15)

        # Load fonts from assets/fonts
        font_dir = os.path.join(os.path.dirname(indexly.__file__), "assets", "fonts")
        try:
            pdf.add_font(
                "DejaVu", "", os.path.join(font_dir, "DejaVuSans.ttf"), uni=True
            )
            pdf.add_font(
                "DejaVu", "B", os.path.join(font_dir, "DejaVuSans-Bold.ttf"), uni=True
            )
            pdf.add_font(
                "DejaVu",
                "I",
                os.path.join(font_dir, "DejaVuSans-Oblique.ttf"),
                uni=True,
            )
        except Exception as e:
            print(f"❌ Failed to load fonts: {e}")
            # fallback font
            pdf.set_font("Arial", size=12)

        pdf.add_page()

        # Header
        pdf.set_font("DejaVu", "B", 14)
        pdf.cell(
            0, 10, safe_text(f"Search Results for: {search_term}"), ln=True, align="C"
        )
        pdf.set_font("DejaVu", "", 11)
        pdf.cell(
            0,
            10,
            safe_text(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            ln=True,
            align="C",
        )
        pdf.ln(10)

        for idx, row in enumerate(results, 1):
            row = dict(row)
            path = row.get("path", "Unknown file")
            snippet = row.get("snippet") or row.get("content", "")[:500]

            # File path
            pdf.set_font("DejaVu", "B", 12)
            _safe_multicell(pdf, safe_text(f"{idx}. File: {path}"), h=8)

            # Tags
            tagline = format_tags(path)
            if tagline:
                pdf.set_font("DejaVu", "I", 10)
                _safe_multicell(pdf, safe_text(tagline), h=6)

            # Snippet
            pdf.set_font("DejaVu", "", 11)
            for raw_line in snippet.splitlines():
                line = raw_line.strip()
                if line:
                    _safe_multicell(pdf, safe_text(line), h=8)

            pdf.ln(5)  # spacing

        # Save PDF
        pdf.output(output_file)
        print(f"✅ PDF saved with FPDF: {output_file}")

    except Exception as e:
        print(f"⚠️ FPDF failed ({e}); falling back to ReportLab.")
        try:
            export_results_to_pdf_reportlab(results, search_term, output_file)
        except Exception as re:
            print(f"❌ ReportLab export also failed: {re}")


def export_results_to_pdf_reportlab(results, search_term, output_file):
    from .utils import safe_text, format_tags
    from . import indexly

    """Minimal ReportLab fallback export"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(
        Paragraph(
            f"<b>Search Results for:</b> {safe_text(search_term)}", styles["Title"]
        )
    )
    story.append(Spacer(1, 12))

    for idx, row in enumerate(results, 1):
        row = dict(row)
        path = row.get("path", "Unknown file")
        snippet = row.get("snippet") or row.get("content", "")[:500]

        story.append(
            Paragraph(f"<b>{idx}. File:</b> {safe_text(path)}", styles["Heading4"])
        )
        tagline = format_tags(path)
        if tagline:
            story.append(Paragraph(safe_text(tagline), styles["Italic"]))

        for raw_line in snippet.splitlines():
            line = raw_line.strip()
            if line:
                story.append(Paragraph(safe_text(line), styles["Normal"]))

        story.append(Spacer(1, 12))

    doc.build(story)
    print(f"✅ PDF saved with ReportLab: {output_file}")


def export_results_to_txt(results, output_path, search_term):
    from .utils import get_snippets, format_tags

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for row in results:
                row = dict(row)
                f.write(f"File: {row['path']}\n")
                tagline = format_tags(row["path"])
                if tagline:
                    f.write(tagline + "\n")

                tags = get_tags_for_file(row["path"])
                if tags:
                    f.write(f"Tags: {', '.join(tags)}\n")
                raw = row.get("snippet") or row.get("content", "")
                snips = get_snippets(raw, search_term)
                snippet = snips[0] if snips else raw[:300]
                f.write(snippet.strip() + "\n\n")
        print(f"📄 TXT export complete: {output_path}")

    except Exception as e:
        print(
            f"❌ Failed to export TXT to '{output_path}' with search term '{search_term}': {type(e).__name__}: {e}"
        )


def export_results_to_json(results, output_path, search_term):
    from .utils import get_snippets

    try:
        export_data = []
        for row in results:
            row = dict(row)
            raw = row.get("snippet") or row.get("content", "")
            snips = get_snippets(raw, search_term)
            raw_snippet = snips[0] if snips else raw[:300]
            cleaned_snippet = html.escape(str(raw_snippet).strip())
            export_data.append(
                {
                    "path": row["path"],
                    "tags": get_tags_for_file(row["path"]),
                    "snippet": cleaned_snippet,
                }
            )
        with open(output_path, "w", encoding="utf-8") as f:

            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"📄 JSON export complete: {output_path}")

    except Exception as e:
        print(
            f"❌ Failed to export JSON to '{output_path}' with search term '{search_term}': {type(e).__name__}: {e}"
        )


# --------------------------------------------------------------------------
# Safe Export Utility with Markdown Table Support
# --------------------------------------------------------------------------


def safe_export(
    results: Any,
    export_path: Optional[Path] = None,
    export_format: str = "txt",
    df: Optional[pd.DataFrame] = None,
    source_file: Optional[Path] = None,
    compress: bool = False,
) -> str:
    """
    Safely export results as txt, md, or JSON.
    - Converts None values to empty strings.
    - Automatically converts dict/list to Markdown table if export_format='md'.
    - Supports optional gzip compression.
    - Always writes UTF-8 to avoid UnicodeEncodeError.
    """
    import os
    import json
    from datetime import datetime

    if export_path is None:
        base = source_file.stem if source_file else "analysis"
        export_path = Path(f"{base}.{export_format}")
    export_path = Path(export_path)
    os.makedirs(export_path.parent or ".", exist_ok=True)

    # -----------------------
    # Helper: Convert None → ""
    # -----------------------
    def _none_to_empty(obj: Any) -> Any:
        if obj is None:
            return ""
        if isinstance(obj, dict):
            return {k: _none_to_empty(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_none_to_empty(v) for v in obj]
        return obj

    safe_results = _none_to_empty(results)

    # -----------------------
    # Convert dict/list → Markdown table
    # -----------------------
    def _to_md_table(data: Any) -> str:
        lines = []
        if isinstance(data, dict):
            lines.append(
                f"<!-- Generated by Indexly {datetime.utcnow().isoformat()}Z -->\n"
            )
            lines.append("| Key | Value |")
            lines.append("|-----|-------|")
            for k, v in data.items():
                val = (
                    json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (dict, list))
                    else str(v)
                )
                lines.append(f"| {k} | {val} |")
        elif isinstance(data, list) and all(isinstance(d, dict) for d in data):
            if not data:
                return ""
            cols = sorted({k for row in data for k in row.keys()})
            lines.append(
                f"<!-- Generated by Indexly {datetime.utcnow().isoformat()}Z -->\n"
            )
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("| " + " | ".join("---" for _ in cols) + " |")
            for row in data:
                lines.append(
                    "| " + " | ".join(str(row.get(c, "")) for c in cols) + " |"
                )
        else:
            lines.append(str(data))
        lines.append(f"\n<!-- End of Export -->")
        return "\n".join(lines)

    # -----------------------
    # Prepare content
    # -----------------------
    if export_format == "md":
        content = _to_md_table(safe_results)
    elif export_format == "txt":
        content = (
            json.dumps(safe_results, indent=2, ensure_ascii=False)
            if isinstance(safe_results, (dict, list))
            else str(safe_results)
        )
    elif export_format == "json":
        content = json.dumps(safe_results, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported export format: {export_format}")

    # -----------------------
    # Write to file (UTF-8)
    # -----------------------
    mode = "wt"
    if compress:
        import gzip

        open_func = lambda p, m: gzip.open(p, m, encoding="utf-8")
    else:
        open_func = lambda p, m: open(p, m, encoding="utf-8")

    with open_func(export_path, mode) as f:
        f.write(content)

    timestamp = datetime.utcnow().isoformat() + "Z"
    print(f"✅ Exported {export_format.upper()} to: {export_path} at {timestamp}")

    return str(export_path)


# Export Utils for analyze-db


def save_json(obj: Any, out_path: Path) -> Path:
    out = out_path.with_suffix(out_path.suffix + ".analysis.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, default=str, indent=2)
    return out


def save_markdown(summary: Dict, out_path: Path, include_diagram: bool = False) -> Path:
    out = out_path.with_suffix(out_path.suffix + ".analysis.md")
    lines = ["# Database Analysis\n"]

    # Meta
    lines.append("## Meta\n")
    for k, v in summary.get("meta", {}).items():
        lines.append(f"- **{k}**: {v}")

    # Tables
    lines.append("\n## Tables\n")
    for tbl, prof in summary.get("profiles", {}).items():
        lines.append(f"### {tbl}")
        lines.append(f"- rows: {prof.get('rows')}")
        lines.append(f"- cols: {len(prof.get('columns', []))}")
        if prof.get("non_numeric"):
            lines.append(f"- top values: {list(prof['non_numeric'].keys())[:6]}")

    # Mermaid ER diagram
    if include_diagram and "schema_summary" in summary:
        mermaid = build_mermaid_from_schema(summary["schema_summary"])
        lines.append("\n## Relationship Diagram (Mermaid)\n")
        lines.append("```mermaid")
        lines.append(mermaid)
        lines.append("```\n")

    # Adjacency Graph (JSON)
    if "adjacency_graph" in summary:
        import json
        lines.append("## Adjacency Graph\n")
        lines.append("```json")
        lines.append(json.dumps(summary["adjacency_graph"], indent=2))
        lines.append("```")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out



def save_html(summary: Dict, out_path: Path, include_diagram: bool = False) -> Path:
    out = out_path.with_suffix(out_path.suffix + ".analysis.html")
    md = save_markdown(summary, out_path, include_diagram=include_diagram)
    md_text = md.read_text(encoding="utf-8")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>DB Analysis</title></head><body><pre>{md_text}</pre></body></html>"""
    out.write_text(html, encoding="utf-8")
    return out
