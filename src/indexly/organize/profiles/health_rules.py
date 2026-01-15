from pathlib import Path
from indexly.organize.profiles.base_rules import get_destination as base_destination

HEALTH_FOLDERS = {
    "patients": "Patients",
    "reports": "Reports",
    "imaging": "Imaging",
    "lab": "Lab",
    "admin": "Admin",
    "guidelines": "Guidelines",
    "archive": "Archive",
}


def get_destination(
    root: Path,
    file_path: Path,
    *,
    patient_id: str | None = None,
    ensure_patient_folder_exists: bool = False,
    **_,
) -> Path:
    """
    Health profile placement rules.
    """

    root = Path(root)
    fname = file_path.name.lower()
    suffix = file_path.suffix.lower()

    image_exts = {".jpg", ".jpeg", ".png", ".dcm"}
    text_exts = {".txt", ".pdf", ".docx", ".md"}

    # 🔒 Patient-bound placement
    if patient_id:
        patient_root = root / "Health" / HEALTH_FOLDERS["patients"] / patient_id

        if ensure_patient_folder_exists:
            patient_root.mkdir(parents=True, exist_ok=True)
            for folder in HEALTH_FOLDERS.values():
                if folder != HEALTH_FOLDERS["patients"]:
                    (patient_root / folder).mkdir(parents=True, exist_ok=True)
        elif not patient_root.exists():
            raise RuntimeError(
                f"Patient ID '{patient_id}' does not exist. "
                "Use `organize scaffold health --apply` to create it first."
            )

        if "report" in fname:
            folder = patient_root / HEALTH_FOLDERS["reports"]
        elif suffix in image_exts or "image" in fname:
            folder = patient_root / HEALTH_FOLDERS["imaging"]
        elif "lab" in fname:
            folder = patient_root / HEALTH_FOLDERS["lab"]
        elif "admin" in fname:
            folder = patient_root / HEALTH_FOLDERS["admin"]
        elif "guideline" in fname:
            folder = patient_root / HEALTH_FOLDERS["guidelines"]
        elif suffix in text_exts:
            folder = patient_root / HEALTH_FOLDERS["archive"]
        else:
            dest = base_destination(patient_root, file_path)
            folder = dest.parent

        folder.mkdir(parents=True, exist_ok=True)
        return folder / file_path.name

    # 🔓 Non-patient placement
    if "report" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["reports"]
    elif suffix in image_exts or "image" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["imaging"]
    elif "lab" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["lab"]
    elif "admin" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["admin"]
    elif "guideline" in fname:
        folder = root / "Health" / HEALTH_FOLDERS["guidelines"]
    else:
        folder = root / "Health" / HEALTH_FOLDERS["archive"]

    folder.mkdir(parents=True, exist_ok=True)
    return folder / file_path.name
