from pathlib import Path


PAPER_EXTS = {".pdf", ".doc", ".docx", ".tex", ".rtf"}
DATA_EXTS = {".csv", ".tsv", ".xlsx", ".json", ".json.gz", ".parquet", ".db", ".sqlite"}
NOTE_EXTS = {".md", ".txt", ".rst"}
PRESENTATION_EXTS = {".ppt", ".pptx", ".key"}
SCRIPT_EXTS = {".py", ".r", ".R", ".jl", ".m", ".ipynb", ".sql"}

RAW_HINTS = {"raw", "source", "original", "instrument"}
CLEAN_HINTS = {"clean", "processed", "normalized", "derived"}
RESULT_HINTS = {"result", "results", "analysis", "output", "figure", "table"}
REFERENCE_HINTS = {"reference", "citation", "bibliography", "bibtex", "zotero"}
DRAFT_HINTS = {"draft", "manuscript", "preprint"}
PUBLISHED_HINTS = {"published", "accepted", "final"}
ADMIN_HINTS = {"ethics", "irb", "grant", "budget", "admin", "approval"}


def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    """
    Conservative research placement rules.

    The rules preserve raw/source material, separate derived data from results,
    and keep papers, notes, references, presentations, and admin documents apart.
    """
    fname = file_path.name.lower()
    ext = file_path.suffix.lower()
    if file_path.name.lower().endswith(".json.gz"):
        ext = ".json.gz"

    base = root / "Research"

    if any(h in fname for h in ADMIN_HINTS):
        folder = base / "Admin"
    elif any(h in fname for h in REFERENCE_HINTS):
        folder = base / "References" / "PDFs" if ext == ".pdf" else base / "References"
    elif ext in PRESENTATION_EXTS:
        folder = base / "Presentations"
    elif ext in NOTE_EXTS:
        folder = base / "Notes"
    elif ext in SCRIPT_EXTS:
        folder = base / "Data" / "Results"
    elif ext in DATA_EXTS:
        if any(h in fname for h in RAW_HINTS):
            folder = base / "Data" / "Raw"
        elif any(h in fname for h in CLEAN_HINTS):
            folder = base / "Data" / "Cleaned"
        elif any(h in fname for h in RESULT_HINTS):
            folder = base / "Data" / "Results"
        else:
            folder = base / "Data" / "Raw"
    elif ext in PAPER_EXTS:
        if any(h in fname for h in PUBLISHED_HINTS):
            folder = base / "Papers" / "Published"
        elif any(h in fname for h in DRAFT_HINTS):
            folder = base / "Papers" / "Drafts"
        else:
            folder = base / "Papers" / "Submitted"
    else:
        folder = base / "Admin"

    return folder / file_path.name
