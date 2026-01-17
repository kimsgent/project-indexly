from pathlib import Path

DOC_EXTS = {".pdf", ".txt", ".md", ".docx", ".pptx"}
SLIDE_EXTS = {".pptx", ".key"}

def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    ext = file_path.suffix.lower()
    if ext in DOC_EXTS:
        folder = root / "Education" / "Documents"
    elif ext in SLIDE_EXTS:
        folder = root / "Education" / "Slides"
    else:
        folder = root / "Education" / "Archive"
    return folder / file_path.name
