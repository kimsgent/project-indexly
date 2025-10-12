"""
📄 indexly.py

Purpose:
    CLI entry point and main controller for all actions (index, search, regex, watch, export).

Key Features:
    - Argument parsing for all supported features.
    - Ripple animation during operations.
    - Loads saved profiles, handles exports, real-time watch mode.
    - Delegates to core search, index, and export modules.

Usage:
    indexly search "term"
    indexly index /path --tag important
    indexly regex "pattern"
"""

import os
import re
import sys
import asyncio
import argparse
import logging
import time
import sqlite3
from datetime import datetime
from .ripple import Ripple
from rich import print as rprint
from rapidfuzz import fuzz
from .filetype_utils import extract_text_from_file, SUPPORTED_EXTENSIONS
from .db_utils import connect_db, get_tags_for_file, _sync_path_in_db
from .search_core import search_fts5, search_regex, normalize_near_term
from .extract_utils import update_file_metadata
from .mtw_extractor import _extract_mtw
from .rename_utils import rename_file, rename_files_in_dir, SUPPORTED_DATE_FORMATS
from .profiles import (
    save_profile,
    apply_profile,
)
from .cli_utils import (
    remove_tag_from_file,
    add_tag_to_file,
    export_results_to_format,
    apply_profile_to_args,
    command_titles,
    get_search_term,
    build_parser,
)
from .output_utils import print_search_results, print_regex_results
from pathlib import Path

from .config import DB_FILE
from .path_utils import normalize_path


# Force UTF-8 output encoding (Recommended for Python 3.7+)
sys.stdout.reconfigure(encoding="utf-8")

# Silence noisy INFO/DEBUG logs from extract_msg
logging.getLogger("extract_msg").setLevel(logging.ERROR)

# Silence noisy fontTools logs globally (applies to all modules)
logging.getLogger("fontTools").setLevel(logging.ERROR)


db_lock = asyncio.Lock()


async def async_index_file(full_path, mtw_extended=False):
    from .fts_core import calculate_hash

    """
    Index a single file asynchronously without attempting to sync renames in the DB.
    """
    full_path = normalize_path(full_path)

    try:
        # --- Handle MTW archives ---
        if full_path.lower().endswith(".mtw"):
            extracted_files = _extract_mtw(full_path, extended=mtw_extended)
            if not extracted_files:
                print(f"⚠️ No extractable content in: {full_path}")
                return

            stub_content = f"MTW Archive: {os.path.basename(full_path)}"
            file_hash = calculate_hash(stub_content)
            last_modified = datetime.fromtimestamp(
                os.path.getmtime(full_path)
            ).isoformat()

            async with db_lock:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM file_index WHERE path = ?", (full_path,))
                cursor.execute(
                    "INSERT INTO file_index (path, content, modified, hash) VALUES (?, ?, ?, ?)",
                    (full_path, stub_content, last_modified, file_hash),
                )
                conn.commit()
                conn.close()

            # Index extracted files
            tasks = [
                async_index_file(f, mtw_extended=mtw_extended) for f in extracted_files
            ]
            await asyncio.gather(*tasks)
            return

        # --- Extract content & metadata ---
        content, metadata = extract_text_from_file(full_path)
        if isinstance(content, dict):
            content = " ".join(f"{k}:{v}" for k, v in content.items())
        if not content and not metadata:
            print(f"⏭️ Skipped (no content or metadata): {full_path}")
            return

        if metadata:
            update_file_metadata(full_path, metadata)
            extra_fields = [
                str(metadata[k])
                for k in ("source", "author", "subject", "title", "format", "camera")
                if metadata.get(k)
            ]
            if extra_fields:
                content = (content or "") + " ; " + " ; ".join(extra_fields)

        if not content:
            content = f"File: {os.path.basename(full_path)}"

        file_hash = calculate_hash(content)
        last_modified = datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat()

        # --- DB operations serialized ---
        async with db_lock:
            conn = connect_db()
            cursor = conn.cursor()

            # Skip unchanged file
            cursor.execute("SELECT hash FROM file_index WHERE path = ?", (full_path,))
            row = cursor.fetchone()
            if row and row["hash"] == file_hash:
                conn.close()
                print(f"⏭️ Skipped unchanged: {full_path}")
                return

            # Insert/update index and ensure metadata exists
            cursor.execute("DELETE FROM file_index WHERE path = ?", (full_path,))
            cursor.execute(
                "INSERT INTO file_index (path, content, modified, hash) VALUES (?, ?, ?, ?)",
                (full_path, content, last_modified, file_hash),
            )
            cursor.execute(
                "INSERT OR REPLACE INTO file_metadata (path) VALUES (?)", (full_path,)
            )
            conn.commit()
            conn.close()

        print(f"✅ Indexed: {full_path}")

    except Exception as e:
        print(f"⚠️ Failed to index {full_path}: {e}")


