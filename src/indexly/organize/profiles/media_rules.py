from pathlib import Path
from datetime import datetime

def get_destination(root: Path, file_path: Path, shoot_name: str | None = None, **kwargs) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    shoot_folder = date_str if not shoot_name else f"{date_str}-{shoot_name}"

    ext = file_path.suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".tiff", ".bmp"}:
        folder = root / "Media" / "Shoots" / shoot_folder / "RAW"
    elif ext in {".mp4", ".avi", ".mov", ".mkv"}:
        folder = root / "Media" / "Video"
    else:
        folder = root / "Media" / "Archive"

    return folder / file_path.name
