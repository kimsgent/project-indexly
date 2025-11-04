import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from rich.console import Console
from .analysis_result import AnalysisResult
from .csv_pipeline import run_csv_pipeline
from .json_pipeline import run_json_pipeline
from .db_pipeline import run_db_pipeline
from .csv_analyzer import export_results, _json_safe
from .analyze_utils import (
    save_analysis_result,
    load_cleaned_data,
    validate_file_content,
)
from .visualize_timeseries import _handle_timeseries_visualization

console = Console()


# -------------------------------
# File type detection (enhanced)
# -------------------------------
def detect_file_type(path: Path) -> str:
    """
    Determine the file type based on extension or content inspection.
    Supports compressed (.gz) variants like .csv.gz and .json.gz.
    """
    name = path.name.lower()
    ext = path.suffix.lower()

    # Handle gzip-compressed files (.csv.gz, .json.gz, etc.)
    if name.endswith(".csv.gz") or name.endswith(".tsv.gz"):
        return "csv"
    elif name.endswith(".json.gz"):
        return "json"
    elif name.endswith(".sqlite.gz") or name.endswith(".db.gz"):
        return "sqlite"
    elif name.endswith(".xlsx.gz") or name.endswith(".xls.gz"):
        return "excel"
    elif name.endswith(".parquet.gz"):
        return "parquet"

    # Regular uncompressed files
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


console = Console()


