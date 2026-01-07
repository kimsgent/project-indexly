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
import json
import asyncio
import argparse
import logging
import time
import sqlite3
import pandas as pd
import numpy as np
from rich.console import Console
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
from .clean_csv import clear_cleaned_data
from .update_utils import check_for_updates

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
from indexly.license_utils import show_full_license, print_version, show_full_license
from .config import DB_FILE
from .path_utils import normalize_path
from .db_update import check_schema, apply_migrations
from .log_utils import _unified_log_entry, _default_logger, shutdown_logger




# Force UTF-8 output encoding (Recommended for Python 3.7+)
sys.stdout.reconfigure(encoding="utf-8")

# Silence noisy INFO/DEBUG logs from extract_msg
logging.getLogger("extract_msg").setLevel(logging.ERROR)

# Silence noisy fontTools logs globally (applies to all modules)
logging.getLogger("fontTools").setLevel(logging.ERROR)


db_lock = asyncio.Lock()

console = Console()


async def async_index_file(
    full_path,
    mtw_extended=False,
    force_ocr=False,
    disable_ocr=False,
):
    from .fts_core import calculate_hash
    from .semantic_index import (
        semantic_filter_text,
        build_semantic_fts_text,
        split_metadata_tiers,
        build_technical_filters,
    )
    import logging

    logger = logging.getLogger(__name__)
    full_path = normalize_path(full_path)

    try:
        # -------------------------
        # MTW archives (Tier 3 only)
        # -------------------------
        if full_path.lower().endswith(".mtw"):
            extracted_files = _extract_mtw(full_path, extended=mtw_extended)
            if not extracted_files:
                print(f"⚠️ No extractable content in: {full_path}")
                return

            stub_content = f"MTW Archive {os.path.basename(full_path)}"
            clean_content = semantic_filter_text(stub_content)
            content = clean_content

            file_hash = calculate_hash(content)
            last_modified = datetime.fromtimestamp(
                os.path.getmtime(full_path)
            ).isoformat()

            async with db_lock:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM file_index WHERE path = ?", (full_path,))
                cursor.execute(
                    """
                    INSERT INTO file_index (path, content, clean_content, modified, hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (full_path, content, clean_content, last_modified, file_hash),
                )
                update_file_metadata(
                    full_path, {}, conn=conn
                )  # empty metadata for MTW stub
                conn.commit()
                conn.close()

            await asyncio.gather(
                *(
                    async_index_file(f, mtw_extended=mtw_extended)
                    for f in extracted_files
                )
            )
            return

        # -------------------------
        # Extract raw content & metadata
        # -------------------------
        raw_text, metadata = extract_text_from_file(
            full_path,
            force_ocr=force_ocr,
            disable_ocr=disable_ocr,
        )
        if not raw_text and not metadata:
            print(f"⏭️ Skipped (no content or metadata): {full_path}")
            return

        # -------------------------
        # Tier 1 – Human text
        # -------------------------
        clean_content = semantic_filter_text(raw_text or "", tier="human")

        # -------------------------
        # Tier 2 / Tier 3 split
        # -------------------------
        semantic_meta_text = ""
        technical_meta_data = {}
        if metadata:
            semantic_meta, technical_meta = split_metadata_tiers(metadata)
            unknown_keys = set(metadata) - set(semantic_meta) - set(technical_meta)
            if unknown_keys:
                logger.debug(
                    "Unknown metadata keys ignored for %s: %s",
                    full_path,
                    sorted(unknown_keys),
                )

            # Tier-2 FTS text filtered & weighted
            semantic_meta_text = build_semantic_fts_text(semantic_meta, weighted=True)
            technical_meta_data = build_technical_filters(technical_meta)

        # -------------------------
        # Final FTS content
        # -------------------------
        content = f"{clean_content} {semantic_meta_text}".strip()
        if not content:
            content = semantic_filter_text(
                f"File {os.path.basename(full_path)}", tier="human"
            )

        file_hash = calculate_hash(content)
        last_modified = datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat()

        # -------------------------
        # DB operations (serialized)
        # -------------------------
        async with db_lock:
            conn = connect_db()
            cursor = conn.cursor()

            # Skip if hash unchanged
            cursor.execute("SELECT hash FROM file_index WHERE path = ?", (full_path,))
            row = cursor.fetchone()
            if row and row["hash"] == file_hash:
                conn.close()
                print(f"⏭️ Skipped unchanged: {full_path}")
                return

            # Update file_index
            cursor.execute("DELETE FROM file_index WHERE path = ?", (full_path,))
            cursor.execute(
                """
                INSERT INTO file_index (path, content, clean_content, modified, hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (full_path, content, clean_content, last_modified, file_hash),
            )

            # Merge structured + JSON metadata using same connection
            full_metadata = (
                {
                    k: metadata.get(k)
                    for k in [
                        "title",
                        "author",
                        "subject",
                        "created",
                        "last_modified",
                        "last_modified_by",
                        "camera",
                        "image_created",
                        "dimensions",
                        "format",
                        "gps",
                    ]
                }
                if metadata
                else {}
            )

            # fallback from technical_meta_data
            for key, value in technical_meta_data.items():
                if key in full_metadata and not full_metadata[key]:
                    full_metadata[key] = value

            # Pass the active connection to avoid "database is locked"
            update_file_metadata(full_path, full_metadata, conn=conn)

            conn.commit()
            conn.close()

        print(f"✅ Indexed: {full_path}")

    except Exception as e:
        print(f"⚠️ Failed to index {full_path}: {e}")


async def scan_and_index_files(
    root_dir: str,
    mtw_extended=False,
    force_ocr=False,
    disable_ocr=False,
    ignore_path: str | None = None,  # <-- path to custom .indexlyignore
    preset: str = "standard",        # <-- default preset
):
    from .cache_utils import clean_cache_duplicates
    from indexly.ignore import IgnoreRules
    from indexly.ignore_defaults.loader import load_ignore_template

    root_dir = normalize_path(root_dir)
    root_path = Path(root_dir).resolve()

    # Ensure DB exists
    conn = connect_db()
    conn.close()

    # -------------------------
    # Load ignore rules
    # -------------------------
    if ignore_path:
        custom_ignore = Path(ignore_path)
        if custom_ignore.exists():
            content = custom_ignore.read_text(encoding="utf-8")
            ignore = IgnoreRules(content.splitlines())
        else:
            print(f"⚠️ Custom ignore file not found: {ignore_path}")
            ignore = IgnoreRules(load_ignore_template(preset).splitlines())
    else:
        local_ignore = root_path / ".indexlyignore"
        if local_ignore.exists():
            content = local_ignore.read_text(encoding="utf-8")
            ignore = IgnoreRules(content.splitlines())
        else:
            ignore = IgnoreRules(load_ignore_template(preset).splitlines())

    # -------------------------
    # Collect supported files with ignore filtering
    # -------------------------
    file_paths = []
    for folder, _, files in os.walk(root_path):
        for f in files:
            file_path = Path(folder) / f
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            # Pass root_path so IgnoreRules can compute relative path
            if ignore.should_ignore(file_path, root_path):
                continue
            file_paths.append(str(file_path))

    if not file_paths:
        print("⚠️ No supported files found.")
        return []

    # -------------------------
    # Record start time
    # -------------------------
    start_time = datetime.now()

    # -------------------------
    # Index files asynchronously
    # -------------------------
    tasks = [
        async_index_file(
            path,
            mtw_extended=mtw_extended,
            force_ocr=force_ocr,
            disable_ocr=disable_ocr,
        )
        for path in file_paths
    ]
    await asyncio.gather(*tasks)

    # -------------------------
    # Cache hygiene
    # -------------------------
    clean_cache_duplicates()

    # -------------------------
    # Logging (post-index only)
    # -------------------------
    for path in file_paths:
        entry = _unified_log_entry("FILE_INDEXED", path)
        _default_logger.log(entry)  # async-safe

    summary_entry = {
        "event": "INDEX_SUMMARY",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "root": str(root_dir),
        "count": len(file_paths),
        "duration_seconds": (datetime.now() - start_time).total_seconds(),
    }

    _default_logger.log(summary_entry)  # async-safe
    print(f"📝 Indexed {len(file_paths)} files and logged summary")

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

        async def _run():
            return await scan_and_index_files(
                root_dir=normalize_path(args.folder),
                mtw_extended=args.mtw_extended,
                force_ocr=args.ocr,
                disable_ocr=args.no_ocr,
                ignore_path=getattr(args, "ignore", None),
            )

        indexed_files = asyncio.run(_run())
        logging.info("Indexing completed.")

    finally:
        ripple.stop()
        shutdown_logger(timeout=2.0)


def handle_ignore_init(args):
    """
    Initialize or upgrade a .indexlyignore file in the target folder.
    """

    from indexly.ignore_defaults.loader import load_ignore_template
    from indexly.ignore_defaults.validator import validate_template

    target = Path(normalize_path(args.folder))
    ignore_file = target / ".indexlyignore"

    # -------------------------
    # Load preset template
    # -------------------------
    template = load_ignore_template(args.preset)
    valid, _ = validate_template(template)
    if not valid:
        print(f"⚠️ Preset '{args.preset}' invalid, using minimal fallback.")
        template = (
            "# Minimal fallback ignore template\n"
            ".cache/\n"
            "__pycache__/\n"
            "*.tmp\n"
            "*.log\n"
        )

    # -------------------------
    # UPGRADE MODE
    # -------------------------
    if args.upgrade:
        if not ignore_file.exists():
            print("⚠️ No .indexlyignore found to upgrade.")
            return

        existing_lines = ignore_file.read_text(encoding="utf-8").splitlines()
        existing_set = set(line.strip() for line in existing_lines if line.strip())

        new_lines = [
            line for line in template.splitlines()
            if line.strip() and line.strip() not in existing_set
        ]

        if not new_lines:
            print("✅ .indexlyignore already up to date.")
            return

        with ignore_file.open("a", encoding="utf-8") as f:
            f.write("\n\n# --- Indexly upgrade additions ---\n")
            f.write("\n".join(new_lines))

        print(
            f"🔁 Upgraded .indexlyignore at {ignore_file} "
            f"(preset: {args.preset}, +{len(new_lines)} rules)"
        )
        return

    # -------------------------
    # INIT MODE
    # -------------------------
    if ignore_file.exists():
        print(f"⚠️ .indexlyignore already exists at {ignore_file}")
        return

    ignore_file.write_text(template, encoding="utf-8")
    print(
        f"✅ Created .indexlyignore at {ignore_file} "
        f"(preset: {args.preset})"
    )

def handle_ignore_show(args):
    """
    Display active ignore rules for a folder.
    Read-only, no side effects.
    """

    from indexly.ignore_defaults.loader import load_ignore_rules
    from indexly.ignore.ignore_rules import IgnoreRules

    root = Path(normalize_path(args.folder))

    # Load rules using the SAME logic as indexing
    ignore = load_ignore_rules(
        root=root,
        custom_ignore=None,
        preset=args.preset,
    )

    local_ignore = root / ".indexlyignore"

    # -------------------------
    # Header
    # -------------------------
    print(f"📂 Folder: {root}")

    if local_ignore.exists():
        print("📄 Ignore source: project-local .indexlyignore")
        print(f"   Path: {local_ignore}")
    else:
        print("📄 Ignore source: preset")
        print(f"   Preset: {args.preset}")

    # -------------------------
    # Rules
    # -------------------------
    rules = ignore._rules  # intentional internal view

    if not rules:
        print("\n⚠️ No active ignore rules.")
        return

    print("\nActive ignore rules:")
    for r in rules:
        print(f"  - {r}")

    # -------------------------
    # Effective view
    # -------------------------
    if args.effective:
        print("\nEffective (normalized) rules:")
        for r in sorted(set(rules)):
            print(f"  - {r}")


def handle_search(args):
    """Handle the `indexly search` command."""
    from .profiles import (
        load_profile,
        filter_saved_results,
        save_profile,
    )

    term_cli = get_search_term(args)

    if not term_cli:
        print("❌ No search term provided.")
        return

    # ─────────────────────────────────────────────
    # PROFILE-ONLY MODE: reuse stored results
    # ─────────────────────────────────────────────
    if getattr(args, "profile", None):
        prof = load_profile(args.profile)
        if prof and prof.get("results"):
            results = filter_saved_results(prof["results"], term_cli)
            print(
                f"Searching '{term_cli or prof.get('term')}' (profile-only: {args.profile})"
            )
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

    # ─────────────────────────────────────────────
    # LIVE SEARCH MODE
    # ─────────────────────────────────────────────
    ripple = Ripple(f"Searching '{term_cli}'", speed="medium", rainbow=True)
    ripple.start()

    try:
        results = search_fts5(
            term=term_cli,
            query=None,  # normalized term not required
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

    # ─────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────
    if results:
        print_search_results(results, term_cli, context_chars=args.context)
        if args.export_format:
            export_results_to_format(
                results,
                args.output or f"search_results.{args.export_format}",
                args.export_format,
                term_cli,
            )

        # 🟢 SAVE PROFILE if requested
        if getattr(args, "save_profile", None):
            save_profile(args.save_profile, args, results)
            print(
                f"💾 Profile '{args.save_profile}' saved with {len(results)} result(s)."
            )

    else:
        print("🔍 No matches found.")


def handle_regex(args):
    from .profiles import save_profile  # ensure import

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

        # ✅ Save profile if requested
        if getattr(args, "save_profile", None):
            save_profile(args.save_profile, args, results)
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


def clear_cleaned_data_handler(args):
    if getattr(args, "all", False):
        clear_cleaned_data(remove_all=True)
    elif getattr(args, "file", None):
        clear_cleaned_data(file_path=args.file)
    else:
        print("⚠️ Please provide a file path or use --all to remove all entries.")


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
    counter_format = args.counter_format if hasattr(args, "counter_format") else "d"

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


def handle_update_db(args):
    """Handle the update-db CLI command."""

    print("🔧 Checking database schema...")
    conn = connect_db(args.db) if args.db else connect_db()

    if args.apply:
        print("🛠️ Applying schema updates...")
        apply_migrations(conn, dry_run=False)
    else:
        apply_migrations(conn, dry_run=True)

    conn.close()
    print("✅ Done.")


def handle_show_help(args):
    """Display CLI help for all commands, with optional Markdown or detailed output."""
    import argparse
    from textwrap import indent
    from indexly.indexly import build_parser  # adjust import if needed

    parser = build_parser()

    categories = {
        "Indexing & Watching": ["index", "watch"],
        "Searching": ["search", "regex"],
        "Organizing & Listing": ["organize", "lister"],
        "Tagging & File Operations": ["tag", "rename-file"],
        "Analysis & Data Inspection": [
            "analyze-csv",
            "analyze-json",
            "analyze-file",
            "analyze-db",
            "clear-data",
            "read-json",
        ],
        "Analysis & Extraction": ["extract-mtw"],
        "Backup, Restore & Compare": ["backup", "restore", "compare"],
        "Database Maintenance": ["update-db", "migrate", "stats"],
        "Logs & Maintenance": ["log-clean"],
        "Meta": ["show-help"],
    }

    # collect subcommands
    subparsers = {}
    for action in parser._subparsers._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers.update(action.choices)

    def extract_summary(subparser):
        help_lines = subparser.format_help().splitlines()

        skip_prefixes = (
            "usage:",
            "positional arguments:",
            "options:",
            "optional arguments:",
        )

        for line in help_lines:
            line = line.strip()
            if not line:
                continue
            if any(line.lower().startswith(p) for p in skip_prefixes):
                continue
            return line

        return "(no description)"

    # Markdown output
    if getattr(args, "markdown", False):
        print("# 🧭 Indexly Command Reference\n")
        print("A categorized overview of all Indexly commands and their purpose.\n")
        for category, cmd_list in categories.items():
            print(f"## {category}\n")
            print("| Command | Description |")
            print("|----------|-------------|")
            for cmd in cmd_list:
                sp = subparsers.get(cmd)
                if not sp:
                    continue
                desc = extract_summary(sp)
                print(f"| `{cmd}` | {desc} |")
            print()
        print("_Use `indexly <command> --help` for detailed usage instructions._\n")
        return

    # CLI output (terminal)
    print("\n📚 **Indexly Commands Overview**\n")

    for category, cmd_list in categories.items():
        print(f"🔹 {category}")
        for cmd in cmd_list:
            sp = subparsers.get(cmd)
            if not sp:
                continue
            desc = extract_summary(sp)
            print(f"   • {cmd:<15} — {desc}")

            if getattr(args, "details", False):
                # Only show the concise usage block, not the entire argparse dump
                usage_line = next(
                    (
                        l.strip()
                        for l in sp.format_help().splitlines()
                        if l.strip().startswith("usage:")
                    ),
                    None,
                )
                if usage_line:
                    print(indent(f"\n{usage_line}\n", "      "))

                # Show only the "options" section in indented style
                help_lines = sp.format_help().splitlines()
                options_section = []
                capture = False
                for line in help_lines:
                    if line.strip().lower().startswith("options"):
                        capture = True
                        continue
                    if capture:
                        if line.strip() == "":
                            break
                        options_section.append(line)
                if options_section:
                    print(indent("\n".join(options_section) + "\n", "      "))

        print()

    print("💡 Tip: Use `indexly <command> --help` for full details.\n")


def main():
    parser = build_parser()

    # -----------------------------
    # 1) Parse top-level arguments
    # -----------------------------
    args, remaining_args = parser.parse_known_args()

    # Handle top-level flags first
    if getattr(args, "show_license", False):
        show_full_license()
        sys.exit(0)

    if getattr(args, "version", False):
        print_version()
        sys.exit(0)

    # ----------------------------------
    # 2) Automatic update check (FIXED)
    # ----------------------------------
    if not getattr(args, "no_update_check", False):
        try:
            info = check_for_updates()
            if info["update_available"]:
                console.print(
                    f"\n[bold yellow]🔔 New indexly version available: "
                    f"{info['latest']} (you run {info['current']})[/bold yellow]\n"
                )
        except Exception:
            pass

    # ----------------------------------
    # 3) Manual "--check-updates" mode
    # ----------------------------------
    if getattr(args, "check_updates", False):
        info = check_for_updates()
        console.print(f"Current: {info['current']}")
        console.print(f"Latest:  {info['latest'] or 'unknown'}")
        console.print(
            "Update available: " + ("yes" if info["update_available"] else "no")
        )
        sys.exit(0)

    # --------------------------
    # 4) Full argument parsing
    # --------------------------
    args = parser.parse_args()

    # Optional: profile support
    if hasattr(args, "profile") and args.profile:
        profile_data = apply_profile(args.profile)
        if profile_data:
            args = apply_profile_to_args(args, profile_data)

    # --------------------------
    # 5) Dispatch subcommand
    # --------------------------
    if hasattr(args, "func"):
        args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user.")
        sys.exit(1)
