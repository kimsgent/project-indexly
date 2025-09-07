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
from datetime import datetime
from fpdf import FPDF
from reportlab.lib.pagesizes import A4
from .db_utils import get_tags_for_file
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from fpdf.errors import FPDFException






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
            pdf.add_font("DejaVu", "", os.path.join(font_dir, "DejaVuSans.ttf"), uni=True)
            pdf.add_font("DejaVu", "B", os.path.join(font_dir, "DejaVuSans-Bold.ttf"), uni=True)
            pdf.add_font("DejaVu", "I", os.path.join(font_dir, "DejaVuSans-Oblique.ttf"), uni=True)
        except Exception as e:
            print(f"❌ Failed to load fonts: {e}")
            # fallback font
            pdf.set_font("Arial", size=12)

        pdf.add_page()

        # Header
        pdf.set_font("DejaVu", "B", 14)
        pdf.cell(0, 10, safe_text(f"Search Results for: {search_term}"), ln=True, align="C")
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

    story.append(Paragraph(f"<b>Search Results for:</b> {safe_text(search_term)}", styles["Title"]))
    story.append(Spacer(1, 12))

    for idx, row in enumerate(results, 1):
        row = dict(row)
        path = row.get("path", "Unknown file")
        snippet = row.get("snippet") or row.get("content", "")[:500]

        story.append(Paragraph(f"<b>{idx}. File:</b> {safe_text(path)}", styles["Heading4"]))
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