def analyze_file(args) -> AnalysisResult:
    """
    Unified orchestrator for analyzing CSV, JSON, or DB files.
    Delegates to format-specific pipelines and avoids duplicate visualization calls.
    """
    from rich.table import Table

    file_path = Path(args.file).resolve()
    ext = file_path.suffix.lower()
    file_type = detect_file_type(file_path)

    # --- CLI override (for subcommands like analyze-csv / analyze-json) ---
    if getattr(args, "func", None):
        func_name = args.func.__name__
        if "csv" in func_name:
            file_type = "csv"
        elif "json" in func_name:
            file_type = "json"

    # --- Step 0: Load from saved dataset if requested ---
    use_saved = getattr(args, "use_saved", False) or getattr(args, "use_cleaned", False)
    if use_saved:
        try:
            exists, record = load_cleaned_data(file_path)
            if exists:
                console.print(
                    f"[cyan]♻️ Using previously saved data for {file_path.name}[/cyan]"
                )

                data_json = record.get("data_json", {})
                metadata_json = record.get("metadata_json", {})
                df = pd.DataFrame(data_json.get("sample_data", []))
                df_stats = pd.DataFrame(data_json.get("summary_statistics", {})).T

                # Display summary and meta info
                console.print(
                    f"\n📦 [bold cyan]Saved Dataset Overview for {file_path.name}[/bold cyan]"
                )
                console.print(
                    f"• File Type: {file_type.upper()} | Cleaned: {record.get('cleaned', True)} | Persisted: ✅"
                )

                if df_stats is not None and not df_stats.empty:
                    console.print("\n📊 [bold cyan]Summary Statistics[/bold cyan]")
                    table = Table(show_header=True, header_style="bold magenta")
                    table.add_column("Statistic")
                    for col in df_stats.columns:
                        table.add_column(str(col))
                    for stat_name, row in df_stats.iterrows():
                        table.add_row(stat_name, *[str(v) for v in row])
                    console.print(table)

                if "table_output" in metadata_json:
                    console.print("\n📋 [bold cyan]Formatted Table Output[/bold cyan]")
                    console.print(metadata_json["table_output"])

                if not df.empty:
                    console.print("\n🧩 [bold cyan]Sample Data Preview[/bold cyan]")
                    console.print(df.head(5))

                return AnalysisResult(
                    file_path=str(file_path),
                    file_type=file_type,
                    df=df,
                    summary=df_stats,
                    metadata=metadata_json,
                    cleaned=True,
                    persisted=True,
                )
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to load saved data: {e}[/yellow]")

    # --- Step 1: Validate file before analysis ---
    if not validate_file_content(file_path, file_type):
        console.print("[red]❌ File validation failed — analysis aborted.[/red]")
        return None

   # --- Step 2: Route to appropriate pipeline ---
    df = df_stats = table_output = None

    # --- Step 2a: Propagate global no-persist flag for pipelines ---
    no_persist_flag = getattr(args, "no_persist", False)

    # --- Step 2b: Run appropriate pipeline based on file type ---
    if file_type == "csv":
        df, df_stats, table_output = run_csv_pipeline(file_path, args)
    elif file_type == "json":
        df, df_stats, table_output = run_json_pipeline(file_path, args)
    elif file_type in {"sqlite", "db"}:
        df, df_stats, table_output = run_db_pipeline(file_path, args)
    else:
        console.print(f"[red]❌ Unsupported file type:[/red] {file_type}")
        return None

    # Ensure the pipeline knows about orchestrator-controlled persistence
    if df is not None:
        df._no_persist = no_persist_flag
        df._from_orchestrator = True

    # --- Step 3: Handle deferred persistence from cleaning stage ---
    # Some pipelines (like CSV auto-clean) attach a _persist_ready payload.
    if hasattr(df, "_persist_ready") and not getattr(df, "_persisted", False):
        if no_persist_flag:
            console.print(
                f"[yellow]⚠️ Skipped deferred persistence (--no-persist active) for {file_path.name}[/yellow]"
            )
        else:
            try:
                save_analysis_result(
                    file_path=file_path,
                    file_type=file_type,  # "csv" or "json"
                    **df._persist_ready,
                )
                df._persisted = True
                console.print(f"[green]💾 Deferred persistence saved for {file_path.name}[/green]")
            except Exception as e:
                console.print(f"[red]❌ Deferred persistence failed for {file_path.name}: {e}[/red]")

    # --- Step 4: Persist results if needed (main orchestrator save) ---
    cleaned_flag = df_stats is not None and not df_stats.empty
    result = AnalysisResult(
        file_path=str(file_path),
        file_type=file_type,
        df=df,
        summary=df_stats,
        metadata={"table_output": table_output} if table_output else {},
        cleaned=cleaned_flag,
    )

    # Only save if not already persisted and --no-persist not set
    if not no_persist_flag and not getattr(df, "_persisted", False):
        try:
            save_analysis_result(
                file_path=str(file_path),
                file_type=file_type,
                summary=df_stats.to_dict() if hasattr(df_stats, "to_dict") else {},
                sample_data=(df.head(3).to_dict(orient="records") if df is not None else {}),
                metadata={"table_output": table_output} if table_output else {},
                row_count=len(df) if df is not None else 0,
                col_count=len(df.columns) if df is not None else 0,
            )
            df._persisted = True
            result.persisted = True
            console.print(f"[green]💾 Analysis result persisted for {file_path.name}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to persist analysis result: {e}[/yellow]")
            result.persisted = False

    elif getattr(df, "_persisted", False):
        console.print(f"[dim]💾 Already persisted, skipping duplicate save.[/dim]")

    # --- Step 5: Optional export (centralized) ---

    export_path = getattr(args, "export_path", None)
    export_fmt = getattr(args, "format", "txt")
    compress_export = getattr(args, "compress_export", False)

    if export_path and (df is not None):
        if file_type == "json":
            payload = {
                "metadata": {
                    "analyzed_at": datetime.utcnow().isoformat() + "Z",
                    "source_file": str(file_path),
                    "export_format": "json",
                    "rows": len(df),
                    "columns": len(df.columns),
                },
                "summary_statistics": (
                    df_stats.to_dict(orient="index") if df_stats is not None else {}
                ),
                "sample_data": df.head(10).to_dict(orient="records"),
                "table_output": table_output,
            }

            # handle compressed JSON export
            if compress_export:
                import gzip, json
                compressed_path = (
                    export_path if export_path.endswith(".gz") else export_path + ".gz"
                )
                with gzip.open(compressed_path, "wt", encoding="utf-8") as fh:
                    json.dump(
                        _json_safe(payload, preserve_numeric=True),
                        fh,
                        indent=2,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                console.print(f"[green]✅ Exported compressed JSON to: {compressed_path}[/green]")
            else:
                with open(export_path, "w", encoding="utf-8") as fh:
                    json.dump(
                        _json_safe(payload, preserve_numeric=True),
                        fh,
                        indent=2,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                console.print(f"[green]✅ Exported JSON successfully to: {export_path}[/green]")

        else:
            # pass compression flag through to export_results()
            export_results(
                results=table_output,
                export_path=export_path,
                export_format=export_fmt,
                df=df,
                source_file=file_path,
                compress=compress_export,
            )
            console.print(f"✅ Exported to: {export_path}")

    # --- Step 6: Show summary preview ---
    if getattr(args, "show_summary", False):
        console.print("\n📊 [bold cyan]Dataset Summary Preview[/bold cyan]")
        if isinstance(df_stats, pd.DataFrame) and not df_stats.empty:
            table = Table(
                title="Dataset Summary", show_header=True, header_style="bold magenta"
            )
            for col in df_stats.columns:
                table.add_column(str(col))
            for _, row in df_stats.iterrows():
                table.add_row(*[str(x) for x in row])
            console.print(table)
        elif isinstance(table_output, str):
            console.print(table_output)
        else:
            console.print("[yellow]No summary data available.[/yellow]")

    # --- Step 7: Optional visualization ---
    if getattr(args, "timeseries", False) and df is not None:
        try:
            _handle_timeseries_visualization(df, args)
        except Exception as e:
            console.print(f"[yellow]⚠️ Visualization skipped due to error: {e}[/yellow]")

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
