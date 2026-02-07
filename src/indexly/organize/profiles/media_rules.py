from pathlib import Path
from datetime import datetime
import re

from indexly.extract_utils import extract_image_metadata


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv"}

FALLBACK_FOLDER = "_Unknown"


def _safe_folder_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^\w\-., ]+", "_", value)
    return value[:80] or FALLBACK_FOLDER


def get_destination(
    root: Path,
    file_path: Path,
    shoot_name: str | None = None,
    *,
    profile: str | None = None,
    category: str | None = None,
    classify_raw: str | None = None,
    **_,
) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    shoot_folder = date_str if not shoot_name else f"{date_str}-{shoot_name}"

    ext = file_path.suffix.lower()

    # ---------------------------
    # IMAGE → SHOOTS / RAW
    # ---------------------------
    if ext in IMAGE_EXTS:
        base = root / "Media" / "Shoots" / shoot_folder / "00_RAW"

        # Photographer RAW classification (OPT-IN)
        if profile == "media" and category == "photographer" and classify_raw:
            md = extract_image_metadata(str(file_path))

            key_map = {
                "camera": md.get("camera"),
                "gps": md.get("gps"),
                "date": md.get("image_created"),
                "title": md.get("title"),
                "author": md.get("author"),
            }

            raw_value = key_map.get(classify_raw)
            folder_name = (
                _safe_folder_name(raw_value)
                if isinstance(raw_value, str) and raw_value.strip()
                else FALLBACK_FOLDER  # "_Unknown"
            )

            return base / folder_name / file_path.name

        # Default RAW behavior
        return base / file_path.name

    # ---------------------------
    # VIDEO
    # ---------------------------
    if ext in VIDEO_EXTS:
        return root / "Media" / "Video" / file_path.name

    # ---------------------------
    # EVERYTHING ELSE
    # ---------------------------
    return root / "Media" / "Archive" / file_path.name
