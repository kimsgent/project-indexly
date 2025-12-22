from pathlib import Path
import json
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def _discover_log(path: Path) -> Path:
    """Find organizer log from file or directory"""
    path = Path(path)

    if path.is_file():
        return path

    if path.is_dir():
        logs = sorted(
            path.rglob("organized_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not logs:
            raise FileNotFoundError("No organizer logs found")
        return logs[0]

    raise FileNotFoundError(path)


def list_organizer_log(
    source: Path,
    *,
    ext: str | None = None,
    category: str | None = None,
    date: str | None = None,
    duplicates_only: bool = False,
):
    """List files from organizer JSON log"""
    log_path = _discover_log(source)

    with open(log_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", [])
    meta = data.get("meta", {})

    table = Table(
        title=f"📂 Organizer log — {Path(meta.get('root', '')).name}",
        show_lines=False,
    )
    table.add_column("#", justify="right")
    table.add_column("Category")
    table.add_column("Ext")
    table.add_column("Date")
    table.add_column("Size", justify="right")
    table.add_column("Path")

    count = 0
    for idx, f in enumerate(files, 1):
        if ext and f["extension"] != ext:
            continue
        if category and f["category"] != category:
            continue
        if date and f["used_date"] != date:
            continue
        if duplicates_only and not f.get("duplicate"):
            continue

        size = f["size"]
        size_str = f"{size:,}"

        path_text = Text(f["new_path"])
        if f.get("duplicate"):
            path_text.stylize("yellow")

        table.add_row(
            str(idx),
            f["category"],
            f["extension"],
            f["used_date"],
            size_str,
            path_text,
        )
        count += 1

    console.print(table)
    console.print(
        f"\n📊 Listed {count} / {len(files)} files from {log_path.name}"
    )

    return count
