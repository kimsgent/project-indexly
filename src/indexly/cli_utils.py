# New: CLI handlers for tagging, exporting, profiles
from . import __version__, __author__, __license__
import os
import sys
import json
import time
import argparse
import getpass
from pathlib import Path
from importlib import resources
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
from .clean_csv import clear_cleaned_data
from .analyze_db import analyze_db
from .analysis_orchestrator import analyze_file
from .log_utils import handle_log_clean
from .read_indexly_json import read_indexly_json
from indexly.organize.cli_wrapper import handle_organize, handle_lister
from indexly.backup.cli import handle_backup
from indexly.backup.cli_restore import handle_restore
from indexly.compare.cli_compare import handle_compare


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
    parser.add_argument("--context", type=int, default=150, help="Context around match")

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip reading/writing cached search results",
    )

    parser.add_argument(
        "--no-refresh-write",
        action="store_true",
        help="Do not write refreshed cache back to disk",
    )

    parser.add_argument("--export-format", choices=["txt", "md", "pdf", "json"])
    parser.add_argument("--pdf-lib", choices=["fpdf", "reportlab"], default="fpdf")
    parser.add_argument("--output")


def build_parser():
    from .indexly import (
        handle_index,
        handle_search,
        handle_regex,
        handle_tag,
        run_stats,
        run_watch,
        handle_extract_mtw,
        handle_rename_file,
        handle_update_db,
        handle_show_help,
        handle_ignore_init,
    )

    parser = argparse.ArgumentParser(
        prog="indexly",
        description="Indexly — Local file indexing, search, and analysis tool",
    )

    # ----------------------------------------
    # 📦 Version info with license excerpt
    # ----------------------------------------
    parser.add_argument(
        "--version",
        action="store_true",  # <--- must be store_true to detect flag
        help="Show version, author, short license excerpt, and project links.",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check if a new Indexly version is available",
    )
    parser.add_argument("--no-update-check", action="store_true")

    # ----------------------------------------
    # 🪪 --show-license flag
    # ----------------------------------------
    parser.add_argument(
        "--show-license",
        action="store_true",
        help="Display the full license text and exit.",
    )

    # ----------------------------------------
    # 🧩 Subcommands
    # ----------------------------------------
    subparsers = parser.add_subparsers(dest="command")

    # Default behavior: show help if no subcommand
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
    index_parser.add_argument(
        "--ignore",
        type=str,
        help="Path to .indexlyignore file (overrides default root .indexlyignore)",
    )

    ocr_group = index_parser.add_mutually_exclusive_group()
    ocr_group.add_argument(
        "--ocr",
        action="store_true",
        help="Force OCR for all PDFs (ignore size and page limits)",
    )
    ocr_group.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR entirely for PDFs",
    )

    index_parser.set_defaults(func=handle_index)

    # -------------------------
    # Ignore init parser
    # -------------------------
    ignore_parser = subparsers.add_parser(
        "ignore",
        help="Create a default .indexlyignore template in the folder"
    )
    ignore_parser.add_argument(
        "folder",
        help="Target folder to initialize the .indexlyignore file"
    )
    ignore_parser.set_defaults(func=handle_ignore_init)

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

    # Add profile save/load support
    regex_parser.add_argument(
        "--save-profile",
        help="Save this regex search as a profile (parameters + results)",
    )
    regex_parser.add_argument(
        "--profile", help="Load a saved profile and optionally filter its results"
    )

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

    # -------------------------------
    # Analyze CSV (and all files via orchestrator)
    # -------------------------------
    csv_parser = subparsers.add_parser(
        "analyze-csv", help="Analyze a CSV file (or any supported file)"
    )
    csv_parser.add_argument("file", help="Path to the CSV file")
    csv_parser.add_argument(
        "--export-path", help="Export analysis table to file (txt, md)"
    )
    csv_parser.add_argument(
        "--format", choices=["txt", "md"], default="txt", help="Export format"
    )
    csv_parser.add_argument(
        "--compress-export",
        action="store_true",
        help="Compress JSON export output into .json.gz format",
    )

    # Visualization options
    csv_parser.add_argument(
        "--show-chart",
        choices=["ascii", "static", "interactive"],
        help="Visualize CSV data in terminal, static image, or interactive HTML",
    )
    csv_parser.add_argument(
        "--chart-type",
        choices=["bar", "line", "box", "hist", "scatter", "pie"],
        default="None",
        help="Chart type for visualizing numeric data",
    )
    csv_parser.add_argument(
        "--export-plot", help="Export chart to file (png, svg, html)"
    )
    csv_parser.add_argument("--x-col", help="X-axis column for scatter plot")
    csv_parser.add_argument("--y-col", help="Y-axis column for scatter plot")
    csv_parser.add_argument(
        "--transform",
        choices=["none", "log", "sqrt", "softplus", "exp-log", "auto"],
        default="none",
        help="Apply data transformation before visualization",
    )
    csv_parser.add_argument(
        "--bar-scale",
        choices=["sqrt", "log"],
        default="sqrt",
        help="Scaling method for ASCII histogram bars",
    )
    csv_parser.add_argument(
        "--timeseries", action="store_true", help="Plot timeseries if CSV"
    )
    csv_parser.add_argument(
        "--x", type=str, help="Datetime column for timeseries X-axis"
    )
    csv_parser.add_argument(
        "--y", type=str, help="Comma-separated numeric columns for Y-axis"
    )
    csv_parser.add_argument("--freq", type=str, help="Resample frequency (D,W,M,Q,Y)")
    csv_parser.add_argument(
        "--agg", type=str, default="mean", help="Aggregation for resampling"
    )
    csv_parser.add_argument("--rolling", type=int, help="Rolling mean window size")
    csv_parser.add_argument(
        "--mode",
        type=str,
        default="interactive",
        choices=["interactive", "static"],
        help="Plotting backend",
    )
    csv_parser.add_argument("--output", type=str, help="Output filename for chart")
    csv_parser.add_argument("--title", type=str, help="Plot title override")

    # Cleaning options
    csv_parser.add_argument(
        "--auto-clean", action="store_true", help="Run robust cleaning pipeline"
    )
    csv_parser.add_argument(
        "--fill-method",
        choices=["mean", "median"],
        default="mean",
        help="Method to fill missing numeric values",
    )
    csv_parser.add_argument(
        "--datetime-formats",
        nargs="+",
        metavar="FMT",
        help="Optional list of datetime formats to apply (e.g. '%%Y-%%m-%%d' '%%d/%%m/%%Y %%H:%%M')",
    )
    csv_parser.add_argument(
        "--derive-dates",
        choices=["all", "minimal", "none"],
        default="all",
        help="How many derived datetime features to generate",
    )
    csv_parser.add_argument(
        "--date-threshold",
        type=float,
        default=0.3,
        help="Minimum valid ratio for date detection",
    )
    csv_parser.add_argument(
        "--use-cleaned",
        action="store_true",
        help="Use previously saved cleaned dataset",
    )
    csv_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Disable saving cleaned or analyzed results to the database",
    )
    csv_parser.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize numeric columns after cleaning",
    )
    csv_parser.add_argument(
        "--remove-outliers", action="store_true", help="Remove outliers after cleaning"
    )
    csv_parser.add_argument(
        "--export-format",
        choices=["txt", "md", "json"],
        default="csv",
        help="Format for cleaned dataset export",
    )
    csv_parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Show extended summary of columns and derived fields",
    )

    csv_parser.set_defaults(func=analyze_file, subcommand="analyze-csv")

    # -------------------------------
    # Clear cleaned data
    # -------------------------------
    clear_parser = subparsers.add_parser(
        "clear-data", help="Remove saved cleaned dataset"
    )
    clear_parser.add_argument(
        "file", nargs="?", help="CSV file whose cleaned data should be removed"
    )
    clear_parser.add_argument(
        "--all", action="store_true", help="Remove all cleaned datasets"
    )
    clear_parser.set_defaults(
        func=lambda args: clear_cleaned_data(
            file_path=args.file, remove_all=getattr(args, "all", False)
        )
    )

    # -------------------------------
    # Analyze JSON
    # -------------------------------
    sub_analyze_json = subparsers.add_parser(
        "analyze-json", help="Analyze a JSON file structure and statistics"
    )
    sub_analyze_json.add_argument("file", help="Path to JSON file")
    sub_analyze_json.add_argument("--export-path", help="Export analysis output path")
    sub_analyze_json.add_argument(
        "--format", default="txt", choices=["txt", "md", "json"], help="Export format"
    )
    sub_analyze_json.add_argument(
        "--show-summary", action="store_true", help="Show structural summary"
    )
    sub_analyze_json.add_argument(
        "--show-chart", action="store_true", help="Display numeric histograms"
    )
    sub_analyze_json.add_argument(
        "--chunk-size",
        type=int,
        default=10000,
        help="Rows per chunk for memory-efficient JSON export",
    )
    sub_analyze_json.add_argument(
        "--use-saved",
        action="store_true",
        help="Use previously saved JSON analysis data",
    )
    sub_analyze_json.add_argument(
        "--no-persist",
        action="store_true",
        help="Disable saving cleaned or analyzed results to the database",
    )
    sub_analyze_json.set_defaults(func=analyze_file, subcommand="analyze-json")

    # -------------------------------
    # Analyze any supported file
    # -------------------------------

    analyze_file_parser = subparsers.add_parser(
        "analyze-file",
        help="Analyze any supported file (CSV, JSON, SQLite, XML, YAML, Parquet, Excel etc.)",
    )

    analyze_file_parser.add_argument("file", help="Path to the file to analyze")

    # -------------------------------
    # Common options (all file types)
    # -------------------------------
    common = analyze_file_parser.add_argument_group("Common options")

    common.add_argument("--export-path", help="Export analysis table to file")
    common.add_argument(
        "--format",
        choices=["txt", "md", "db", "csv", "json", "parquet", "excel"],
        default="txt",
        help="Output format for exported data",
    )
    common.add_argument(
        "--no-persist", action="store_true", help="Disable database writes"
    )
    common.add_argument(
        "--show-summary",
        action="store_true",
        help="Show extended summary of columns and derived fields",
    )
    common.add_argument(
        "--wide-view",
        action="store_true",
        help="Display full column width for wide screens",
    )
    common.add_argument(
        "--export-summary",
        action="store_true",
        help="Export dataset summary preview as Markdown (.md)",
    )
    common.add_argument(
        "--use-saved",
        action="store_true",
        help="Use previously saved analysis data",
    )

    # -------------------------------
    # CSV-specific options
    # -------------------------------
    csv_opts = analyze_file_parser.add_argument_group("CSV-specific options")

    csv_opts.add_argument(
        "--auto-clean", action="store_true", help="Run robust CSV cleaning pipeline"
    )
    csv_opts.add_argument(
        "--fill-method",
        choices=["mean", "median"],
        default="mean",
        help="Fill missing numeric values",
    )
    csv_opts.add_argument(
        "--datetime-formats",
        nargs="+",
        metavar="FMT",
        help="Explicit datetime formats for CSV parsing",
    )
    csv_opts.add_argument(
        "--derive-dates",
        choices=["all", "minimal", "none"],
        default="all",
        help="Generate derived datetime features",
    )
    csv_opts.add_argument(
        "--date-threshold",
        type=float,
        default=0.3,
        help="Minimum valid ratio for date detection",
    )
    csv_opts.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize numeric columns",
    )
    csv_opts.add_argument(
        "--remove-outliers",
        action="store_true",
        help="Remove numeric outliers",
    )
    csv_opts.add_argument(
        "--use-cleaned",
        action="store_true",
        help="Use previously cleaned CSV dataset",
    )

    # -------------------------------
    # CSV visualization options
    # -------------------------------
    csv_viz = analyze_file_parser.add_argument_group("CSV visualization options")

    csv_viz.add_argument(
        "--show-chart",
        choices=["ascii", "static", "interactive"],
        help="Visualize CSV data",
    )
    csv_viz.add_argument(
        "--chart-type",
        choices=["bar", "line", "box", "hist", "scatter", "pie"],
        default="None",
        help="Chart type",
    )
    csv_viz.add_argument("--x-col", help="X-axis column")
    csv_viz.add_argument("--y-col", help="Y-axis column")
    csv_viz.add_argument("--export-plot", help="Export chart to file")
    csv_viz.add_argument(
        "--timeseries",
        action="store_true",
        help="Plot CSV timeseries data",
    )
    csv_viz.add_argument("--x", help="Datetime column for timeseries X-axis")
    csv_viz.add_argument("--y", help="Comma-separated numeric Y columns")
    csv_viz.add_argument("--freq", help="Resample frequency (D,W,M,Q,Y)")
    csv_viz.add_argument("--agg", default="mean", help="Aggregation method")
    csv_viz.add_argument("--rolling", type=int, help="Rolling window size")

    # -------------------------------
    # JSON-specific options
    # -------------------------------
    json_opts = analyze_file_parser.add_argument_group("JSON-specific options")

    json_opts.add_argument(
        "--summarize-search",
        action="store_true",
        help="Summarize normalized search-cache JSON files",
    )
    json_opts.add_argument(
        "--sortdate-by",
        choices=["date", "year", "month", "week"],
        help="Sort normalized JSON search results",
    )

    # -------------------------------
    # XML options
    # -------------------------------
    xml_opts = analyze_file_parser.add_argument_group("XML-specific options")

    xml_opts.add_argument(
        "--invoice",
        action="store_true",
        help="Treat XML file as e-invoice",
    )
    xml_opts.add_argument(
        "--invoice-export",
        help="Export e-invoice summary to Markdown",
    )
    xml_opts.add_argument(
        "--treeview",
        action="store_true",
        help="Display XML tree view",
    )

    # -------------------------------
    # Excel options
    # -------------------------------
    excel_opts = analyze_file_parser.add_argument_group("Excel-specific options")

    excel_opts.add_argument(
        "--sheet-name",
        nargs="+",
        help="Excel sheet names to analyze (default: all)",
    )

    analyze_file_parser.set_defaults(func=analyze_file)

    # -----------------------------------------
    # analyze-db subcommand
    # -----------------------------------------

    analyze_db_parser = subparsers.add_parser(
        "analyze-db", help="Inspect a SQLite DB and generate analysis summary."
    )

    analyze_db_parser.add_argument("db_path", help="Path to the SQLite database file.")

    analyze_db_parser.add_argument(
        "--table",
        help="Only analyze a specific table.",
    )

    analyze_db_parser.add_argument(
        "--all-tables",
        action="store_true",
        help="Analyze all tables instead of auto-selecting one.",
    )

    # -------------------------
    # Sampling controls
    # -------------------------
    analyze_db_parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Maximum number of rows to sample per table. "
        "If omitted, adaptive sampling is applied.",
    )

    analyze_db_parser.add_argument(
        "--all-data",
        action="store_true",
        help="Disable sampling and use full table data.",
    )

    analyze_db_parser.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: lighter profiling for huge tables.",
    )

    # -------------------------
    # Output controls
    # -------------------------
    analyze_db_parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Print analysis overview to terminal.",
    )

    analyze_db_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write summary file to disk.",
    )
    analyze_db_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Profile multiple tables in parallel using multiple CPU cores",
    )
    analyze_db_parser.add_argument(
        "--max-workers",
        type=int,
        default=os.cpu_count(),
        help="Maximum number of parallel workers (default = CPU count)",
    )
    analyze_db_parser.add_argument(
        "--fast-mode",
        action="store_true",
        help="Enable fast profiling mode (lighter metrics, faster)",
    )
    analyze_db_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Per-table profiling timeout in seconds",
    )
    analyze_db_parser.add_argument(
        "--persist-level",
        choices=["minimal", "full", "none"],
        default="full",
    )

    analyze_db_parser.add_argument(
        "--export",
        choices=["json", "md", "html"],
        help="Export summary in the chosen format.",
    )

    analyze_db_parser.add_argument(
        "--diagram",
        choices=["mermaid"],
        help="Include diagrams in MD/HTML export.",
    )

    analyze_db_parser.set_defaults(func=analyze_db)

    # ------------------------
    # Organizer CLI
    # ------------------------
    organize_parser = subparsers.add_parser(
        "organize", help="Organize files in a folder by date or name"
    )
    organize_parser.add_argument("folder", help="Folder to organize")
    organize_parser.add_argument(
        "--sort-by",
        choices=["date", "name", "extension"],
        default="date",
        help="Sort files by date, name or extension",
    )
    organize_parser.add_argument(
        "--backup",
        help="Optional backup folder to store copies of organized files",
    )
    organize_parser.add_argument(
        "--log-dir",
        help="Optional folder to store organizer logs (default: <folder>/log)",
    )
    organize_parser.add_argument(
        "--executed-by",
        default=getpass.getuser(),
        help="Name of the user performing the organization (default: system user)",
    )
    organize_parser.add_argument(
        "--lister",
        action="store_true",
        help="List files from the organizer log AFTER organizing (uses generated JSON log)",
    )

    organize_parser.add_argument(
        "--lister-ext", help="Filter listed files by extension"
    )
    organize_parser.add_argument(
        "--lister-category", help="Filter listed files by category"
    )
    organize_parser.add_argument(
        "--lister-date", help="Filter listed files by used date"
    )
    organize_parser.add_argument(
        "--lister-duplicates",
        action="store_true",
        help="Show only duplicate files",
    )

    organize_parser.set_defaults(
        func=lambda args: handle_organize(
            folder=args.folder,
            sort_by=args.sort_by,
            backup=args.backup,
            log_dir=args.log_dir,
            executed_by=args.executed_by,
            lister=args.lister,
            lister_ext=args.lister_ext,
            lister_category=args.lister_category,
            lister_date=args.lister_date,
            lister_duplicates=args.lister_duplicates,
        )
    )

    # Lister
    lister_parser = subparsers.add_parser(
        "lister",
        help="List files from organizer log",
    )
    lister_parser.add_argument(
        "source",
        help="Organizer JSON log file or directory containing logs",
    )
    lister_parser.add_argument("--ext", help="Filter by extension (e.g. .json)")
    lister_parser.add_argument("--category", help="Filter by category")
    lister_parser.add_argument("--date", help="Filter by YYYY-MM")
    lister_parser.add_argument(
        "--duplicates",
        action="store_true",
        help="Show only duplicate files",
    )
    lister_parser.set_defaults(
        func=lambda args: handle_lister(
            args.source,
            ext=args.ext,
            category=args.category,
            date=args.date,
            duplicates=args.duplicates,
        )
    )

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

    # ----------------------- read-json -----------------------
    read_json_parser = subparsers.add_parser(
        "read-json",
        help="Read and display indexly JSON file",
        description="Read and view Indexly JSON files.",
    )

    read_json_parser.add_argument("file", help="Path to Indexly JSON file")

    read_json_parser.add_argument(
        "--treeview", action="store_true", help="Display full Rich tree view"
    )

    read_json_parser.add_argument(
        "--preview",
        type=int,
        default=3,
        help="Number of top-level keys/items to preview in compact view",
    )

    read_json_parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Display database-aware summary of JSON content",
    )

    # IMPORTANT: always set func → otherwise argparse prints top-level help
    read_json_parser.set_defaults(
        func=lambda args: read_indexly_json(
            file_path=args.file,
            treeview=args.treeview,
            preview=args.preview,
            show_summary=args.show_summary,
        )
    )

    # Backup
    backup_parser = subparsers.add_parser(
        "backup",
        help="Create a full or incremental backup",
    )

    backup_parser.add_argument(
        "folder",
        nargs="?",
        help="Folder to back up (required for manual backup or --init-auto)",
    )

    backup_parser.add_argument(
        "--incremental",
        action="store_true",
        help="Create an incremental backup (default: full backup)",
    )
    backup_parser.add_argument(
        "--manual",
        action="store_true",
        help="Force interactive/manual mode even if auto-backup is enabled",
    )

    backup_parser.add_argument(
        "--encrypt",
        metavar="PASSWORD",
        help="Encrypt backup with password",
    )

    # 🔹 Automatic backup controls
    backup_parser.add_argument(
        "--init-auto",
        action="store_true",
        help="Initialize automatic backup structure (opt-in)",
    )

    backup_parser.add_argument(
        "--disable-auto",
        action="store_true",
        help="Disable automatic backups and delete all backup data",
    )

    backup_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive actions (required for --disable-auto)",
    )

    backup_parser.set_defaults(func=lambda args: handle_backup(args))

    # Restore Backup
    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore a backup",
    )
    restore_parser.add_argument("backup", help="Backup name")
    restore_parser.add_argument("--target", help="Restore destination")
    restore_parser.add_argument("--decrypt", help="Decryption password")
    restore_parser.set_defaults(func=handle_restore)

    # Compare
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare files or folders",
    )

    compare_parser.add_argument(
        "path_a",
        help="First file or folder (or target for auto-compare)",
    )

    compare_parser.add_argument(
        "path_b",
        nargs="?",
        help="Second file or folder (optional for auto-compare)",
    )

    compare_parser.add_argument(
        "--threshold",
        type=float,
        help="Similarity tolerance (0.0 exact, 1.0 very loose)",
    )

    compare_parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    compare_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress normal output (exit code only)",
    )

    compare_parser.add_argument(
        "--extensions",
        type=str,
        help="Comma-separated list of file extensions to compare (e.g., .py,.md,.json)",
    )
    compare_parser.add_argument(
        "--context",
        type=int,
        default=3,
        help="Number of context lines to show around changes (default: 3)",
    )

    compare_parser.add_argument(
        "--ignore",
        type=str,
        help="Comma-separated list of file/folder names to ignore (e.g., .git,__pycache__)",
    )

    compare_parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Show summary only (folders)",
    )

    compare_parser.set_defaults(func=lambda args: handle_compare(args))

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

    # -------------------------------------------------------------------
    # update-db command
    # -------------------------------------------------------------------
    update_db = subparsers.add_parser(
        "update-db",
        help="Quickly check or apply database schema updates (without backups).",
    )

    update_db.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to database file (default: uses DB_FILE from config)",
    )

    update_db.add_argument(
        "--apply",
        action="store_true",
        help="Apply schema fixes instead of just checking.",
    )

    update_db.set_defaults(func=lambda args: handle_update_db(args))

    # ------------------------------------------------------------
    # LOG-CLEAN SUBCOMMAND
    # ------------------------------------------------------------
    sub_log_clean = subparsers.add_parser(
        "log-clean",
        help="Clean one or multiple index log files (auto-detects *_index.log)",
    )

    sub_log_clean.add_argument(
        "file",
        help="Path to a single index log file OR a directory containing multiple logs.",
    )

    sub_log_clean.add_argument(
        "--export",
        default="json",
        choices=["json", "csv", "ndjson"],
        help="Export format for cleaned logs.",
    )

    sub_log_clean.add_argument(
        "--out",
        help=(
            "Output file or directory. "
            "If processing multiple logs without --combine-log, this should be a directory. "
            "Default: auto-generated filenames in the same folder."
        ),
    )

    sub_log_clean.add_argument(
        "--combine-log",
        action="store_true",
        help="Merge all found logs into a single combined export.",
    )

    sub_log_clean.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable deduplication when combining logs.",
    )

    sub_log_clean.set_defaults(func=handle_log_clean)

    # -------------------------------------------------------------------
    # show-help command
    # -------------------------------------------------------------------

    show_help_parser = subparsers.add_parser(
        "show-help", help="Display help for all Indexly commands"
    )
    show_help_parser.add_argument(
        "--markdown", action="store_true", help="Output as Markdown for docs"
    )
    show_help_parser.add_argument(
        "--details", action="store_true", help="Show detailed help for each command"
    )
    show_help_parser.set_defaults(func=handle_show_help)

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
