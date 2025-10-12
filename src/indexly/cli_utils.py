# New: CLI handlers for tagging, exporting, profiles

import os
import sys
import json
import time
import argparse
from datetime import datetime
from .db_utils import connect_db
from .export_utils import (
    export_results_to_json,
    export_results_to_pdf,
    export_results_to_txt,
)
from .utils import clean_tags
from .config import PROFILE_FILE
from .cache_utils import save_cache, load_cache
from .path_utils import normalize_path
from .migration_manager import run_migrations
from .rename_utils import SUPPORTED_DATE_FORMATS

# CLI display configurations here
command_titles = {
    "index": "[I] n  d  e  x  i  n  g",
    "search": "[S] e  a  r  c  h  i  n  g",
    "regex": "[R] e  g  e  x   S  e  a  r  c  h",
    "tag": "[T] a  g   M  a  n  a  g  e  m  e  n  t",
    "watch": "[W] a  t  c  h  i  n  g     F  o  l  d  e  r  s",
    "stats": "[S] t  a  t  i  s  t  i  c  s",
    "analyze-csv": "[C] S  V   A  n  a  l  y  s  i  s",
}
# --------------------------------------------------------------------------------


def get_search_term(args):
    return getattr(args, "term", None)


def add_common_arguments(parser):
    parser.add_argument("--filetype", nargs="+", help="Filter by filetype(s)")
    parser.add_argument("--date-from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--path-contains", help="Only search files with paths containing this string"
    )
    parser.add_argument("--filter-tag", help="Filter by tag")
    parser.add_argument(
        "--context", type=int, default=150, help="Context characters around match"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip reading/writing cached search results",
    )

    parser.add_argument(
        "--export-format", choices=["txt", "md", "pdf", "json"], help="Export format"
    )
    parser.add_argument(
        "--pdf-lib",
        choices=["fpdf", "reportlab"],
        default="fpdf",
        help="Choose PDF library for PDF export (default: fpdf)",
    )
    parser.add_argument("--output", help="Output file path")


