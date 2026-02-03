from pathlib import Path
import json
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel

from indexly.organize.lister_fallback import generate_log_from_tree
from indexly.organize.lister_cache import read_cache, write_cache
from indexly.organize.lister_hash import hash_file

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
    no_generate: bool = False,
    sort_by: str = "date",
    detect_duplicates: bool = False,
    no_cache: bool = False,
) -> int:
    """List files from organizer JSON log with cache, sorting, and optional hash-based duplicates."""
    data = None
    log_path = None
    generated_log = False

    if not no_cache:
        data = read_cache(source)

    if data:
        source_label = f"cached log ({source.name})"
    else:
        try:
            log_path = _discover_log(source)
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_label = log_path.name
        except FileNotFoundError:
            if no_generate:
                console.print(
                    f"🔹 No organizer log found in '{source}' and --no-generate was specified. Nothing to list.",
                    style="red",
                )
                return 0
            source = Path(source)
            if not source.is_dir():
                console.print(
                    f"🔹 Path '{source}' is not a directory and no log found. Nothing to list.",
                    style="red",
                )
                return 0
            data = generate_log_from_tree(source)
            source_label = f"generated log ({source.name})"
            generated_log = True

            if not no_cache:
                write_cache(source, data)

    files = data.get("files", [])
    meta = data.get("meta", {})

    # Optional hash-based duplicate detection only for real logs
    if detect_duplicates:
        if generated_log:
            console.print(
                "⚠️ Skipping hash-based duplicate detection for generated/dry-run log.",
                style="yellow",
            )
        else:
            seen_hashes: dict[str, str] = {}
            for f in files:
                path = Path(f["new_path"])
                h = hash_file(path)
                f["hash"] = h
                if h and h in seen_hashes:
                    f["duplicate"] = True
                    for orig_f in files:
                        if orig_f.get("hash") == h:
                            orig_f["duplicate"] = True
                elif h:
                    seen_hashes[h] = str(path)

    # Sorting
    if sort_by == "date":
        files.sort(key=lambda f: f["used_date"])
    elif sort_by == "name":
        files.sort(key=lambda f: Path(f["new_path"]).name.lower())
    elif sort_by == "extension":
        files.sort(key=lambda f: f["extension"])
    else:
        console.print(
            f"⚠️ Unknown sort key '{sort_by}', defaulting to 'date'.", style="yellow"
        )
        files.sort(key=lambda f: f["used_date"])

    # Display
    table = Table(
        title=f"📂 Organizer log — {Path(meta.get('root', '')).name}", show_lines=False
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

        size_str = f"{f['size']:,}"
        path_text = Text(f["new_path"])
        if f.get("duplicate"):
            path_text.stylize("yellow")

        table.add_row(
            str(idx), f["category"], f["extension"], f["used_date"], size_str, path_text
        )
        count += 1

    console.print(table)
    if log_path is not None:
        console.print(f"\n📊 Listed {count} / {len(files)} files from {log_path.name}")
    return count
