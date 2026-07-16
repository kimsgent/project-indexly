"""Side-effect-free resolution of Indexly runtime paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_base_dir() -> Path:
    """Return the configured runtime root without creating it."""
    explicit = os.environ.get("INDEXLY_HOME")
    if explicit:
        return Path(explicit).expanduser()

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "indexly"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "indexly"
        return home / "AppData" / "Roaming" / "indexly"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "indexly"
    return home / ".local" / "share" / "indexly"
