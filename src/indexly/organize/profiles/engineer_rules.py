from pathlib import Path


CAD_EXTS = {".dwg", ".dxf", ".step", ".stp", ".iges", ".igs", ".sldprt", ".sldasm", ".f3d"}
SIM_EXTS = {".fem", ".inp", ".odb", ".msh", ".sim", ".ans", ".cfd"}
CALC_EXTS = {".xlsx", ".xls", ".csv", ".m", ".py", ".ipynb", ".r"}
REPORT_EXTS = {".pdf", ".doc", ".docx", ".md", ".txt"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp"}

DESIGN_HINTS = {"design", "concept", "spec", "requirement"}
SIM_HINTS = {"simulation", "sim", "fea", "cfd", "analysis", "model"}
CALC_HINTS = {"calc", "calculation", "spreadsheet", "load", "stress", "tolerance"}
REPORT_HINTS = {"report", "summary", "review", "memo"}
DRAWING_HINTS = {"drawing", "drawings", "schematic", "layout"}
STANDARD_HINTS = {"standard", "specification", "code", "iso", "din", "astm"}
PHOTO_HINTS = {"photo", "site", "inspection", "field"}


def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    """
    Conservative engineering placement rules.

    The rules separate CAD, simulations, calculations, drawings, standards,
    reports, and field photos without assuming a discipline-specific taxonomy.
    """
    fname = file_path.name.lower()
    ext = file_path.suffix.lower()
    base = root / "Engineering"

    if ext in CAD_EXTS:
        folder = base / "CAD"
    elif ext in SIM_EXTS or any(h in fname for h in SIM_HINTS):
        folder = base / "Projects" / "Simulation"
    elif ext in CALC_EXTS or any(h in fname for h in CALC_HINTS):
        folder = base / "Projects" / "Calculations"
    elif any(h in fname for h in STANDARD_HINTS):
        folder = base / "Standards"
    elif any(h in fname for h in DRAWING_HINTS):
        folder = base / "Drawings"
    elif ext in IMAGE_EXTS or any(h in fname for h in PHOTO_HINTS):
        folder = base / "Photos"
    elif ext in REPORT_EXTS or any(h in fname for h in REPORT_HINTS):
        folder = base / "Projects" / "Reports"
    elif any(h in fname for h in DESIGN_HINTS):
        folder = base / "Projects" / "Design"
    else:
        folder = base / "Archive"

    return folder / file_path.name
