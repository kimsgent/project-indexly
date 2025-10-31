import pandas as pd
from pathlib import Path
from rich.console import Console
from .analysis_result import AnalysisResult
from .csv_pipeline import run_csv_pipeline
from .json_pipeline import run_json_pipeline
from .db_pipeline import run_db_pipeline
from .csv_analyzer import export_results, detect_delimiter
from .analyze_utils import validate_file_content
from .analyze_utils import save_analysis_result, handle_show_summary

console = Console()


# -------------------------------
# File type detection
# -------------------------------
def detect_file_type(path: Path) -> str:
    """
    Determine the file type based on extension or content inspection.
    """
    ext = path.suffix.lower()
    if ext in [".csv", ".tsv"]:
        return "csv"
    elif ext == ".json":
        return "json"
    elif ext in [".db", ".sqlite"]:
        return "sqlite"
    elif ext in [".xlsx", ".xls"]:
        return "excel"
    elif ext == ".parquet":
        return "parquet"
    else:
        return "unknown"


# -------------------------------
# Unified orchestrator
# -------------------------------


def analyze_file(args) -> AnalysisResult:
    """
    Unified orchestrator for analyzing CSV, JSON, or DB files.
    Handles cleaning, analysis, visualization, and export.
    """
    file_path = Path(args.file).resolve()
    ext = file_path.suffix.lower()
    file_type = (
        "csv" if ext in [".csv", ".tsv"]
        else "json" if ext == ".json"
        else "sqlite" if ext in [".db", ".sqlite"]
        else "excel" if ext in [".xlsx", ".xls"]
        else "parquet" if ext == ".parquet"
        else "unknown"
    )

    # --- CLI subcommand-based file type override ---
   
    file_type = detect_file_type(file_path)
    if getattr(args, "func", None):
        func_name = args.func.__name__
        if "csv" in func_name:
            file_type = "csv"
        elif "json" in func_name:
            file_type = "json"

    # --- ✅ Universal content validation ---
    if not validate_file_content(file_path, file_type):
        console.print("[red]❌ File validation failed — analysis aborted.[/red]")
        return None

    # --- Dispatch based on file type ---
    if file_type == "csv":
        df, df_stats, table_output = run_csv_pipeline(file_path, args)
    elif file_type == "json":
        from .json_pipeline import run_json_pipeline
        df, df_stats, table_output = run_json_pipeline(file_path, args)
    elif file_type in {"sqlite", "db"}:
        from .db_pipeline import run_db_pipeline
        df, df_stats, table_output = run_db_pipeline(file_path, args)
    else:
        console.print(f"[red]❌ Unsupported file type:[/red] {file_type}")
        return None

    # --- Optional persistence ---

    cleaned_flag = False if df_stats is None else not df_stats.empty
    result = AnalysisResult(
        file_path=str(file_path),
        file_type=file_type,
        df=df,
        summary=df_stats,
        metadata={"table_output": table_output} if table_output else {},
        cleaned=cleaned_flag,
    )

    # Only persist if it hasn't been saved yet
    persisted_by_clean_csv = getattr(df, "_persisted", False)  # we can set this inside clean_csv_data()

    if not getattr(args, "no_persist", False) and not persisted_by_clean_csv:
        save_analysis_result(
            file_path=str(file_path),
            file_type=file_type,
            summary=df_stats.to_dict() if hasattr(df_stats, "to_dict") else {},
            sample_data=df.head(3).to_dict(orient="records") if df is not None else {},
            metadata={"table_output": table_output} if table_output else {},
            row_count=len(df) if df is not None else 0,
            col_count=len(df.columns) if df is not None else 0,
        )
        result.persisted = True
    else:
        result.persisted = persisted_by_clean_csv


    # --- Timeseries visualization for CSV ---
    if file_type == "csv" and (getattr(args, "timeseries", False) or getattr(args, "plot_timeseries", False)):
        from .visualize_timeseries import visualize_timeseries_plot
        y_cols = [c.strip() for c in getattr(args, "y", "").split(",") if c.strip()] or None
        try:
            visualize_timeseries_plot(
                df=df,
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
            console.print(f"[red]❌ Timeseries visualization failed: {e}[/red]")

    # --- Export table output ---
    export_path = getattr(args, "export_path", None)
    export_fmt = getattr(args, "format", "txt")
    if export_path:
        export_results(
            results=table_output,
            export_path=export_path,
            export_format=export_fmt,
            df=df,
            source_file=file_path,
        )
        console.print(f"✅ Exported to: {export_path}")

    # --- Optional summary display ---
    show_summary = getattr(args, "show_summary", False)
    auto_clean = getattr(args, "auto_clean", False)

    if show_summary:
        from .analyze_utils import handle_show_summary

        # Case 1: user requested summary after saved run
        if not auto_clean:
            handle_show_summary(args.file)
            return result

        # Case 2: live run with in-memory df_stats (during cleaning)
        console.print("\n📊 [bold cyan]Live Summary Preview:[/bold cyan]\n")
        if isinstance(df_stats, pd.DataFrame) and not df_stats.empty:
            from rich.table import Table
            table = Table(title="Dataset Summary", show_header=True, header_style="bold magenta")
            for col in df_stats.columns:
                table.add_column(str(col))
            for _, row in df_stats.iterrows():
                table.add_row(*[str(x) for x in row])
            console.print(table)
        elif isinstance(table_output, str):
            console.print(table_output)
        else:
            console.print("[yellow]No summary data available.[/yellow]")


    return result


# -------------------------------
# Legacy helper
# -------------------------------
def run_analyze_csv(args):
    """
    Backward-compatible wrapper for the old CLI.
    Simply delegates to analyze_file for CSVs.
    """
    return analyze_file(args)