def build_parser():
    from .indexly import (
        handle_index,
        handle_search,
        handle_regex,
        handle_tag,
        run_stats,
        run_analyze_csv,
        run_watch,
        handle_extract_mtw,
        handle_rename_file,
    )

    parser = argparse.ArgumentParser(
        description="Indexly - File Indexing and Search Tool"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Default: if no subcommand is given, show help
    parser.set_defaults(func=lambda args: parser.print_help())

    # Index
    index_parser = subparsers.add_parser("index", help="Index files in a folder")
    index_parser.add_argument("folder", help="Folder to index")
    index_parser.add_argument("--filetype", help="Filter by filetype (e.g. .pdf)")
    index_parser.add_argument(
        "--mtw-extended",
        action="store_true",
        help="Enable extended MTW extraction (extra streams, extra metadata)",
    )
    index_parser.set_defaults(func=handle_index)

    # Search
    search_parser = subparsers.add_parser("search", help="Perform FTS search")
    search_parser.add_argument("term", type=str, help="Search term (FTS5 syntax)")
    search_parser.add_argument("--db", default="index.db", help="Database path")
    add_common_arguments(search_parser)
    search_parser.add_argument(
        "--fuzzy", action="store_true", help="Enable fuzzy search"
    )
    search_parser.add_argument(
        "--fuzzy-threshold", type=int, default=80, help="Fuzzy match threshold (0-100)"
    )
    search_parser.add_argument(
        "--near-distance",
        type=int,
        default=5,
        help="Maximum distance for NEAR operator (default: 5)",
    )
    search_parser.add_argument("--author", help="Filter by author metadata")
    search_parser.add_argument("--camera", help="Filter by camera metadata")
    search_parser.add_argument(
        "--image-created", dest="image_created", help="Filter by image creation date"
    )
    search_parser.add_argument("--format", help="Filter by format")
    search_parser.add_argument("--save-profile", help="Save search profile name")
    search_parser.add_argument("--profile", help="Load search profile name")
    search_parser.set_defaults(func=handle_search)

    # Regex
    regex_parser = subparsers.add_parser("regex", help="Regex search mode")
    regex_parser.add_argument("pattern", help="Regex pattern")
    regex_parser.add_argument("--db", default="index.db", help="Database path")
    add_common_arguments(regex_parser)
    regex_parser.set_defaults(func=handle_regex)

    # Tag
    tag_parser = subparsers.add_parser("tag", help="Manage file tags")
    tag_parser.add_argument(
        "tag_action",
        choices=["add", "remove", "list"],
        help="Action to perform on tags",
    )
    tag_parser.add_argument("--files", nargs="+", help="Files or folders to tag")
    tag_parser.add_argument("--file", help="File to list tags for (used with 'list')")
    tag_parser.add_argument("--tags", nargs="+", help="Tags to add/remove")
    tag_parser.add_argument(
        "--recursive", action="store_true", help="Recursively tag files in folders"
    )
    tag_parser.set_defaults(func=handle_tag)

    # Watch
    watch_parser = subparsers.add_parser(
        "watch", help="Watch folder for changes and auto-index"
    )
    watch_parser.add_argument("folder", help="Folder to watch")
    watch_parser.set_defaults(func=run_watch)

    # Analyze CSV
    csv_parser = subparsers.add_parser("analyze-csv", help="Analyze a CSV file")
    csv_parser.add_argument("file")
    csv_parser.add_argument("--export-path")
    csv_parser.add_argument("--format", choices=["txt", "md"], default="txt")
    csv_parser.set_defaults(func=run_analyze_csv)

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    stats_parser.set_defaults(func=run_stats)

    # Extract MTW
    extract_mtw_parser = subparsers.add_parser(
        "extract-mtw", help="Extract files from a .mtw file (Minitab Worksheet)"
    )
    extract_mtw_parser.add_argument("file", help="Path to the .mtw file")
    extract_mtw_parser.add_argument(
        "--output",
        "-o",
        default=".",
        help="Directory to extract files into (default: current folder)",
    )
    extract_mtw_parser.set_defaults(func=handle_extract_mtw)

    # Rename File(s)
    rename_file_parser = subparsers.add_parser(
        "rename-file",
        help="Rename a file or all files in a directory according to a pattern",
    )
    rename_file_parser.add_argument(
        "path", help="Path to a file or directory to rename"
    )
    rename_file_parser.add_argument(
        "--pattern", help="Renaming pattern (supports {date}, {title}, {counter})"
    )
    rename_file_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be renamed without making changes",
    )
    rename_file_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively rename all files in the given directory",
    )
    rename_file_parser.add_argument(
        "--update-db",
        action="store_true",
        help="Also update database paths after renaming",
    )
    rename_file_parser.add_argument(
        "--date-format",
        type=str,
        choices=SUPPORTED_DATE_FORMATS,
        default="%Y%m%d",
        help="Specify date format to use in filename (default: %%Y%%m%%d)",
    )
    rename_file_parser.add_argument(
        "--counter-format",
        default="d",
        help="Format for counter (e.g. 02d, 03d, d). Default: plain integer.",
    )

    rename_file_parser.set_defaults(func=handle_rename_file)

    # Migrate
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Database migration and schema management (adds missing tables/columns and updates FTS5 prefix/vocab)",
    )
    migrate_sub = migrate_parser.add_subparsers(dest="migrate_command")
    migrate_parser.set_defaults(func=lambda args: migrate_parser.print_help())

    # migrate run
    migrate_run = migrate_sub.add_parser(
        "run", help="Run migrations on the database. Creates a backup by default."
    )
    migrate_run.add_argument(
        "--db", default="index.db", help="Path to the SQLite database file"
    )
    migrate_run.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a backup before running migrations (use with caution)",
    )
    migrate_run.set_defaults(
        func=lambda args: run_migrations(
            args.db, dry_run=False, no_backup=args.no_backup
        )
    )

    # migrate check
    migrate_check = migrate_sub.add_parser(
        "check",
        help="Check if migrations are needed without applying changes. No backup needed in dry-run mode.",
    )
    migrate_check.add_argument(
        "--db", default="index.db", help="Path to the SQLite database file"
    )
    migrate_check.add_argument(
        "--no-backup",
        action="store_true",
        help="Dry-run only; no backup created (for informational checks)",
    )
    migrate_check.set_defaults(
        func=lambda args: run_migrations(
            args.db, dry_run=True, no_backup=args.no_backup
        )
    )
    # migrate history
    migrate_history = migrate_sub.add_parser(
        "history", help="Show migration history from the schema_migrations table."
    )
    migrate_history.add_argument(
        "--db", default="index.db", help="Path to the SQLite database file"
    )
    migrate_history.add_argument(
        "--last",
        type=int,
        default=None,
        help="Show only the last N migrations",
    )
    migrate_history.set_defaults(
        func=lambda args: __import__("indexly.debug_tbl").debug_tbl.show_migrations(
            args.db, last=args.last
        )
    )

    return parser


