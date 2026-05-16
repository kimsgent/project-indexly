from pathlib import Path
import json
from rich.console import Console
from rich.table import Table
from rich.text import Text

from indexly.ignore_defaults.loader import load_ignore_rules
from indexly.organize.lister_fallback import generate_log_from_tree
from indexly.organize.lister_cache import read_cache, write_cache
from indexly.organize.lister_hash import hash_file

console = Console()


def _sorted_logs(logs):
    return sorted(
        (p for p in logs if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _print_log_choice(log_path: Path, source: str) -> None:
    console.print(
        f"🔎 Using organizer log: {log_path} ({source})",
        style="cyan",
    )


def _discover_log(path: Path) -> Path:
    """Find organizer log from file or directory"""
    path = Path(path).expanduser().resolve()

    if path.is_file():
        _print_log_choice(path, "explicit file")
        return path

    if path.is_dir():
        search_tiers = [
            ("log/ directory", (path / "log").glob("organized_*.json")),
            ("root directory", path.glob("organized_*.json")),
            ("nested fallback search", path.rglob("organized_*.json")),
        ]

        for source, candidates in search_tiers:
            logs = _sorted_logs(candidates)
            if logs:
                _print_log_choice(logs[0], source)
                return logs[0]

        raise FileNotFoundError(f"No organizer logs found in {path}")

    raise FileNotFoundError(path)


def _path_for_hash(file_entry: dict) -> Path:
    """Prefer the executed target path, then fall back to the original source."""
    for key in ("new_path", "original_path"):
        value = file_entry.get(key)
        if not value:
            continue
        path = Path(value)
        if path.is_file():
            return path
    return Path(file_entry.get("new_path") or file_entry.get("original_path", ""))


def _detect_hash_duplicates(files: list[dict]) -> int:
    """Mark hash duplicates in one pass and return unreadable/missing file count."""
    skipped_hash_files = 0
    first_index_by_hash: dict[str, int] = {}

    for idx, file_entry in enumerate(files):
        path = _path_for_hash(file_entry)
        h = hash_file(path)
        file_entry["hash"] = h

        if h is None:
            skipped_hash_files += 1
            continue

        first_idx = first_index_by_hash.get(h)
        if first_idx is None:
            first_index_by_hash[h] = idx
            continue

        files[first_idx]["duplicate"] = True
        file_entry["duplicate"] = True

    return skipped_hash_files


def _sort_files(files: list[dict], sort_by: str) -> bool:
    if sort_by == "date":
        files.sort(key=lambda f: f["used_date"])
        return True
    if sort_by == "name":
        files.sort(key=lambda f: Path(f["new_path"]).name.lower())
        return True
    if sort_by == "extension":
        files.sort(
            key=lambda f: (
                f.get("extension") in {"", None},
                (f.get("extension") or "").lower(),
                Path(f["new_path"]).name.lower(),
            )
        )
        return True
    return False


def _matches_filters(
    file_entry: dict,
    *,
    ext: str | None,
    category: str | None,
    date: str | None,
    duplicates_only: bool,
) -> bool:
    if ext and file_entry["extension"] != ext:
        return False
    if category and file_entry["category"] != category:
        return False
    if date and file_entry["used_date"] != date:
        return False
    if duplicates_only and not file_entry.get("duplicate"):
        return False
    return True


def _active_filters(
    *,
    ext: str | None,
    category: str | None,
    date: str | None,
    duplicates_only: bool,
) -> list[str]:
    filters = []
    if ext:
        filters.append(f"extension={ext}")
    if category:
        filters.append(f"category={category}")
    if date:
        filters.append(f"date={date}")
    if duplicates_only:
        filters.append("duplicates only")
    return filters


def _format_values(values) -> str:
    normalized = sorted({value or "(no extension)" for value in values})
    return ", ".join(normalized[:12]) + (" ..." if len(normalized) > 12 else "")


def _print_empty_filter_feedback(
    files: list[dict],
    *,
    ext: str | None,
    category: str | None,
    date: str | None,
    duplicates_only: bool,
    detect_duplicates: bool,
) -> None:
    filters = _active_filters(
        ext=ext,
        category=category,
        date=date,
        duplicates_only=duplicates_only,
    )
    if not filters:
        return

    console.print(
        f"⚠️ No files matched the applied filters: {', '.join(filters)}",
        style="yellow",
    )

    if ext:
        console.print(
            f"Available extensions: {_format_values(f['extension'] for f in files)}",
            style="dim",
        )
    if category:
        console.print(
            f"Available categories: {_format_values(f['category'] for f in files)}",
            style="dim",
        )
    if date:
        console.print(
            f"Available dates: {_format_values(f['used_date'] for f in files)}",
            style="dim",
        )
    if duplicates_only:
        if detect_duplicates:
            console.print("No hash duplicates were detected.", style="dim")
        else:
            console.print(
                "No duplicate entries are marked in the log. Use --detect-duplicates "
                "to hash accessible files.",
                style="dim",
            )


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
    """List files from organizer JSON log with cache, sorting, optional duplicates, and summary."""

    data = None
    generated_log = False
    skipped_hash_files = 0
    source = Path(source).expanduser()

    # 1️⃣ Load cache or discover log
    if not no_cache:
        data = read_cache(source)

    if data:
        console.print(
            f"🔎 Using cached lister log: {source.resolve() / '.indexly' / 'lister_cache.json'}",
            style="cyan",
        )
    else:
        try:
            log_path = _discover_log(source)
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
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
            generated_log = True

            if not no_cache:
                write_cache(source, data, mode="dry-run", skip_invalid_root=True)

    raw_files = data.get("files", [])
    meta = data.get("meta", {})
    if meta.get("mode") == "dry-run":
        generated_log = True

    # ── Apply .indexlyignore rules (Option A) ──
    root_path = Path(meta.get("root") or source).resolve()
    ignore_rules = load_ignore_rules(root_path)
    files = [
        f
        for f in raw_files
        if not ignore_rules.should_ignore(Path(f["new_path"]), root=root_path)
    ]
    ignored_count = len(raw_files) - len(files)

    # 2️⃣ Optional hash-based duplicate detection
    if detect_duplicates:
        skipped_hash_files = _detect_hash_duplicates(files)

    # 3️⃣ Sorting
    if not _sort_files(files, sort_by):
        console.print(
            f"⚠️ Unknown sort key '{sort_by}', defaulting to 'date'.", style="yellow"
        )
        _sort_files(files, "date")

    filtered_files = [
        f
        for f in files
        if _matches_filters(
            f,
            ext=ext,
            category=category,
            date=date,
            duplicates_only=duplicates_only,
        )
    ]
    filtered_count = len(files) - len(filtered_files)

    # 4️⃣ Display table
    table = Table(
        title=f"📂 Organizer log — {Path(meta.get('root', '')).name}", show_lines=False
    )
    table.add_column("#", justify="right")
    table.add_column("Category")
    table.add_column("Ext")
    table.add_column("Date")
    table.add_column("Size", justify="right")
    table.add_column("Path")

    for idx, f in enumerate(filtered_files, 1):
        size_str = f"{f['size']:,}"
        path_text = Text(f["new_path"])
        if f.get("duplicate"):
            path_text.stylize("yellow")

        table.add_row(
            str(idx), f["category"], f["extension"], f["used_date"], size_str, path_text
        )

    console.print(table)

    if not filtered_files and files:
        _print_empty_filter_feedback(
            files,
            ext=ext,
            category=category,
            date=date,
            duplicates_only=duplicates_only,
            detect_duplicates=detect_duplicates,
        )
    elif not files and ignored_count:
        console.print("⚠️ All files were excluded by .indexlyignore.", style="yellow")

    # 5️⃣ Summary
    summary_lines = [
        f"🗂 Total files in log: {len(raw_files)}",
        f"🚫 Ignored by .indexlyignore: {ignored_count}",
        f"🔎 Filtered out: {filtered_count}",
        f"✅ Files listed: {len(filtered_files)}",
    ]

    if detect_duplicates:
        duplicates = sum(1 for f in files if f.get("duplicate"))
        if duplicates > 0:
            summary_lines.append(f"⚠️ Duplicates detected: {duplicates}")

    if skipped_hash_files:
        summary_lines.append(
            f"⚠️ Files skipped during hash detection: {skipped_hash_files}"
        )

    if generated_log:
        summary_lines.append("ℹ️ Paths are simulated; no filesystem changes were made.")

    console.print("\n" + "\n".join(summary_lines))
    return len(filtered_files)
