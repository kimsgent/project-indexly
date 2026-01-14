from pathlib import Path

HEALTH_FOLDERS = {
    "patients": "Patients",
    "reports": "Reports",
    "imaging": "Imaging",
    "lab": "Lab",
    "admin": "Admin",
    "guidelines": "Guidelines",
}

def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    fname = file_path.name.lower()
    if "patient" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["patients"]
    elif "report" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["reports"]
    elif "image" in fname or file_path.suffix.lower() in {".jpg", ".png", ".dcm"}:
        folder = root / "Health" / HEALTH_FOLDERS["imaging"]
    elif "lab" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["lab"]
    else:
        folder = root / "Health" / "Archive"
    return folder / file_path.name
