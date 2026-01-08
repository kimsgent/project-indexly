from indexly import __version__, __author__
import os
import sys
import site
import importlib.resources
import importlib.metadata
from pathlib import Path
from rich.console import Console
from rich.text import Text

console = Console()




def _find_license_file():
    # 1. Try inside package folder
    try:
        path = importlib.resources.files("indexly").joinpath("LICENSE.txt")
        if path.is_file():
            return path
    except Exception:
        pass

    # 2. Try dist-info licenses folder using metadata
    try:
        dist = importlib.metadata.distribution("indexly")
        license_path = Path(dist.locate_file("licenses/LICENSE.txt"))
        if license_path.exists():
            return license_path
    except Exception:
        pass

    # 3. Fallback: glob for indexly-*.dist-info/licenses/LICENSE.txt in sys.path
    for site_path in [Path(p) for p in sys.path if "site-packages" in p]:
        for dist_info in site_path.glob("indexly-*.dist-info"):
            candidate = dist_info / "licenses" / "LICENSE.txt"
            if candidate.exists():
                return candidate

    # 4. Source fallback
    candidate = Path(__file__).parent.parent.parent / "LICENSE.txt"
    if candidate.exists():
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
    text.append(f"Indexly {__version__} (c) 2026 {__author__})\n", style="bold cyan")
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
