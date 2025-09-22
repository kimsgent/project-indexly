"""
📄 utils.py

Purpose:
    Generic helper functions reused across multiple modules.

Key Features:
    - clean_text(): Whitespace normalization.
    - get_snippet_around_match(): Provides contextual text around regex matches.
    - format_tags(): Pretty output of tags for terminal view.

Used by:
    - All search modes and export utilities.
"""


# 📦 Standard library imports (safe to keep at the top)
import io
import re
import sys
import subprocess
import shutil
import platform
from .ripple import Ripple  # ✅ if ripple.py has no heavy dependencies
from pptx import Presentation
from ebooklib import epub
from bs4 import BeautifulSoup
from odf.opendocument import load
from odf.text import P
from .db_utils import get_tags_for_file
from fpdf.errors import FPDFException


# ✅ Helper: Install missing packages
def prompt_install(package_list):
    install_all = False
    try:
        for module, package in package_list:
            try:
                __import__(module)
            except ImportError:
                if not install_all:
                    response = (
                        input(f"Install missing package '{package}'? [Y/n/A=all]: ")
                        .strip()
                        .lower()
                    )

                    if response in ("a", "all"):
                        install_all = True
                        response = "y"

                if install_all or response in ("", "y", "yes"):
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", package]
                    )
    except KeyboardInterrupt:
        print("\n⛔ Package installation cancelled by user.")
        sys.exit(1)


def check_and_install_packages(pkg_list):
    try:
        prompt_install(pkg_list)
    except KeyboardInterrupt:
        print("\n❌ Cancelled while checking packages.")
        sys.exit(1)


# ✅ Check for optional/heavy third-party packages BEFORE importing
check_and_install_packages(
    [
        ("nltk", "nltk"),
        ("fitz", "pymupdf"),
        ("pytesseract", "pytesseract"),
        ("PIL", "pillow"),
        ("docx", "python-docx"),
        ("openpyxl", "openpyxl"),
        ("rapidfuzz", "rapidfuzz"),
        ("fpdf", "fpdf2"),
        ("reportlab", "reportlab"),
        ("bs4", "beautifulsoup4"),
        ("extract_msg", "extract_msg"),
        ("eml_parser", "eml-parser"),
        ("PyPDF2", "PyPDF2"),
        ("watchdog", "watchdog"),
        ("colorama", "colorama"),
        # NEW for pptx, epub, odt
        ("pptx", "python-pptx"),
        ("ebooklib", "ebooklib"),
        ("odf", "odfpy"),
    ]
)

def check_external_tools():
    # ExifTool
    if shutil.which("exiftool") is None:
        print("⚠️ ExifTool not found. Install: https://exiftool.org/")

    # Tesseract
    if shutil.which("tesseract") is None:
        os_name = platform.system().lower()
        print("⚠️ Tesseract OCR not found. Install:")
        if "windows" in os_name:
            print("  choco install tesseract OR winget install tesseract")
        elif "darwin" in os_name:
            print("  brew install tesseract")
        elif "linux" in os_name:
            print("  sudo apt install tesseract-ocr")

def check_exiftool():
    if shutil.which("exiftool") is None:
        os_name = platform.system().lower()
        print("ℹ️ exiftool not found. For richer image metadata extraction:")

        if "windows" in os_name:
            print("   👉 Install with Chocolatey: choco install exiftool")
            print("   👉 Or with Winget: winget install exiftool")
            print("   👉 Or download manually: https://exiftool.org/")
        elif "darwin" in os_name:  # macOS
            print("   👉 Install with Homebrew: brew install exiftool")
        elif "linux" in os_name:
            print("   👉 Install with apt: sudo apt install libimage-exiftool-perl")
            print("   👉 Or use your distro’s package manager.")
        else:
            print("   👉 Please install from https://exiftool.org/")

# ✅ Safe to import third-party modules after checks
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import sent_tokenize
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import openpyxl
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from textwrap import wrap, fill
import re
from rich.text import Text

# print("DEBUG: updated hightlight_term loaded")
def highlight_term(text, term):
    """
    Highlight all occurrences of `term` in `text` using Rich Text.
    Matches appear in bold red; surrounding text can have a different style.
    """
    if not term:
        return Text(text)  # plain Text if nothing to highlight

    t = Text(text)  # base Text object
    pattern = re.compile(rf"({re.escape(term)})", re.IGNORECASE)

    for match in pattern.finditer(text):
        start, end = match.span()
        t.stylize("bold red", start, end)

    return t


def format_tags(path):
    
    tags = get_tags_for_file(path)
    if not tags:
        return ""
    # Parse tags and sort
    tag_dict = {}
    for tag in tags:
        if ":" in tag:
            key, val = tag.split(":", 1)
            tag_dict[key.strip()] = val.strip()
    sorted_pairs = [f"{k}: {v}" for k, v in sorted(tag_dict.items())]
    return f"[{' | '.join(sorted_pairs)}]"


def get_snippets(text, query, context_sentences=2):
    text = re.sub(r"\s+", " ", text).strip()
    sentences = sent_tokenize(text)
    matches = []

    for i, sent in enumerate(sentences):
        if re.search(re.escape(query), sent, re.IGNORECASE):
            start = max(0, i - context_sentences)
            end = min(len(sentences), i + context_sentences + 1)
            snippet = " ".join(sentences[start:end])
            highlighted = re.sub(
                f"({re.escape(query)})",
                f"\033[93m\1\033[0m",
                snippet,
                flags=re.IGNORECASE,
            )
            matches.append(highlighted.strip())

    return matches


