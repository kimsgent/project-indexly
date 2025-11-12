# src/indexly/analysis_orchestrator.py
from __future__ import annotations
import json
import pandas as pd
from pathlib import Path
from rich.table import Table
from typing import Optional, Any
from rich.console import Console
from .export_utils import safe_export
from .analysis_result import AnalysisResult
from .csv_pipeline import run_csv_pipeline
from .json_pipeline import run_json_pipeline
from .db_pipeline import run_db_pipeline
from .xml_pipeline import run_xml_pipeline
from .parquet_pipeline import run_parquet_pipeline
from .csv_analyzer import export_results
from .analyze_utils import (
    load_cleaned_data,
    validate_file_content,
    save_analysis_result,
)
from indexly.universal_loader import detect_and_load, detect_file_type

console = Console()


# --- Universal persistence block ---
def _persist_analysis(
    df: pd.DataFrame | None,
    df_preview: pd.DataFrame | None,
    file_path: Path,
    file_type: str,
    table_output: dict | None = None,
    derived_map: dict | None = None,
    args: Optional[Any] = None,
    verbose: bool = True,
) -> bool:
    """
    Persist cleaned/processed data to DB if not already persisted and not disabled via --no-persist.
    Returns True if persisted, False if skipped.
    """
    # Respect --no-persist CLI flag
    if getattr(args, "no_persist", False):
        if verbose:
            console.print(
                f"[dim]💤 Skipping persistence (--no-persist) for {file_path.name}[/dim]"
            )
        return False

    # Avoid double writes
    if getattr(df, "_persisted", False) or getattr(df_preview, "_persisted", False):
        if verbose:
            console.print(f"[dim]💾 Already persisted: {file_path.name}[/dim]")
        return False

    data_to_save = df if df is not None else df_preview
    if data_to_save is None or data_to_save.empty:
        if verbose:
            console.print(f"[yellow]⚠️ Nothing to persist for {file_path.name}[/yellow]")
        return False

    try:
        summary_records = getattr(df, "_summary_records", None)
        derived_map = derived_map or getattr(df, "_derived_map", None)

        save_analysis_result(
            file_path=str(file_path),
            file_type=file_type,
            summary=pd.DataFrame(summary_records) if summary_records else None,
            sample_data=data_to_save.head(10),
            metadata=derived_map or {},
            row_count=len(data_to_save),
            col_count=len(data_to_save.columns),
        )

        # Mark as persisted
        if df is not None:
            df._persisted = True
        if df_preview is not None:
            df_preview._persisted = True

        if verbose:
            console.print(
                f"[green]✔ Persisted cleaned data for {file_path.name}[/green]"
            )
        return True

    except Exception as e:
        console.print(f"[red]❌ Failed to persist data for {file_path.name}: {e}[/red]")
        return False