async def scan_and_index_files(root_dir: str, mtw_extended=False):
    root_dir = normalize_path(root_dir)

    conn = connect_db()
    conn.close()

    from .cache_utils import clean_cache_duplicates

    file_paths = [
        os.path.join(folder, f)
        for folder, _, files in os.walk(root_dir)
        for f in files
        if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    tasks = [async_index_file(path, mtw_extended=mtw_extended) for path in file_paths]
    await asyncio.gather(*tasks)

    clean_cache_duplicates()

    log_filename = datetime.now().strftime("%Y-%m-%d_index.log")
    with open(log_filename, "w", encoding="utf-8") as log:
        log.write(f"[INDEX LOG] Completed at {datetime.now().isoformat()}\n")
        log.writelines(f"{path}\n" for path in file_paths)

    print(f"📝 Index log created: {log_filename}")
    return file_paths


def run_stats(args):
    from collections import Counter

    ripple = Ripple(command_titles["stats"], speed="fast", rainbow=True)
    ripple.start()

    try:
        conn = connect_db()
        cursor = conn.cursor()

        total_files = cursor.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
        total_tagged = cursor.execute("SELECT COUNT(*) FROM file_tags").fetchone()[0]
        db_size = os.path.getsize(DB_FILE) / 1024

        ripple.stop()
        print("\n📊 Database Stats:")
        print(f"- Total Indexed Files: {total_files}")
        print(f"- Total Tagged Files: {total_tagged}")
        print(f"- DB Size: {db_size:.1f} KB")

        print("\n🏷️ Top Tags:")
        rows = cursor.execute("SELECT tags FROM file_tags").fetchall()
        all_tags = []

        for row in rows:
            tag_string = row["tags"]
            if tag_string:
                all_tags.extend(t.strip() for t in tag_string.split(",") if t.strip())

        tag_counter = Counter(all_tags)
        for tag, count in tag_counter.most_common(10):
            print(f"  • {tag}: {count}")

    finally:
        ripple.stop()
        conn.close()


# Configure logging
# logging.basicConfig(
#    level=logging.INFO,
#    format="%(asctime)s - %(levelname)s - %(message)s",
#    handlers=[
#        logging.StreamHandler(sys.stdout),
#        logging.FileHandler("indexly.log", mode="w", encoding="utf-8"),
#    ],
# )


def handle_index(args):
    ripple = Ripple("Indexing", speed="fast", rainbow=True)
    ripple.start()
    try:
        logging.info("Indexing started.")
        indexed_files = asyncio.run(
            scan_and_index_files(
                root_dir=normalize_path(args.folder),
                mtw_extended=args.mtw_extended,
            )
        )
        logging.info("Indexing completed.")

    finally:
        ripple.stop()


def handle_search(args):
    term_cli = get_search_term(args)

    if not term_cli:
        print("❌ No search term provided.")
        return

    # Profile-only mode
    if getattr(args, "profile", None):
        from .profiles import load_profile, filter_saved_results

        prof = load_profile(args.profile)
        if prof and prof.get("results"):
            results = filter_saved_results(prof["results"], term_cli)
            print(f"Searching '{term_cli or prof.get('term')}' (profile-only: {args.profile})")
            if results:
                print_search_results(results, term_cli or prof.get("term", ""))
                if args.export_format:
                    export_results_to_format(
                        results,
                        args.output or f"search_results.{args.export_format}",
                        args.export_format,
                        term_cli or prof.get("term", ""),
                    )
            else:
                print("🔍 No matches found in saved profile results.")
            return

    ripple = Ripple(f"Searching '{term_cli}'", speed="medium", rainbow=True)
    ripple.start()

    try:
        results = search_fts5(
            term=term_cli,
            query=None,  # ← no need to pass normalized term
            db_path=getattr(args, "db", DB_FILE),
            context_chars=args.context,
            filetypes=args.filetype,
            date_from=args.date_from,
            date_to=args.date_to,
            path_contains=args.path_contains,
            tag_filter=getattr(args, "filter_tag", None),
            use_fuzzy=getattr(args, "fuzzy", False),
            fuzzy_threshold=getattr(args, "fuzzy_threshold", 80),
            author=getattr(args, "author", None),
            camera=getattr(args, "camera", None),
            image_created=getattr(args, "image_created", None),
            format=getattr(args, "format", None),
            no_cache=args.no_cache,
            near_distance=args.near_distance,
        )
    finally:
        ripple.stop()

    if results:
        print_search_results(results, term_cli, context_chars=args.context)
        if args.export_format:
            export_results_to_format(
                results,
                args.output or f"search_results.{args.export_format}",
                args.export_format,
                term_cli,
            )
    else:
        print("🔍 No matches found.")


def handle_regex(args):
    ripple = Ripple("Regex Search", speed="fast", rainbow=True)
    ripple.start()

    results = []  # ✅ always defined
    pattern = getattr(args, "pattern", None) or getattr(args, "folder_or_term", None)

    try:
        if not pattern:
            print("❌ Missing regex pattern. Use --pattern or provide as argument.")
            sys.exit(1)

        results = search_regex(
            pattern=pattern,
            query=None,
            db_path=getattr(args, "db", DB_FILE),
            context_chars=getattr(args, "context", 150),
            filetypes=getattr(args, "filetype", None),
            date_from=getattr(args, "date_from", None),
            date_to=getattr(args, "date_to", None),
            path_contains=getattr(args, "path_contains", None),
            tag_filter=getattr(args, "filter_tag", None),
            no_cache=getattr(args, "no_cache", False),
        )

    finally:
        ripple.stop()

    print(f"\n[bold underline]Regex Search:[/bold underline] '{pattern}'\n")

    if results:
        print_regex_results(results, pattern, args.context)
        if getattr(args, "export_format", None):
            output_file = args.output or f"regex_results.{args.export_format}"
            export_results_to_format(results, output_file, args.export_format, pattern)
    else:
        print("🔍 No regex matches found.")


def handle_tag(args, db_path=None):
    # Trap missing files/tags early
    if args.tag_action in {"add", "remove"}:
        if not args.files:
            print("⚠️ Please provide at least one file or folder with --files.")
            return
        if not args.tags:
            print("⚠️ Please provide at least one tag with --tags.")
            return

        # Collect all target files
        all_files = []
        for path in args.files:
            norm = normalize_path(path)
            if os.path.isdir(norm):
                # Folder -> scan files
                for root, _, files in os.walk(norm):
                    all_files.extend(
                        [normalize_path(os.path.join(root, f)) for f in files]
                    )
                    if not getattr(args, "recursive", False):
                        break  # only top-level if not recursive
            else:
                all_files.append(norm)

        # Apply tags
        for file in all_files:
            for tag in args.tags:
                if args.tag_action == "add":
                    add_tag_to_file(file, tag, db_path=db_path)
                elif args.tag_action == "remove":
                    remove_tag_from_file(file, tag, db_path=db_path)

        action_emoji = "🏷️" if args.tag_action == "add" else "❌"
        print(
            f"{action_emoji} Tags {args.tags} {args.tag_action}ed on {len(all_files)} file(s)."
        )

    elif args.tag_action == "list":
        if not getattr(args, "file", None):
            print("⚠️ Please provide a file with --file when using 'list'.")
            return
        norm = normalize_path(args.file)
        tags = get_tags_for_file(norm, db_path=db_path)
        print(f"📂 {args.file} has tags: {tags if tags else 'No tags'}")


def run_watch(args):

    ripple = Ripple(command_titles["watch"], speed="fast", rainbow=True)
    ripple.start()
    try:
        from .watcher import start_watcher

        if not os.path.isdir(args.folder):
            print("❌ Invalid folder path.")
            sys.exit(1)
        start_watcher(args.folder)
    finally:
        ripple.stop()


def run_analyze_csv(args):

    ripple = Ripple(command_titles["analyze-csv"], speed="fast", rainbow=True)
    ripple.start()
    try:
        from .csv_analyzer import analyze_csv, export_results

        result = analyze_csv(args.file)
        if result:
            print(result)
            if args.export_path:
                export_results(result, args.export_path, args.format)
        else:
            print("⚠️ No data to analyze or invalid file format.")
    finally:
        ripple.stop()


def handle_extract_mtw(args):
    # Normalize inputs
    file_path = normalize_path(args.file)
    output_dir = (
        normalize_path(args.output) if args.output else os.path.dirname(file_path)
    )

    print(f"📂 Extracting MTW file: {file_path}")

    try:
        extracted_files = _extract_mtw(file_path, output_dir)
    except Exception as e:
        print(f"❌ Error extracting MTW file: {e}")
        return

    if not extracted_files:
        print("⚠️ No files extracted (empty or invalid MTW).")
        return

    print(f"✅ Files successfully extracted to: {normalize_path(output_dir)}")
    for f in extracted_files:
        print(f"   - {normalize_path(f)}")


def handle_rename_file(args):
    """
    Handle renaming of a file or all files in a directory,
    and immediately update DB to reflect the change.
    """

    path = Path(args.path)
    if not path.exists():
        print(f"⚠️ Path not found: {path}")
        return

    # Determine valid date format
    date_format = (
        args.date_format
        if hasattr(args, "date_format") and args.date_format in SUPPORTED_DATE_FORMATS
        else "%Y%m%d"
    )

    # Determine counter format (default = plain integer)
    counter_format = (
        args.counter_format if hasattr(args, "counter_format") else "d"
    )

    # --- Directory handling ---
    if path.is_dir():
        rename_files_in_dir(
            str(path),
            pattern=args.pattern,
            dry_run=args.dry_run,
            recursive=args.recursive,
            update_db=args.update_db,
            date_format=date_format,
            counter_format=counter_format,
        )
        return

    # --- Single file handling ---
    new_path = rename_file(
        str(path),
        pattern=args.pattern,
        dry_run=args.dry_run,
        update_db=args.update_db,
        date_format=date_format,
        counter_format=counter_format,
    )

    # --- Sync rename in DB immediately ---
    if not args.dry_run:
        try:
            _sync_path_in_db(str(path), str(new_path))
        except Exception as e:
            print(f"⚠️ DB sync after rename failed: {e}")

    # --- Output ---
    if args.dry_run:
        print(f"[Dry-run] Would rename: {path} → {new_path}")
    else:
        print(f"✅ Renamed and synced: {path} → {new_path}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if hasattr(args, "profile") and args.profile:
        profile_data = apply_profile(args.profile)
        if profile_data:
            args = apply_profile_to_args(args, profile_data)

    if getattr(args, "save_profile", None):
        save_profile(args.save_profile, args)

    if hasattr(args, "func"):
        args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user.")
        sys.exit(1)
