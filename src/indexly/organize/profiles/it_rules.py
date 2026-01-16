from pathlib import Path

IT_EXTS = {
    ".exe": "Software",
    ".msi": "Software",
    ".zip": "Archives",
    ".tar": "Archives",
    ".7z": "Archives",
    ".rar": "Archives",
    ".pdf": "Documents",
    ".docx": "Documents",
    ".txt": "Documents",
    ".py": "Scripts",
    ".bat": "Scripts",
    ".cfg": "Configs",
}

def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    ext = file_path.suffix.lower()
    category = IT_EXTS.get(ext, "Misc")
    return root / "IT" / category / file_path.name
