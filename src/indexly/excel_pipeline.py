from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List
import pandas as pd
from rich.console import Console
from datetime import datetime
from io import StringIO

from .datetime_utils import normalize_datetime_columns
from .cleaning.auto_clean import auto_clean_csv


console = Console()

# -----------------------
# Helpers
# -----------------------

def _generate_treeview(df: pd.DataFrame, file_path: Path) -> str:
    from rich.tree import Tree
    from rich.text import Text
    from rich.console import Console as _Console
    from io import StringIO
    tree = Tree(Text(f"📦 {file_path.name} ({df.shape[0]} rows × {df.shape[1]} cols)", style="bold cyan"))
    for col in df.columns:
        dtype = str(df[col].dtype)
        preview = df[col].dropna().astype(str).head(3).tolist()
        preview_text = ", ".join(preview) if preview else "—"
        branch = tree.add(f"{col} : {dtype}")
        branch.add(preview_text)
    buf = StringIO()
    _Console(file=buf, force_terminal=True, color_system="truecolor").print(tree)
    return buf.getvalue()

def _generate_markdown_summary(df: pd.DataFrame, meta: Dict[str, Any]) -> str:
    lines = [
        "# 🧾 Excel File Summary",
        f"- **Rows:** {meta['rows']}",
        f"- **Columns:** {meta['cols']}",
        f"- **Generated:** {datetime.utcnow().isoformat()}Z",
        f"- **Sheets Loaded:** {', '.join(meta.get('sheets', []))}",
        "",
        "## 🧩 Columns Overview:",
    ]
    for col in df.columns:
        lines.append(f"- `{col}` ({str(df[col].dtype)})")

    # Numeric stats
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        lines.append("\n### Numeric Columns\n")
        lines.append(numeric.describe().round(3).transpose().to_markdown())

    # Categorical stats
    cat = df.select_dtypes(include=["object", "category"])
    if not cat.empty:
        lines.append("\n### Categorical Columns\n")
        lines.append(cat.describe().transpose().to_markdown())

    return "\n".join(lines)


# -----------------------
# Excel pipeline (multi-sheet upgrade)
# -----------------------


def run_excel_pipeline(
    *,
    file_path: Optional[Path] = None,
    df: Optional[pd.DataFrame] = None,
    args: Optional[Any] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Multi-sheet Excel pipeline with --sheet-name selection and unified merging.
    """
    raw: Dict[str, Any] = {}

    # -------------------------
    # STEP 1 – LOAD SHEETS
    # -------------------------
    if df is None and file_path:
        try:
            sheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")
            all_sheet_names = list(sheets.keys())

            console.print(f"[green]Detected sheets:[/green] {', '.join(all_sheet_names)}")
            for name, s in sheets.items():
                console.print(f"  - {name}: shape={s.shape}")

            # --- FIX: normalize args.sheet_name into a list ---
            requested_sheets = getattr(args, "sheet_name", None)
            if isinstance(requested_sheets, str):
                requested_sheets = requested_sheets.split()  # split space-separated names
            elif requested_sheets is None:
                requested_sheets = []

            # Select sheets
            if "all" in [s.lower() for s in requested_sheets]:
                selected = sheets
            elif requested_sheets:
                selected = {name: sheets[name] for name in requested_sheets if name in sheets}
            else:
                selected = sheets
            missing = [s for s in requested_sheets if s not in sheets]
            if missing:
                console.print(
                    f"[red]❌ Requested sheet(s) not found:[/red] {', '.join(missing)}"
                )
                console.print(
                    f"[blue]📄 Available sheets:[/blue] {', '.join(all_sheet_names)}"
                )
                console.print(
                    "[yellow]⚠️ No data analyzed because none of the requested sheets were found.[/yellow]"
                )
            if not selected:
                console.print(f"[red]❌ No valid sheet(s) found in {file_path.name}[/red]")
                return None, None, {"pretty_text": "No valid Excel sheets found.", "meta": {}}

            # Merge selected sheets
            df_list = []
            for sheet_name, sdf in selected.items():
                sdf = sdf.copy()
                sdf["_sheet_name"] = sheet_name
                df_list.append(sdf)

            df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

            # --- FIX: populate raw["selected"] correctly ---
            raw = {"sheets": all_sheet_names, "selected": list(selected.keys())}

        except Exception as e:
            console.print(f"[red]❌ Failed to load Excel file: {e}[/red]")
            return None, None, {"pretty_text": "Failed to load Excel file.", "meta": {"rows": 0, "cols": 0}}

    elif isinstance(df, tuple):
        df = next((x for x in df if isinstance(x, pd.DataFrame)), None)
        raw_candidate = next((x for x in df if isinstance(x, dict)), None)
        raw = raw_candidate if raw_candidate else raw or {}
    else:
        raw = raw or {}

    if df is None or df.empty:
        console.print("[yellow]⚠️ No usable sheet/data found for Excel pipeline.[/yellow]")
        return None, None, {"pretty_text": "No data available for Excel pipeline.", "meta": {"rows": 0, "cols": 0}}

    if file_path:
        setattr(df, "_source_file_path", str(file_path))

    # -------------------------
    # STEP 2 – CLEANING
    # -------------------------
    clean_summary_records = None
    if args and getattr(args, "auto_clean", False):
        try:
            persist_flag = not getattr(args, "no_persist", False)
            df, clean_summary_records, derived_map = auto_clean_csv(
                df,
                fill_method=getattr(args, "fill_method", "mean"),
                verbose=False,
                derive_dates=getattr(args, "derive_dates", "all"),
                user_datetime_formats=getattr(args, "datetime_formats", None),
                date_threshold=getattr(args, "date_threshold", 0.3),
                persist=persist_flag,
            )
            df.attrs["_derived_map"] = derived_map
        except Exception as e:
            console.print(f"[yellow]⚠️ Auto-clean failed: {e}[/yellow]")

    # -------------------------
    # STEP 3 – DATETIME NORMALIZATION
    # -------------------------
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="excel")
    except Exception as e:
        dt_summary = {}
        console.print(f"[yellow]⚠️ Datetime normalization warning: {e}[/yellow]")

    # -------------------------
    # STEP 4 – NUMERIC TIGHTENING
    # -------------------------
    for col in df.columns[df.dtypes == "object"]:
        try:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                df[col] = converted
        except Exception:
            pass

    # -------------------------
    # STEP 5 – DESCRIPTIVE STATS
    # -------------------------
    try:
        df_stats = df.describe(include="all", datetime_is_numeric=True)
    except Exception:
        df_stats = None

    # -------------------------
    # STEP 6 – META & OUTPUT
    # -------------------------
    meta = {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "sheets": raw.get("selected", []),  # <- now properly filled
    }

    table_output = {
        "pretty_text": f"✅ Excel file analyzed successfully with shape {df.shape}",
        "meta": meta,
        "datetime_summary": dt_summary,
        "clean_summary": clean_summary_records,
        "raw": raw,
        "markdown": _generate_markdown_summary(df, meta),
    }

    if getattr(args, "treeview", False) and file_path:
        try:
            table_output["tree"] = _generate_treeview(df, Path(file_path))
        except Exception as e:
            console.print(f"[yellow]⚠️ Tree generation failed: {e}[/yellow]")

    setattr(df, "_persist_ready", True)
    return df, df_stats, table_output