def analyze_file(args) -> Optional[AnalysisResult]:
    file_path = Path(args.file).resolve()
    file_type = detect_file_type(file_path)

    df = df_stats = table_output = metadata = summary = None
    df_preview = None
    legacy_mode = False

    # --- Legacy passthrough
    cmd = getattr(args, "command", "")
    if cmd in {"analyze-csv", "analyze-json"}:
        pipeline = run_csv_pipeline if cmd == "analyze-csv" else run_json_pipeline
        df, df_stats, table_output = pipeline(file_path, args)
        file_type = "csv" if cmd == "analyze-csv" else "json"
        legacy_mode = True

        # --- Persist legacy data
        _persist_analysis(df, None, file_path, file_type, table_output, args=args)

    # --- Use saved/cleaned data
    use_saved = getattr(args, "use_saved", False) or getattr(args, "use_cleaned", False)
    if use_saved:
        try:
            exists, record = load_cleaned_data(file_path)
            if exists and record:
                console.print(
                    f"[cyan]♻️ Using previously saved data for {file_path.name}[/cyan]"
                )
                data_json = record.get("data_json", {})
                metadata_json = record.get("metadata_json", {})
                df = pd.DataFrame(data_json.get("sample_data", []))
                df_stats = (
                    pd.DataFrame(data_json.get("summary_statistics", {})).T
                    if data_json.get("summary_statistics")
                    else None
                )
                table_output = metadata_json.get("table_output", None)
                file_type = record.get("file_type", file_type)

                if getattr(args, "show_summary", False):
                    if df_stats is not None and not df_stats.empty:
                        table = Table(show_header=True, header_style="bold magenta")
                        table.add_column("Statistic")
                        for col in df_stats.columns:
                            table.add_column(str(col))
                        for stat_name, row in df_stats.iterrows():
                            table.add_row(stat_name, *[str(v) for v in row])
                        console.print(table)
                    if table_output:
                        console.print(
                            "\n📋 [bold cyan]Formatted Table Output[/bold cyan]"
                        )
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

    # --- Validate
    if not validate_file_content(file_path, file_type):
        console.print("[red]❌ File validation failed — analysis aborted.[/red]")
        return None

    # --- Universal loader (skip CSV/JSON passthrough)
    if not legacy_mode:
        try:
            load_result = detect_and_load(str(file_path), args)
            if not load_result:
                console.print(
                    f"[red]❌ Universal loader failed for {file_path.name}[/red]"
                )
                return None
        except Exception as e:
            console.print(
                f"[red]❌ Universal loader error for {file_path.name}: {e}[/red]"
            )
            return None

        file_type = load_result.get("file_type", file_type)
        raw = load_result.get("raw")
        metadata = load_result.get("metadata", {})
        df_preview = load_result.get("df_preview") if file_type == "xml" else None
        df = load_result.get("df") if file_type != "xml" else None

        try:
            # --- Direct passthrough for CSV/JSON (.gz handled by pipelines)
            if file_type in {"csv", "json"}:
                pipeline = run_csv_pipeline if file_type == "csv" else run_json_pipeline
                df, df_stats, table_output = pipeline(file_path, args, df=df)
            # --- Other pipelines unchanged
            elif file_type in {"sqlite", "db"}:
                df, df_stats, table_output = run_db_pipeline(file_path, args)
            elif file_type in {"yaml", "yml"}:
                from indexly.yaml_pipeline import run_yaml_pipeline

                df, df_stats, table_output = run_yaml_pipeline(
                    df=df, raw=raw, args=args
                )
                vertical_summary = table_output.get("vertical_summary", None)
            elif file_type == "xml":
                console.print(f"[cyan]📂 Processing XML file: {file_path.name}[/cyan]")
                df_preview, summary, metadata = run_xml_pipeline(
                    file_path=file_path, args=args
                )
            elif file_type == "excel":
                from indexly.excel_pipeline import run_excel_pipeline
                df, df_stats, table_output = run_excel_pipeline(df=df, args=args)
            elif file_type == "parquet":
                console.print(f"[cyan]📂 Processing Parquet file: {file_path.name}[/cyan]")
                try:
                    df, df_stats, table_output = run_parquet_pipeline(df=df, args=args)
                except Exception as e:
                    console.print(f"[red]❌ Parquet pipeline failed: {e}[/red]")
                    return None
                # Optional TreeView rendering support
                if getattr(args, "treeview", False) and table_output.get("tree"):
                    console.print("\n🌳 [bold cyan]Tree-View Summary (Parquet)[/bold cyan]")
                    console.print(table_output["tree"])
                # Markdown summary (if available)
                if table_output.get("markdown"):
                    console.print("\n🧾 [bold cyan]Markdown Summary (Parquet)[/bold cyan]")

                    md_text = table_output["markdown"]

                    # Inject statistical overview if df_stats is available
                    if isinstance(df_stats, pd.DataFrame) and not df_stats.empty:
                        stats_md = df_stats.round(3).to_markdown(index=True, tablefmt="github")
                        if "_Statistics unavailable._" in md_text:
                            md_text = md_text.replace(
                                "_Statistics unavailable._", f"\n{stats_md}\n"
                            )
                        else:
                            # Append stats if not already present
                            md_text += "\n## 📊 Statistical Overview\n" + stats_md + "\n"
                    else:
                        if "_Statistics unavailable._" not in md_text:
                            md_text += "\n_Statistics unavailable._\n"

                    console.print(md_text)

                # Optional sample preview
                if isinstance(df, pd.DataFrame) and not df.empty:
                    console.print("\n🧩 [bold cyan]Sample Data Preview (Parquet)[/bold cyan]")
                    console.print(df.head(10).to_markdown(index=False))

            else:
                if df is not None:
                    try:
                        df_stats = df.describe(include="all", datetime_is_numeric=True)
                    except Exception:
                        df_stats = None
                    table_output = {
                        "pretty_text": f"{file_type.upper()} file loaded with shape {df.shape}",
                        "meta": metadata,
                    }
                else:
                    console.print(
                        f"[yellow]⚠️ Unsupported file type for analysis: {file_type}[/yellow]"
                    )
                    return None
        except Exception as e:
            console.print(
                f"[red]❌ Pipeline error for {file_path.name} ({file_type}): {e}[/red]"
            )
            return None

        # --- Persist universal loader results ---
        _persist_analysis(df, df_preview, file_path, file_type, table_output, args=args)

    # --- Export
    export_path = getattr(args, "export_path", None)
    export_fmt = getattr(args, "format", "txt")
    compress_export = getattr(args, "compress_export", False)
    db_mode = getattr(args, "db_mode", "replace")  # Smart bonus
    # For CSV/Excel/Parquet, pass dict directly
    if export_path and (df is not None or df_preview is not None):
        export_df = df if df is not None else df_preview

        # 🔧 Choose serialization logic based on format
        # For txt/md/json, serialize as string
        if export_fmt in ("csv", "excel", "parquet"):
            safe_results = table_output  # keep dict for tabular exporters
        elif export_fmt == "db":
            safe_results = table_output  # DB handled internally, keep as is
        else:
            # txt, md, json → stringify
            safe_results = table_output
            if isinstance(safe_results, (dict, list)):
                safe_results = json.dumps(safe_results, indent=2, ensure_ascii=False)

        # 🪶 Unified export call
        export_results(
            results=safe_results,
            export_path=export_path,
            export_format=export_fmt,
            df=export_df,
            source_file=file_path,
            compress=compress_export,
            db_mode=db_mode,
        )

        console.print(f"[green]✅ Exported to:[/green] [bold]{export_path}[/bold]")

    # --- Dataset Summary Preview
    if getattr(args, "show_summary", False):
        import shutil

        console.print("\n📊 [bold cyan]Dataset Summary Preview[/bold cyan]")

        # --------------------------
        # XML files remain untouched
        # --------------------------
        if file_type == "xml" and summary:
            if getattr(args, "invoice", False):
                console.print(
                    summary.get("md", "[yellow]No invoice summary available.[/yellow]")
                )
                if df_preview is not None and not df_preview.empty:
                    console.print("\n🧩 [bold cyan]Sample Data Preview[/bold cyan]")
                    console.print(df_preview.head(5))
            elif getattr(args, "treeview", False):
                console.print("\n🌳 [bold cyan]Tree-View Summary[/bold cyan]")
                console.print(
                    summary.get("tree", "[yellow]No tree view available.[/yellow]")
                )
                console.print("\n🧾 [bold cyan]Flattened Preview[/bold cyan]")
                if df_preview is not None and not df_preview.empty:
                    console.print(df_preview.head(10).to_markdown(index=False))
                else:
                    console.print("[yellow]No preview available.[/yellow]")
            else:
                console.print(
                    summary.get("md", "[yellow]No summary available.[/yellow]")
                )
        if file_type in {"yaml", "yml"}:
            # Vertical Summary
            if vertical_summary is not None and not vertical_summary.empty:
                console.print("[bold cyan]\n🧩 Vertical Summary View[/bold cyan]")
                console.print(vertical_summary.head(40).to_markdown(index=False))

            # Optional tree view
            if getattr(args, "treeview", False) and table_output.get("tree"):
                console.print("\n🌳 [bold cyan]Tree-View Summary[/bold cyan]")
                console.print(table_output["tree"])

            # Markdown summary at the bottom
            if table_output.get("markdown"):
                console.print("\n🧾 [bold cyan]Markdown Summary[/bold cyan]")
                console.print(table_output["markdown"])

        # --------------------------
        # All other filetypes
        # --------------------------
        elif isinstance(df, pd.DataFrame) and not df.empty:
            # Dynamically size columns and truncation based on terminal width
            term_width = shutil.get_terminal_size((120, 40)).columns
            col_fit_estimate = max(5, term_width // 25)
            max_cols = (
                len(df.columns)
                if getattr(args, "wide_view", False)
                else min(col_fit_estimate, len(df.columns))
            )
            truncate_len = max(20, term_width // 6)
            max_rows = 10

            display_cols = df.columns[:max_cols]

            # If single-row, show vertically
            if len(df) == 1 and len(df.columns) > max_cols:
                console.print("[bold cyan]\n🧩 Vertical Summary View[/bold cyan]")
                df_display = df.T.reset_index()
                df_display.columns = ["Field", "Value"]
                console.print(df_display.head(40).to_markdown(index=False))
            else:
                table = Table(
                    title="Dataset Summary",
                    show_header=True,
                    header_style="bold magenta",
                    expand=True,
                )
                for col in display_cols:
                    table.add_column(f"{col} [{df[col].dtype}]")

                for _, row in df.head(max_rows).iterrows():
                    table.add_row(
                        *[
                            str(x)[:truncate_len]
                            + ("…" if len(str(x)) > truncate_len else "")
                            for x in row[display_cols]
                        ]
                    )

                console.print(table)

            # Optional numeric summary
            numeric_cols = df.select_dtypes(include=["number"]).columns
            if len(numeric_cols) > 0:
                stats_table = Table(
                    title="Numeric Summary",
                    show_header=True,
                    header_style="bold green",
                    expand=True,
                )
                stats_table.add_column("Column")
                stats_table.add_column("Count")
                stats_table.add_column("Mean")
                stats_table.add_column("Min")
                stats_table.add_column("Max")
                stats_table.add_column("Std")

                for col in numeric_cols:
                    series = df[col]
                    stats_table.add_row(
                        col,
                        str(series.count()),
                        f"{series.mean():.2f}" if series.count() > 0 else "NaN",
                        f"{series.min():.2f}" if series.count() > 0 else "NaN",
                        f"{series.max():.2f}" if series.count() > 0 else "NaN",
                        f"{series.std():.2f}" if series.count() > 1 else "NaN",
                    )

                console.print(stats_table)

            # Optional export for full summaries
            if getattr(args, "export_summary", False):
                export_dir = Path.cwd()
                summary_path = export_dir / f"{file_path.stem}_summary.md"
                try:
                    df.head(20).to_markdown(summary_path, index=False)
                    console.print(
                        f"[green]📁 Saved full summary to:[/green] {summary_path}"
                    )
                except Exception as e:
                    console.print(f"[yellow]⚠️ Failed to save summary: {e}[/yellow]")

        else:
            console.print("[yellow]No summary data available.[/yellow]")

        # Preserve formatted table output if exists
        if table_output and "pretty_text" in table_output:
            console.print("\n📋 [bold cyan]Formatted Table Output[/bold cyan]")
            console.print(table_output["pretty_text"])

    cleaned_flag = (df is not None and not df.empty) or (df_preview is not None)
    return AnalysisResult(
        file_path=str(file_path),
        file_type=file_type,
        df=df if df is not None else df_preview,
        summary=(summary if file_type == "xml" else df_stats),
        metadata={"table_output": table_output} if table_output else {},
        cleaned=cleaned_flag,
        persisted=True if file_type == "xml" else getattr(df, "_persisted", False),
    )
