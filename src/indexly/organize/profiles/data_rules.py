from pathlib import Path

RAW_HINTS = {"raw", "dirty", "unprocessed"}
PROCESSED_HINTS = {"clean", "processed", "normalized"}
OUTPUT_HINTS = {"output", "result", "final"}

NOTEBOOK_EXTS = {".ipynb"}
SCRIPT_EXTS = {".py", ".r", ".sql"}
VISUAL_EXTS = {".jpg", ".jpeg", ".png", ".svg"}
DATA_EXTS = {".csv", ".parquet", ".xlsx", ".json", ".json.gz"}
DB_EXTS = {".db", ".sqlite"}

def get_destination(root: Path, file_path: Path, project_name: str | None = None, **kwargs) -> Path:
    """
    Returns the folder where the file should be placed for the 'data' profile.
    """
    proj = project_name or "Unnamed_Project"
    base = root / "Projects" / proj

    fname = file_path.name.lower()
    ext = file_path.suffix.lower()

    if any(h in fname for h in RAW_HINTS) or ext in DATA_EXTS:
        folder = base / "Data" / "Raw"
    elif any(h in fname for h in PROCESSED_HINTS):
        folder = base / "Data" / "Processed"
    elif any(h in fname for h in OUTPUT_HINTS):
        folder = base / "Data" / "Output"
    elif ext in NOTEBOOK_EXTS:
        folder = base / "Notebooks"
    elif ext in SCRIPT_EXTS:
        folder = base / "Scripts"
    elif ext in VISUAL_EXTS:
        folder = base / "Visuals"
    elif ext in DB_EXTS:
        folder = base / "Data"
    else:
        folder = root / "Archive"

    return folder / file_path.name
