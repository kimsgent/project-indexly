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
from indexly.universal_loader import detect_and_load, detect_file_type

console = Console()



console = Console()


def analyze_file(args) -> AnalysisResult:
    """
    Unified orchestrator for analyzing CSV, JSON, or DB files.
    Delegates to format-specific pipelines and avoids duplicate visualization calls.
    Fully backward-compatible with legacy analyze-csv / analyze-json calls.
    """
    from rich.table import Table
    from pathlib import Path
    import pandas as pd
    from datetime import datetime

    file_path = Path(args.file).resolve()
    ext = file_path.suffix.lower()
    file_type = detect_file_type(file_path)

    # -----------------------------
    # --- LEGACY SHORT-CIRCUIT ---
    # -----------------------------
    df = df_stats = table_output = None
    legacy_mode = False

    if getattr(args, "command", "") == "analyze-csv":
        df, df_stats, table_output = run_csv_pipeline(file_path, args)
        file_type = "csv"
        legacy_mode = True

    elif getattr(args, "command", "") == "analyze-json":
        df, df_stats, table_output = run_json_pipeline(file_path, args)
        file_type = "json"
        legacy_mode = True

    # -----------------------------
    # --- LOAD SAVED DATA IF REQUESTED ---
    # -----------------------------
    use_saved = getattr(args, "use_saved", False) or getattr(args, "use_cleaned", False)
    if use_saved:
        try:
            exists, record = load_cleaned_data(file_path)
            if exists:
                console.print(f"[cyan]♻️ Using previously saved data for {file_path.name}[/cyan]")
                data_json = record.get("data_json", {})
                metadata_json = record.get("metadata_json", {})
                df = pd.DataFrame(data_json.get("sample_data", []))
                df_stats = pd.DataFrame(data_json.get("summary_statistics", {})).T
                table_output = metadata_json.get("table_output", None)
                file_type = record.get("file_type", file_type)

                # Display saved summary
                console.print(f"\n📦 [bold cyan]Saved Dataset Overview for {file_path.name}[/bold cyan]")
                console.print(f"• File Type: {file_type.upper()} | Cleaned: {record.get('cleaned', True)} | Persisted: ✅")
                if df_stats is not None and not df_stats.empty:
                    console.print("\n📊 [bold cyan]Summary Statistics[/bold cyan]")
                    table = Table(show_header=True, header_style="bold magenta")
                    table.add_column("Statistic")
                    for col in df_stats.columns:
                        table.add_column(str(col))
                    for stat_name, row in df_stats.iterrows():
                        table.add_row(stat_name, *[str(v) for v in row])
                    console.print(table)
                if table_output:
                    console.print("\n📋 [bold cyan]Formatted Table Output[/bold cyan]")
                    console.print(table_output)
                if df is not None and not df.empty:
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

    # -----------------------------
    # --- VALIDATE FILE BEFORE ANALYSIS ---
    # -----------------------------
    if not validate_file_content(file_path, file_type):
        console.print("[red]❌ File validation failed — analysis aborted.[/red]")
        return None

    # -----------------------------
    # --- UNIVERSAL LOADER (SKIP FOR LEGACY) ---
    # -----------------------------
    no_persist_flag = getattr(args, "no_persist", False)
    if not legacy_mode:
        use_universal = getattr(args, "command", "") == "analyze-file" or getattr(args, "global_mode", False)
        if use_universal:
            file_path_str = str(file_path)
            result = detect_and_load(file_path_str, args)
            if result is None:
                console.print(f"[red]❌ Universal loader failed for {file_path.name}[/red]")
                return None

            df = result.get("df")
            metadata = result.get("metadata", {})
            file_type = result.get("file_type", "unknown")

            if df is None and file_type not in {"sqlite", "db"}:
                console.print(f"[red]❌ Universal loader returned no DataFrame for {file_path.name}[/red]")
                return None

            # Route to specialized pipelines
            if file_type == "csv":
                df, df_stats, table_output = run_csv_pipeline(file_path, args)
            elif file_type == "json":
                df, df_stats, table_output = run_json_pipeline(file_path, args)
            elif file_type in {"sqlite", "db"}:
                df, df_stats, table_output = run_db_pipeline(file_path, args)
            elif file_type in {"yaml", "yml"}:
                from indexly.yaml_pipeline import run_yaml_pipeline
                df, df_stats, table_output = run_yaml_pipeline(file_path, args)
            elif file_type == "xml":
                from indexly.xml_pipeline import run_xml_pipeline
                df, df_stats, table_output = run_xml_pipeline(file_path, args)
            elif file_type == "excel":
                from indexly.excel_pipeline import run_excel_pipeline
                df, df_stats, table_output = run_excel_pipeline(file_path, args)
            elif file_type == "parquet":
                from indexly.parquet_pipeline import run_parquet_pipeline
                df, df_stats, table_output = run_parquet_pipeline(file_path, args)
            else:
                if df is not None:
                    table_output = {
                        "pretty_text": f"{file_type.upper()} file loaded with shape {df.shape}",
                        "meta": metadata,
                    }
                    try:
                        df_stats = df.describe(include="all", datetime_is_numeric=True)
                    except Exception:
                        df_stats = None
                else:
                    console.print(f"[yellow]⚠️ Unsupported file type for analysis: {file_type}[/yellow]")
                    return None

    # -----------------------------
    # --- PERSISTENCE & EXPORT ---
    # -----------------------------
    if df is not None:
        df._no_persist = no_persist_flag
        df._from_orchestrator = True

    if hasattr(df, "_persist_ready") and not getattr(df, "_persisted", False):
        if not no_persist_flag:
            try:
                save_analysis_result(file_path=file_path, file_type=file_type, **df._persist_ready)
                df._persisted = True
            except Exception as e:
                console.print(f"[red]❌ Deferred persistence failed: {e}[/red]")

    cleaned_flag = df_stats is not None and not df_stats.empty
    result = AnalysisResult(
        file_path=str(file_path),
        file_type=file_type,
        df=df,
        summary=df_stats,
        metadata={"table_output": table_output} if table_output else {},
        cleaned=cleaned_flag,
    )

    # Only save if not already persisted
    if not no_persist_flag and df is not None and not df.empty and not getattr(df, "_persisted", False):
        try:
            save_analysis_result(
                file_path=str(file_path),
                file_type=file_type,
                summary=df_stats.to_dict() if hasattr(df_stats, "to_dict") else {},
                sample_data=df.head(3).to_dict(orient="records"),
                metadata={"table_output": table_output} if table_output else {},
                row_count=len(df),
                col_count=len(df.columns),
            )
            df._persisted = True
            result.persisted = True
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to persist analysis result: {e}[/yellow]")

    # -----------------------------
    # --- EXPORT RESULTS ---
    # -----------------------------
    export_path = getattr(args, "export_path", None)
    export_fmt = getattr(args, "format", "txt")
    compress_export = getattr(args, "compress_export", False)

    if export_path and df is not None:
        if file_type == "json":
            import gzip, json
            payload = {
                "metadata": {
                    "analyzed_at": datetime.utcnow().isoformat() + "Z",
                    "source_file": str(file_path),
                    "export_format": "json",
                    "rows": len(df),
                    "columns": len(df.columns),
                },
                "summary_statistics": df_stats.to_dict(orient="index") if df_stats is not None else {},
                "sample_data": df.head(10).to_dict(orient="records"),
                "table_output": table_output,
            }
            compressed_path = export_path if export_path.endswith(".gz") else export_path + ".gz"
            with gzip.open(compressed_path, "wt", encoding="utf-8") as fh:
                json.dump(_json_safe(payload, preserve_numeric=True), fh, indent=2, ensure_ascii=False)
            console.print(f"[green]✅ Exported compressed JSON to: {compressed_path}[/green]")
        else:
            export_results(
                results=table_output,
                export_path=export_path,
                export_format=export_fmt,
                df=df,
                source_file=file_path,
                compress=compress_export,
            )
            console.print(f"✅ Exported to: {export_path}")

    # -----------------------------
    # --- SHOW SUMMARY PREVIEW ---
    # -----------------------------
    if getattr(args, "show_summary", False):
        console.print("\n📊 [bold cyan]Dataset Summary Preview[/bold cyan]")
        if isinstance(df_stats, pd.DataFrame) and not df_stats.empty:
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

    # -----------------------------
    # --- TIMESERIES VISUALIZATION ---
    # -----------------------------
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
