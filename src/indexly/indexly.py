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
from .cleaning.auto_clean import (
    auto_clean_csv,
    load_cleaned_data,
    _summarize_cleaning_results,
)
from .clean_csv import (
    clear_cleaned_data,
    _summarize_post_clean,
    _remove_outliers,
    _normalize_numeric,
)
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
from .csv_analyzer import analyze_csv, export_results, detect_delimiter
from .visualize_timeseries import visualize_timeseries_plot
from .visualize_csv import (
    visualize_data,
    visualize_scatter_plotly,
    visualize_pie_plot,
    visualize_bar_plot,
    visualize_line_plot,
    apply_transformation,
    ensure_optional_packages,
)

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


def run_analyze_csv(args):
    """
    Handles `indexly analyze-csv` command including auto-cleaning, exporting, and visualization.
    Fully compatible with --auto-clean, --datetime-formats, --show-summary, --normalize, --remove-outliers, --show-chart, etc.
    """
    console = Console()
    ripple = Ripple("CSV Analysis", speed="fast", rainbow=True)
    ripple.start()
    time.sleep(0.3)

    df = None
    raw_csv_df = None
    summary_records = []

    # --- Step 0: Load raw CSV ---
    try:
        raw_csv_df = pd.read_csv(
            args.file, delimiter=detect_delimiter(args.file), encoding="utf-8"
        )
    except Exception:
        raw_csv_df = None

    # Fallback for misparsed single-column CSV
    if raw_csv_df is not None and raw_csv_df.shape[1] == 1:
        first_col_name = raw_csv_df.columns[0]
        if ";" in first_col_name or "," in first_col_name:
            console.print(
                "🔁 Retrying CSV load with dynamic delimiter detection...",
                style="bold yellow",
            )
            delimiter = detect_delimiter(args.file)
            raw_csv_df = pd.read_csv(args.file, delimiter=delimiter, encoding="utf-8")

    # --- Step 1: Use previously cleaned data if requested ---
    if getattr(args, "use_cleaned", False):
        df = load_cleaned_data(args.file)
        if df is None:
            console.print(
                "[yellow]⚠️ No saved cleaned data found. Falling back to raw CSV.[/yellow]"
            )

    # --- Step 2: Auto-clean if requested ---
    if getattr(args, "auto_clean", False):
        df, summary_records = auto_clean_csv(
            args.file,
            fill_method=getattr(args, "fill_method", "mean"),
            persist=getattr(args, "save_data", True),
            verbose=True,
            derive_dates=getattr(args, "derive_dates", "all"),
            user_datetime_formats=getattr(args, "datetime_formats", None),
            date_threshold=getattr(args, "date_threshold", 0.3),
        )

        # Optional export
        export_path = getattr(args, "export_cleaned", None)
        if export_path:
            export_fmt = getattr(args, "export_format", "csv")
            console.print(
                f"[cyan]Exporting cleaned dataset to {export_path} ({export_fmt})...[/cyan]"
            )
            try:
                if export_fmt == "csv":
                    df.to_csv(export_path, index=False)
                elif export_fmt == "json":
                    df.to_json(export_path, orient="records", indent=2)
                elif export_fmt == "parquet":
                    df.to_parquet(export_path, index=False)
                elif export_fmt == "excel":
                    df.to_excel(export_path, index=False)
                console.print("[green]✅ Cleaned data exported successfully![/green]")
            except Exception as e:
                console.print(f"[red]❌ Export failed: {e}[/red]")

    # --- Step 3: Analyze CSV ---
    if df is None:
        raw_df, df_stats, table_output = analyze_csv(args.file)
        raw_for_plot = raw_csv_df if raw_csv_df is not None else raw_df
    else:
        _, df_stats, table_output = analyze_csv(df, from_df=True)
        raw_for_plot = (
            df
            if getattr(args, "auto_clean", False)
            else (raw_csv_df if raw_csv_df is not None else df)
        )

    ripple.stop()

    # --- Step 4: Display results ---
    def _is_valid_stats(stats_obj):
        if stats_obj is None:
            return False
        if isinstance(stats_obj, (pd.DataFrame, pd.Series)):
            return not stats_obj.empty
        if isinstance(stats_obj, (list, tuple, dict)):
            return len(stats_obj) > 0
        if isinstance(stats_obj, str):
            return bool(stats_obj.strip())
        return True

    if _is_valid_stats(df_stats):
        console.print("\n")

        if isinstance(table_output, str) and table_output.strip():
            console.print(
                "[bold cyan]ℹ️ Displaying statistics for dataset[/bold cyan]\n"
            )
            print(table_output)
        else:
            console.print("[dim]ℹ️ No formatted output table available.[/dim]")

        if getattr(args, "show_summary", False):
            if summary_records:
                _summarize_cleaning_results(summary_records)
            else:
                console.print(
                    "[dim]ℹ️ No cleaning summary available (used pre-cleaned data).[/dim]"
                )

            console.print("\n📊 Extended Data Types Overview", style="bold green")
            if df is None or not hasattr(df, "dtypes"):
                console.print(
                    "[yellow]⚠️ No valid DataFrame available for extended type overview.[/yellow]"
                )
            else:
                for col, dtype in df.dtypes.items():
                    console.print(f"• {col}: {dtype}")

        # Optional export of analysis results
        if getattr(args, "export_path", None):
            export_results(
                table_output, args.export_path, getattr(args, "format", "txt")
            )

        # Optional post-clean numeric transformations
        if getattr(args, "normalize", False):
            df, norm_summary = _normalize_numeric(df)
            console.print("[cyan]→ Normalization applied to numeric columns.[/cyan]")
            _summarize_post_clean(norm_summary, "📏 Normalization Summary")

        if getattr(args, "remove_outliers", False):
            df, out_summary = _remove_outliers(df)
            console.print(
                "[magenta]→ Outliers removed using IQR/z-score thresholds.[/magenta]"
            )
            _summarize_post_clean(out_summary, "📉 Outlier Removal Summary")
    

        # from indexly.visualize_timeseries import visualize_timeseries_plot

        df_clean = df  # or df returned from auto-clean

        # Example: after the data cleaning and summary stage:
        if args.timeseries or getattr(args, "plot_timeseries", False):
            try:
                y_cols = [c.strip() for c in getattr(args, "y", "").split(",") if c.strip()] or None
                visualize_timeseries_plot(
                    df=df_clean,
                    x_col=getattr(args, "x", None),
                    y_cols=y_cols,
                    freq=getattr(args, "freq", None),
                    agg=getattr(args, "agg", "mean"),
                    rolling=getattr(args, "rolling", None),
                    mode=getattr(args, "mode", "interactive"),
                    output=getattr(args, "output", None),
                    title=getattr(args, "title", None),
                )
            except Exception as e:
                Console().print(f"[red]❌ Timeseries visualization failed: {e}[/red]")


        # --- Step 5: Visualization (only if requested) ---

        show_chart = getattr(args, "show_chart", None)  # ascii, static, interactive
        chart_type = getattr(args, "chart_type", None)  # hist, box, scatter, bar, pie, line
        mode = show_chart or "static"
        output_path = getattr(args, "export_plot", None)
        x_col = getattr(args, "x_col", None)
        y_col = getattr(args, "y_col", None)
        transform_mode = getattr(args, "transform", "none").lower()
        auto_transform = transform_mode == "auto"

        # Prepare plotting DataFrame
        plot_df = raw_for_plot.copy() if "raw_for_plot" in locals() else None
        if plot_df is not None:
            plot_df.columns = [c.strip() for c in plot_df.columns]
            for col in plot_df.columns:
                if plot_df[col].dtype == "object":
                    cleaned = plot_df[col].astype(str).str.replace(r"[\$,]", "", regex=True).str.strip()
                    numeric_col = pd.to_numeric(cleaned, errors="coerce")
                    if numeric_col.notna().mean() > 0.5:
                        plot_df[col] = numeric_col

        numeric_cols = plot_df.select_dtypes(include=np.number).columns.tolist() if plot_df is not None else []

        # Apply transformations consistently
        transformed_df = pd.DataFrame()
        transform_map = {}
        for col in numeric_cols:
            col_values = plot_df[col].dropna()
            if auto_transform:
                skew_val = col_values.skew()
                if skew_val > 3:
                    suggested = "log"
                elif 1 < skew_val <= 3:
                    suggested = "sqrt"
                elif skew_val < -1:
                    suggested = "softplus"
                else:
                    suggested = "none"
            else:
                suggested = transform_mode
            transformed_df[col] = apply_transformation(col_values, suggested)
            transform_map[col] = suggested

        # Early exit if no plotting requested
        if not show_chart:
            pass
        elif not numeric_cols:
            console.print("⚠️ No numeric data available to plot. Skipping visualization.", style="yellow")
        else:
            try:
                # ---------------- ASCII ----------------
  
                if str(show_chart).lower() == "ascii":
                    visualize_data(
                        summary_df=df_stats,
                        mode="ascii",
                        chart_type=chart_type or "box",
                        output=output_path,
                        raw_df=plot_df,
                        transform=("auto" if auto_transform else transform_mode),
                        scale=getattr(args, "bar_scale", "sqrt"),
                    )

                # ---------------- Static ----------------
                elif str(show_chart).lower() == "static":
                    if chart_type == "hist" or chart_type == "box":
                        # Keep existing Matplotlib logic for hist/box
                        ensure_optional_packages(["matplotlib"])
                        import matplotlib.pyplot as plt
                        fig, ax = plt.subplots(figsize=(10, 6))
                        if chart_type == "hist":
                            for col in numeric_cols:
                                ax.hist(transformed_df[col].dropna(), bins=10, alpha=0.6, label=col)
                            ax.legend()
                            ax.set_title("Histogram of Transformed Columns")
                        else:
                            ax.boxplot([transformed_df[col].dropna() for col in numeric_cols], labels=numeric_cols)
                            ax.set_title("Boxplot of Transformed Columns")
                        plt.tight_layout()
                        if output_path:
                            plt.savefig(output_path)
                            console.print(f"[+] Chart exported as {output_path}", style="green")
                        else:
                            plt.show()
                    else:
                        # Delegate to your static helpers
                        if chart_type == "scatter":
                            visualize_scatter_plotly(plot_df, x_col, y_col, mode="static", output=output_path)
                        elif chart_type == "line":
                            visualize_line_plot(plot_df, x_col, y_col, mode="static", output=output_path)
                        elif chart_type == "bar":
                            visualize_bar_plot(plot_df, x_col, y_col, mode="static", output=output_path)
                        elif chart_type == "pie":
                            visualize_pie_plot(plot_df, x_col, y_col, mode="static", output=output_path)
                        else:
                            console.print(f"[yellow]⚠️ Unsupported static chart type: {chart_type}[/yellow]")

                # ---------------- Interactive ----------------
                elif str(show_chart).lower() == "interactive":
                    if chart_type == "hist" or chart_type == "box":
                        # Keep existing Plotly logic for hist/box
                        ensure_optional_packages(["plotly"])
                        import plotly.express as px
                        df_melted = transformed_df.melt(value_vars=numeric_cols)
                        if chart_type == "hist":
                            fig = px.histogram(df_melted, x="value", color="variable", nbins=10,
                                            title="Histogram of Transformed Columns")
                        else:
                            fig = px.box(df_melted, x="variable", y="value", color="variable",
                                        title="Boxplot of Transformed Columns")
                        if output_path:
                            fig.write_html(output_path)
                            console.print(f"[+] Interactive chart saved as {output_path}", style="green")
                        else:
                            fig.show()
                    else:
                        # Delegate to your interactive helpers
                        if chart_type == "scatter":
                            visualize_scatter_plotly(plot_df, x_col, y_col, mode="interactive", output=output_path)
                        elif chart_type == "line":
                            visualize_line_plot(plot_df, x_col, y_col, mode="interactive", output=output_path)
                        elif chart_type == "bar":
                            visualize_bar_plot(plot_df, x_col, y_col, mode="interactive", output=output_path)
                        elif chart_type == "pie":
                            visualize_pie_plot(plot_df, x_col, y_col, mode="interactive", output=output_path)
                        else:
                            console.print(f"[yellow]⚠️ Unsupported interactive chart type: {chart_type}[/yellow]")

                else:
                    console.print(f"[yellow]⚠️ Unknown show_chart mode '{show_chart}'. Skipping chart.[/yellow]")

            except Exception as e:
                console.print(f"[red]❌ Failed to render chart: {e}[/red]")


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
        "Tagging & File Operations": ["tag", "rename-file"],
        "Analysis & Extraction": ["analyze-csv", "extract-mtw"],
        "Database Maintenance": ["update-db", "migrate", "stats"],
        "Meta": ["show-help"],
    }

    # collect subcommands
    subparsers = {}
    for action in parser._subparsers._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers.update(action.choices)

    def extract_summary(subparser):
        """Return the first meaningful line of help text."""
        help_lines = subparser.format_help().splitlines()
        for line in help_lines:
            line = line.strip()
            if (
                not line
                or line.lower().startswith("usage:")
                or line.lower().startswith("options")
            ):
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

    # Step 1: parse known args to catch top-level flags
    args, remaining_args = parser.parse_known_args()

    # Handle top-level flags immediately
    if getattr(args, "show_license", False):
        show_full_license()  # prints full license and exits

    if getattr(args, "version", False):
        print_version()      # prints colored multi-line version
        sys.exit(0)

    # Step 2: parse all args (including subcommands)
    args = parser.parse_args()  # now subcommand is included in args

    # Optional: handle profile logic
    if hasattr(args, "profile") and args.profile:
        profile_data = apply_profile(args.profile)
        if profile_data:
            args = apply_profile_to_args(args, profile_data)

    # Step 3: dispatch subcommand
    if hasattr(args, "func"):
        args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user.")
        sys.exit(1)
