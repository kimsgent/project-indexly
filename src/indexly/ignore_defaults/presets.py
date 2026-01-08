# src/indexly/ignore_defaults/presets.py
from __future__ import annotations
from pathlib import Path
from importlib.resources import files, Package
from .validator import validate_template
import warnings

_PRESET_FILES = {
    "standard": "standard.txt",
    "minimal": "minimal.txt",
    "aggressive": "aggressive.txt",
}


def load_preset(name: str = "standard") -> str:
    """
    Load an ignore preset by name.

    Works in both development and installed environments.
    """

    filename = _PRESET_FILES.get(name)
    if not filename:
        raise ValueError(f"Unknown ignore preset: {name}")

    # 1️⃣ Try importlib.resources first (for installed package)
    try:
        preset_pkg: Package = files("indexly.ignore_defaults.presets")
        preset_file = preset_pkg / filename
        if preset_file.exists():
            template = preset_file.read_text(encoding="utf-8")
            valid, _ = validate_template(template)
            if valid:
                return template
            warnings.warn(f"Preset '{name}' invalid, falling back.", stacklevel=2)
    except Exception:
        pass

    # 2️⃣ Try filesystem relative to this file (dev mode)
    dev_path = Path(__file__).parent / "presets" / filename
    if dev_path.exists():
        try:
            template = dev_path.read_text(encoding="utf-8")
            valid, _ = validate_template(template)
            if valid:
                return template
            warnings.warn(f"Dev preset '{name}' invalid, falling back.", stacklevel=2)
        except Exception:
            pass

    # 3️⃣ Hardcoded minimal fallback
    return (
        "# Minimal fallback ignore template\n"
        ".cache/\n"
        "__pycache__/\n"
        "*.tmp\n"
        "*.log\n"
    )
