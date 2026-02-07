# it_rules.py (aligned to PROFILE_STRUCTURES["it"])

from pathlib import Path

IT_RULES = {
    # Code
    ".py": "IT/Code/Scripts",
    ".bat": "IT/Code/Scripts",
    ".ps1": "IT/Code/Scripts",
    ".sh": "IT/Code/Scripts",

    # Configs
    ".cfg": "IT/Configs",
    ".ini": "IT/Configs",
    ".yaml": "IT/Configs",
    ".yml": "IT/Configs",
    ".json": "IT/Configs",

    # Docs
    ".pdf": "IT/Docs/Manuals",
    ".docx": "IT/Docs/Manuals",
    ".md": "IT/Docs/Notes",
    ".txt": "IT/Docs/Notes",

    # Resources / binaries / archives
    ".exe": "IT/Resources",
    ".msi": "IT/Resources",
    ".zip": "IT/Resources",
    ".tar": "IT/Resources",
    ".7z": "IT/Resources",
    ".rar": "IT/Resources",

    # Logs
    ".log": "IT/Logs",
}

def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    ext = file_path.suffix.lower()
    rel = IT_RULES.get(ext, "IT/Resources")
    return root / rel / file_path.name
