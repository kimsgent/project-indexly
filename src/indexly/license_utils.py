import importlib.resources
import os
import sys
import importlib.metadata
from indexly import __version__, __author__
from rich.console import Console
from rich.text import Text

console = Console()

def _find_license_file():
    try:
        path = importlib.resources.files("indexly").joinpath("LICENSE.txt")
        if path.is_file():
            return path
    except Exception:
        pass
    try:
        dist_path = importlib.metadata.distribution("indexly").locate_file("licenses/LICENSE.txt")
        if os.path.isfile(dist_path):
            return dist_path
    except Exception:
        pass
    candidate = os.path.join(os.path.dirname(__file__), "..", "..", "LICENSE.txt")
    if os.path.exists(candidate):
        return candidate
    return None

def get_license_excerpt(lines=2):
    path = _find_license_file()
    if not path:
        return "MIT License"
    try:
        with open(path, encoding="utf-8") as f:
            excerpt = "\n".join(next(f).rstrip() for _ in range(lines))
            return excerpt + "\n[… truncated, run `indexly --show-license` for full text …]"
    except Exception:
        return "MIT License"

def get_version_string_rich():
    """
    Return a rich-formatted multi-line version string.
    """
    license_excerpt = get_license_excerpt(lines=2)

    text = Text()
    text.append(f"Indexly {__version__} (c) 2025 {__author__})\n", style="bold cyan")
    text.append(f"{license_excerpt}\n", style="white")
    text.append("Project: github.com/kimsgent/project-indexly\n", style="bold green")
    text.append("Website: projectindexly.com\n", style="bold green")
    return text

def print_version():
    """
    Print the version using rich for proper line breaks and colors.
    """
    console.print(get_version_string_rich())

def show_full_license():
    path = _find_license_file()
    if not path:
        console.print("[red]License file not found.[/red]")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        console.print(f.read())
    sys.exit(0)