def print_with_context(file_path, paragraph, term, paragraph_num=0):
    lines = paragraph.strip().splitlines()
    context = "\n".join(line.strip() for line in lines if term.lower() in line.lower())

    if not context.strip():
        return  # Skip empty matches

    print(f"\n📄 {file_path}")
    print(highlight_term(context.strip(), term))


def clean_text(text):
    text = re.sub(r"<[^>]+>", " ", text)  # Strip HTML tags
    text = re.sub(r"\s+", " ", text)  # Normalize whitespace
    text = re.sub(r"[\x00-\x1F\x7F-\x9F]", "", text)  # Remove control chars
    return text.strip()

def clean_tags(tags):
    cleaned = []
    for tag in tags:
        if not tag:
            continue
        tag = tag.strip().replace(";", ":")  # normalize key-value separator
        tag = " ".join(tag.split())  # collapse multiple spaces
        cleaned.append(tag)
    return list(dict.fromkeys(cleaned))  # remove duplicates, preserve order

def get_snippet_around_match(text, match_obj, context_chars):
    start, end = match_obj.start(), match_obj.end()
    # Ensure snippet length is up to context_chars, with match roughly centered
    half_context = context_chars // 2
    snippet_start = max(0, start - half_context)
    snippet_end = min(len(text), end + half_context)
    
    # If snippet shorter than context_chars, expand to full length if possible
    if snippet_end - snippet_start < context_chars:
        if snippet_start == 0:
            snippet_end = min(len(text), snippet_start + context_chars)
        elif snippet_end == len(text):
            snippet_start = max(0, snippet_end - context_chars)

    return clean_text(text[snippet_start:snippet_end])

def build_snippet(content, terms, context_chars=150, fuzzy=False, max_snippets=3):
    """
    Wrapper for snippet building:
    - Uses multi-term merge for exact matches.
    - Uses single-term centered snippet for fuzzy fallback.
    """
    if fuzzy:
        # Take first term and search for approximate match
        term = terms[0] if terms else ""
        if not term:
            return ""
        match = re.search(re.escape(term), content, re.IGNORECASE)
        if match:
            return get_snippet_around_match(content, match, context_chars)
        # fallback: truncated slice
        return clean_text(content[:context_chars])
    else:
        return get_snippets_for_matches(content, terms, context_chars, max_snippets)


def get_snippets_for_matches(
    content: str,
    search_terms: list[str],
    context_chars: int = 150,
    max_snippets: int = 3,
) -> str:
    match_ranges = []

    # Collect all match ranges
    for term in search_terms:
        if not term:
            continue
        for match in re.finditer(re.escape(term), content, re.IGNORECASE):
            start, end = match.start(), match.end()
            half_ctx = context_chars // 2
            start = max(0, start - half_ctx)
            end = min(len(content), end + half_ctx)
            match_ranges.append((start, end))

    if not match_ranges:
        return ""

    # Merge overlapping ranges
    match_ranges.sort()
    merged_ranges = [match_ranges[0]]
    for current in match_ranges[1:]:
        last = merged_ranges[-1]
        if current[0] <= last[1]:
            merged_ranges[-1] = (last[0], max(last[1], current[1]))
        else:
            merged_ranges.append(current)

    # Extract merged snippets
    snippets = [clean_text(content[s:e]) for s, e in merged_ranges[:max_snippets]]

    # 🔍 Debug: show applied context length
    # print(f"[DEBUG] context_chars={context_chars}, snippet_lengths={[len(sn) for sn in snippets]}")

    return " ... ".join(snippets)


# Adding pdf export support

def wrap_text_fpdf(text, width=80):
    return wrap(text, width=width, break_long_words=True, break_on_hyphens=False)


def safe_text(text):
    try:
        # Remove ANSI escape sequences
        text = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", str(text))
        # Remove other control characters (non-printable)
        text = "".join(c for c in text if c.isprintable())
        return text.encode("latin-1", "replace").decode("latin-1")
    except:
        return str(text)[:300]


def _soft_breaks(text: str) -> str:
    """Insert soft break opportunities so long paths can wrap."""
    zwsp = "\u200b"
    return (text
            .replace("/", f"/{zwsp}")
            .replace("\\", f"\\{zwsp}")
            .replace("_", f"_{zwsp}")
            .replace("-", f"-{zwsp}")
            .replace(".", f".{zwsp}"))


def _safe_multicell(pdf, text: str, h: float = 8):
    """Always render from left margin with a positive width and catch width errors."""
    if not text:
        return
    text = _soft_breaks(text)
    try:
        # Effective page width (fpdf2 provides `epw`)
        w = getattr(pdf, "epw", pdf.w - pdf.l_margin - pdf.r_margin)
        pdf.set_x(pdf.l_margin)              # start from left margin
        pdf.multi_cell(w, h, text)
    except FPDFException as e:
        # Retry with a smaller font once
        try:
            old = pdf.font_size_pt
            pdf.set_font_size(max(6, old - 2))
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w, h, text)
            pdf.set_font_size(old)           # restore
        except Exception as e2:
            print(f"⚠️ Skipped line: {e2}")
