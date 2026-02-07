from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from indexly.organize.organizer import organize_folder

console = Console()


def generate_log_from_tree(root: Path) -> dict:
    """
    Generate an organizer-compatible log without modifying the filesystem.
    """
    console.print(
        Panel(
            "Organizer log not found.\n"
            "Generating temporary organizer log (read-only scan).",
            title="📂 Lister",
            style="yellow",
        )
    )

    # We intentionally reuse organizer logic to avoid drift
    log = organize_folder(
        root=root,
        sort_by="date",          # same default organizer behavior
        executed_by="lister",
        dry_run=True,
    )

    return log