def add_tags_to_file(file_path, tags, db_path=None):
    file_path = normalize_path(file_path)
    tags = [t.strip().lower() for t in tags if t.strip()]

    conn = connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM file_tags WHERE path = ?", (file_path,))
    existing_tags = (row := cursor.fetchone()) and row["tags"].split(",") or []
    existing_tags = [t.strip().lower() for t in existing_tags if t.strip()]

    all_tags = sorted(set(existing_tags + tags))
    tag_str = ",".join(all_tags)

    cursor.execute(
        "INSERT OR REPLACE INTO file_tags (path, tags) VALUES (?, ?)",
        (file_path, tag_str),
    )
    conn.commit()
    conn.close()


def add_tag_to_file(file_path, new_tag, db_path=None):
    file_path = normalize_path(file_path)
    new_tag = new_tag.strip().lower()

    conn = connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM file_tags WHERE path = ?", (file_path,))
    tags = (row := cursor.fetchone()) and row["tags"].split(",") or []
    tags = [t.strip().lower() for t in tags if t.strip()]

    if new_tag not in tags:
        tags.append(new_tag)
        tags = sorted(set(tags))  # remove duplicates and sort
        tag_str = ",".join(tags)

        cursor.execute(
            "INSERT OR REPLACE INTO file_tags (path, tags) VALUES (?, ?)",
            (file_path, tag_str),
        )
        cursor.execute(
            "UPDATE file_index SET tag = ? WHERE path = ?",
            (tag_str, file_path),
        )
        conn.commit()
        print(f"✅ Tag '{new_tag}' added to {file_path}")
        invalidate_cache_for_file(file_path)
    else:
        print(f"⚠️ Tag '{new_tag}' already exists on {file_path}")

    conn.close()


def filter_files_by_tag(tag, db_path=None):
    conn = connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM file_tags WHERE tags LIKE ?", (f"%{tag}%",))
    rows = cursor.fetchall()
    conn.close()
    return [normalize_path(row["path"]) for row in rows]


def remove_tag_from_file(file_path, tag_to_remove, db_path=None):
    file_path = normalize_path(file_path)
    tag_to_remove = tag_to_remove.strip().lower()

    conn = connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM file_tags WHERE path = ?", (file_path,))
    if (row := cursor.fetchone()) and row["tags"]:
        tags = [t.strip().lower() for t in row["tags"].split(",") if t.strip()]

        if tag_to_remove in tags:
            tags.remove(tag_to_remove)
            if tags:
                tag_str = ",".join(sorted(tags))
                cursor.execute(
                    "UPDATE file_tags SET tags = ? WHERE path = ?",
                    (tag_str, file_path),
                )
            else:
                cursor.execute("DELETE FROM file_tags WHERE path = ?", (file_path,))
            conn.commit()
            print(f"✅ Tag '{tag_to_remove}' removed from {file_path}")
            invalidate_cache_for_file(file_path)
        else:
            print(f"⚠️ Tag '{tag_to_remove}' not found for {file_path}")

    conn.close()


def enrich_results_with_tags(results):
    from .db_utils import get_tags_for_file
    from .fts_core import extract_virtual_tags

    for r in results:
        r["path"] = normalize_path(r["path"])
        db_tags = get_tags_for_file(r["path"]) or []
        virtual_tags = extract_virtual_tags(r["path"], text=r.get("snippet"), meta=None)
        r["tags"] = list(sorted(set(db_tags + virtual_tags)))
    return results


def invalidate_cache_for_file(file_path):
    cache = load_cache()
    changed = False
    for key, entry in list(cache.items()):
        results = entry.get("results", [])
        if any(r["path"] == file_path for r in results):
            del cache[key]
            changed = True
    if changed:
        save_cache(cache)


def apply_profile_to_args(args, profile):
    # Only set term from profile if user didn't pass one this time
    if not getattr(args, "term", None) and not getattr(args, "folder_or_term", None):
        term = profile.get("term")
        if term:
            if hasattr(args, "term"):
                args.term = term
            elif hasattr(args, "folder_or_term"):
                args.folder_or_term = term
    args.filetype = profile.get("filetype", args.filetype)
    args.date_from = profile.get("date_from", args.date_from)
    args.date_to = profile.get("date_to", args.date_to)
    args.path_contains = profile.get("path_contains", args.path_contains)
    args.filter_tag = profile.get("tag_filter", args.filter_tag)
    args.context = profile.get("context", args.context)
    return args


def export_results_to_format(results, output_path, export_format, search_term=None):
    if export_format == "pdf":
        export_results_to_pdf(results, search_term or "", output_path)
    elif export_format == "txt":
        export_results_to_txt(results, output_path, search_term or "")
    elif export_format == "json":
        export_results_to_json(results, output_path, search_term or "")
    else:
        raise ValueError(f"Unsupported export format: {export_format}")
