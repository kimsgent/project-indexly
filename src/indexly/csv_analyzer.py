# Clean description + stat functions

import re
import json
import math
import os
import sys
import csv
import importlib.util
import subprocess
import argparse
import importlib.util
import subprocess
from pathlib import Path
from rich.console import Console
from tqdm import tqdm
from datetime import datetime
from rich.console import Console

console = Console()

REQUIRED_PACKAGES = ["pandas", "numpy", "scipy", "tabulate"]


def ensure_packages(packages):
    for pkg in packages:
        if importlib.util.find_spec(pkg) is None:
            print(f"📦 Installing missing package: {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


ensure_packages(REQUIRED_PACKAGES)

# ✅ Now safe to import
import pandas as pd
import numpy as np
import shutil
import json
import math
from decimal import Decimal
from fractions import Fraction
from scipy.stats import iqr
from tabulate import tabulate
from datetime import datetime, date
import datetime as dt
from tqdm import tqdm  # ✅ For progress bar

try:
    from scipy.stats import iqr
except ImportError:
    iqr = None


def check_requirements():
    try:
        import pandas
        import tabulate
    except ImportError:
        print("[!] Required packages not found. Installing...")
        os.system(f"{sys.executable} -m pip install pandas tabulate")
        if iqr is None:
            os.system(f"{sys.executable} -m pip install scipy")


def detect_delimiter(file_path):
    import re
    import csv

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        sample = f.read(4096)

    possible_delims = [",", ";", "\t", "|", ":", "~"]
    lines = re.split(r"[\r\n]+", sample.strip())[:10]
    freq_scores = {}

    for delim in possible_delims:
        counts = [line.count(delim) for line in lines if line]
        if counts:
            avg = sum(counts) / len(counts)
            variance = sum((c - avg) ** 2 for c in counts) / len(counts)
            freq_scores[delim] = avg / (1 + variance)

    best_delim = max(freq_scores, key=freq_scores.get) if freq_scores else None

    try:
        sniffer_delim = csv.Sniffer().sniff(sample).delimiter
    except csv.Error:
        sniffer_delim = None

    delimiter = best_delim or sniffer_delim
    if not delimiter:
        print("❌ Could not detect a valid CSV delimiter.")
        return None

    # 👇 Removed print here
    return delimiter


def analyze_csv(file_or_df, from_df=False):
    """
    Analyze a CSV file or a provided DataFrame.
    - If from_df=True, file_or_df is treated as a DataFrame (already cleaned)
    - Otherwise, file_or_df is treated as a file path to read CSV
    Returns: df, df_stats, table_output
    """

    console = Console()
    file_path = None

    # ---------------------------
    # 📂 Load DataFrame
    # ---------------------------
    if from_df:
        df = file_or_df.copy()
    else:
        try:
            file_path = Path(file_or_df).expanduser().resolve(strict=False)
        except Exception:
            console.print(f"[!] Invalid file path: {file_or_df}", style="bold red")
            return None, None, None

        if not file_path.exists():
            console.print(f"[!] File not found: {file_or_df}", style="bold red")
            alt_path = Path.cwd() / file_or_df
            if alt_path.exists():
                file_path = alt_path
                console.print(f"ℹ️ Using fallback path: {alt_path}", style="bold cyan")
            else:
                return None, None, None

        try:
            delimiter = detect_delimiter(file_path)
            console.print(f"📄 Detected delimiter: '{delimiter}'", style="bold cyan")
            df = pd.read_csv(file_path, delimiter=delimiter, encoding="utf-8")
        except Exception as e:
            console.print(f"[!] Failed to read CSV: {e}", style="bold red")
            return None, None, None

    # ---------------------------
    # 🚨 Empty dataset check
    # ---------------------------
    if df.empty:
        console.print("[!] No data to analyze.", style="bold red")
        return None, None, None

    # ---------------------------
    # 🔢 Robust numeric inference
    # ---------------------------
    for col in df.columns:
        # Skip columns already numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        # Attempt conversion, coercing invalids to NaN
        converted = pd.to_numeric(df[col], errors="coerce")
        # If most values convert successfully, adopt this column as numeric
        if converted.notna().mean() > 0.8:
            df[col] = converted

    # ---------------------------
    # 🧮 Numeric & datetime detection
    # ---------------------------
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        datetime_numeric_cols = [c for c in df.columns if c.endswith("_timestamp")]
        if datetime_numeric_cols:
            numeric_cols = datetime_numeric_cols
            console.print(
                "ℹ️ Using datetime-derived numeric columns for analysis...",
                style="bold cyan",
            )

    if not numeric_cols:
        console.print(
            "⚠️ No valid numeric or date columns available for analysis.",
            style="bold yellow",
        )
        return df, None, None

    numeric_df = df[numeric_cols]

    # ---------------------------
    # 📊 Compute statistics
    # ---------------------------
    stats = []
    for col in numeric_df.columns:
        values = numeric_df[col].dropna()
        if values.empty:
            continue

        q1, q3 = values.quantile(0.25), values.quantile(0.75)
        col_iqr = iqr(values) if callable(iqr) else (q3 - q1)

        stats.append(
            [
                col,
                values.count(),
                df[col].isnull().sum(),
                values.mean(),
                values.median(),
                values.std(),
                values.sum(),
                values.min(),
                values.max(),
                q1,
                q3,
                col_iqr,
            ]
        )

    headers = [
        "Column",
        "Count",
        "Nulls",
        "Mean",
        "Median",
        "Std Dev",
        "Sum",
        "Min",
        "Max",
        "Q1",
        "Q3",
        "IQR",
    ]
    df_stats = pd.DataFrame(stats, columns=headers)

    # ---------------------------
    # 🧠 Smart number formatting
    # ---------------------------
    def format_number(val):
        if isinstance(val, (int, float, np.number)):
            if np.isnan(val):
                return "-"
            if abs(val) >= 1e6 or abs(val) < 1e-3:
                return f"{val:.3e}"
            return f"{val:,.3f}".rstrip("0").rstrip(".")
        return str(val)

    df_stats = df_stats.apply(lambda col: col.map(format_number))

    # ---------------------------
    # 🖥️ Adaptive table width
    # ---------------------------
    term_width = shutil.get_terminal_size((120, 20)).columns
    max_width = term_width - 4
    col_count = len(df_stats.columns)
    max_col_width = max(8, int(max_width / col_count))

    for c in df_stats.columns:
        df_stats[c] = df_stats[c].apply(
            lambda v: (
                str(v)[: max_col_width - 1] + "…"
                if len(str(v)) > max_col_width
                else str(v)
            )
        )

    # ---------------------------
    # 📋 Render table
    # ---------------------------
    table_output = tabulate(df_stats, headers="keys", tablefmt="grid", showindex=False)

    return df, df_stats, table_output


## JSON Export


def _json_safe(obj, preserve_numeric: bool = True):
    """
    Recursively convert objects to JSON-safe types.
    Handles pandas, numpy, datetime, Timestamp, Decimal, and Fraction types.

    Args:
        obj: Object to convert.
        preserve_numeric: If True, keeps all numeric types as numeric rather than stringifying.
                          Recommended for analytical exports.
    """

    # --- Basic numeric types ---
    if isinstance(obj, (pd.Timestamp, np.datetime64)):
        return str(pd.to_datetime(obj).isoformat())
    elif isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()

    # --- Numeric preservation logic ---
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        # Handle NaN and infinities for strict JSON compliance
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, Decimal):
        # Decimal is not JSON serializable by default
        if preserve_numeric:
            return float(obj)
        else:
            return str(obj)
    elif isinstance(obj, Fraction):
        if preserve_numeric:
            return float(obj)
        else:
            return str(obj)

    # --- Containers ---
    elif isinstance(obj, dict):
        return {
            k: _json_safe(v, preserve_numeric=preserve_numeric) for k, v in obj.items()
        }
    elif isinstance(obj, (list, tuple, set)):
        return [_json_safe(v, preserve_numeric=preserve_numeric) for v in obj]

    # --- Pandas containers ---
    elif isinstance(obj, pd.DataFrame):
        return _json_safe(
            obj.to_dict(orient="records"), preserve_numeric=preserve_numeric
        )
    elif isinstance(obj, pd.Series):
        return _json_safe(obj.to_dict(), preserve_numeric=preserve_numeric)

    # --- Numpy scalar ---
    elif isinstance(obj, np.generic):
        return obj.item()

    # --- Fallback ---
    return obj


def export_results(
    results,
    export_path=None,
    export_format="txt",
    df=None,
    source_file=None,
    chunk_size=10000,
    compress=False,  # 🆕 New
):
    """
    Export analysis results to text, markdown, or JSON formats.
    - Cleans summary statistics text for readability
    - When exporting to JSON, includes both text and structured table form (if available)
    - Streams large dataframes in chunks for memory safety
    - Optional gzip compression for JSON export (.json.gz)
    """

    import os, re, json, math, gzip
    from tqdm import tqdm
    from datetime import datetime
    import pandas as pd

    # --- Normalize export path ---
    if not export_path or str(export_path).strip() == "":
        base_name = "analysis"
        if source_file:
            base_name = os.path.splitext(os.path.basename(source_file))[0]
        export_path = f"{base_name}.{export_format}"

    if os.path.isdir(export_path):
        filename = f"analysis.{export_format}"
        export_path = os.path.join(export_path, filename)

    # 🧩 Ensure .gz extension if compression enabled
    if compress and not export_path.endswith(".gz"):
        export_path = f"{export_path}.gz"

    export_path = str(export_path)
    os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)

    # --- Cleanup conflicting file names (case insensitive) ---
    dir_name = os.path.dirname(export_path) or "."
    base_name = os.path.basename(export_path).lower()
    try:
        for f in os.listdir(dir_name):
            if f.lower() == base_name and f != os.path.basename(export_path):
                os.remove(os.path.join(dir_name, f))
    except Exception:
        pass

    # ----------------------------------------
    # 🔧 Helper: Clean text summary
    # ----------------------------------------
    def _clean_summary_text(text: str) -> str:
        if not text or not isinstance(text, str):
            return text or ""

        lines = text.splitlines()
        cleaned = []
        for line in tqdm(lines, desc="Cleaning summary_statistics", unit="lines"):
            s = line.strip()
            if re.fullmatch(r"^[\+\-\=\| ]+$", s):
                continue

            def _sci_to_full(match):
                token = match.group(0)
                try:
                    val = float(token)
                    if abs(val) >= 1e6 and float(val).is_integer():
                        return str(int(val))
                    return ("{:.6f}".format(val)).rstrip("0").rstrip(".")
                except Exception:
                    return token

            s = re.sub(r"\b\d+\.?\d*e[+\-]?\d+\b", _sci_to_full, s, flags=re.IGNORECASE)
            s = re.sub(r"\s{2,}", " ", s)
            cleaned.append(s)

        return "\n".join(cleaned)

    # ----------------------------------------
    # 🧩 Helper: Parse markdown-like table → JSON list
    # ----------------------------------------
    def _parse_summary_table(text: str):
        if not text or "|" not in text:
            return []

        lines = [ln.strip() for ln in text.splitlines() if "|" in ln]
        if not lines or len(lines) < 2:
            return []

        headers = [h.strip() for h in lines[0].split("|") if h.strip()]
        data_rows = []

        for ln in lines[1:]:
            if set(ln.replace("|", "").strip()) <= {"─", "━", "═", "╇", "╪", "┼", "-"}:
                continue

            parts = [c.strip() for c in ln.split("|") if c.strip()]
            if len(parts) != len(headers):
                continue

            record = {}
            for h, val in zip(headers, parts):
                if val in {"-", "–", "—", "N/A", "NaN", "None", ""}:
                    record[h] = None
                    continue
                if val.endswith("%"):
                    try:
                        record[h] = float(val.strip("%").replace(",", "").strip())
                        continue
                    except Exception:
                        pass
                val_no_commas = val.replace(",", "")
                if re.match(r"^-?\d+(\.\d+)?$", val_no_commas):
                    try:
                        num_val = float(val_no_commas)
                        record[h] = int(num_val) if num_val.is_integer() else num_val
                        continue
                    except Exception:
                        pass
                record[h] = val
            data_rows.append(record)
        return data_rows

    # ----------------------------------------
    # ✍️ Export
    # ----------------------------------------
    if export_format in ("md", "txt"):
        with open(export_path, "w", encoding="utf-8") as f:
            content = results.replace("+", "|") if export_format == "md" else results
            f.write(content)

    elif export_format == "json":
        metadata = {
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "source_file": str(source_file) if source_file else None,
            "export_format": "json",
            "rows": len(df) if df is not None else None,
            "columns": len(df.columns) if df is not None else None,
        }

        if isinstance(results, dict) and "text_summary" in results:
            raw_summary = results.get("text_summary", "")
        elif isinstance(results, str):
            raw_summary = results
        else:
            raw_summary = str(results)

        cleaned_summary = _clean_summary_text(raw_summary)
        structured_summary = _parse_summary_table(cleaned_summary)

        summary_data = {
            "text_summary": cleaned_summary,
            "structured": structured_summary or None,
        }

        # 🧩 Helper for choosing correct open function
        open_func = gzip.open if compress else open
        mode = "wt" if compress else "w"

        # --- Write JSON top-level ---
        with open_func(export_path, mode, encoding="utf-8") as f:
            f.write("{\n")
            f.write(f'"metadata": {json.dumps(_json_safe(metadata), ensure_ascii=False)},\n')
            f.write(f'"summary_statistics": {json.dumps(_json_safe(summary_data), ensure_ascii=False)},\n')
            f.write('"sample_data": [\n')

            if df is not None and len(df) > 0:
                total_chunks = math.ceil(len(df) / chunk_size)
                for i, start in enumerate(range(0, len(df), chunk_size)):
                    chunk = df.iloc[start : start + chunk_size]
                    for j, row in enumerate(
                        tqdm(
                            chunk.itertuples(index=False),
                            desc=f"Exporting chunk {i+1}/{total_chunks}",
                            unit="rows",
                        )
                    ):
                        row_dict = _json_safe(row._asdict(), preserve_numeric=True)
                        row_json = json.dumps(row_dict, ensure_ascii=False)
                        last_chunk = i == total_chunks - 1
                        last_row = j == len(chunk) - 1
                        if not (last_chunk and last_row):
                            f.write(row_json + ",\n")
                        else:
                            f.write(row_json + "\n")

            f.write("]\n}\n")
    
    # ----------------------------------------
    # 🪶 Rich CSV / Parquet / Excel export
    # ----------------------------------------
    elif export_format in ("csv", "excel", "parquet"):
        import pyarrow as pa
        import pyarrow.parquet as pq
        import pandas as pd

        if df is None or df.empty:
            raise ValueError(f"No DataFrame available for {export_format.upper()} export.")

        metadata = {
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "source_file": str(source_file) if source_file else None,
            "rows": len(df),
            "columns": len(df.columns),
            "format": export_format,
        }

        # 🧩 Construct summary if present
        if isinstance(results, dict) and "text_summary" in results:
            summary_text = results.get("text_summary", "")
        elif isinstance(results, str):
            summary_text = results
        else:
            summary_text = ""

        summary_text = _clean_summary_text(summary_text)
        structured_summary = _parse_summary_table(summary_text)
        summary_info = {
            "text_summary": summary_text,
            "structured": structured_summary or None,
        }

        # --- Enrich summary_info with pipeline stats ---
        if isinstance(results, dict):
            if "datetime_summary" in results:
                summary_info["datetime_summary"] = results["datetime_summary"]
            if "df_stats" in results:
                summary_info["numeric_stats"] = json.loads(results["df_stats"].to_json(orient="index"))
            if "meta" in results:
                summary_info["meta_info"] = results["meta"]

        # --- CSV ---
        if export_format == "csv":
            meta_path = export_path.replace(".csv", "_meta.json")
            df.to_csv(export_path, index=False)
            with open(meta_path, "w", encoding="utf-8") as m:
                json.dump({"metadata": metadata, "summary": summary_info}, m, ensure_ascii=False, indent=2)

        # --- Excel ---
        elif export_format == "excel":
            meta_path = export_path.replace(".xlsx", "_meta.json")
            with pd.ExcelWriter(export_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="data")
                # Write summary as a new sheet
                summary_df = pd.DataFrame(summary_info.get("structured") or [])
                if not summary_df.empty:
                    summary_df.to_excel(writer, index=False, sheet_name="summary")
            with open(meta_path, "w", encoding="utf-8") as m:
                json.dump(metadata, m, ensure_ascii=False, indent=2)

        # --- Parquet ---

        elif export_format == "parquet":
            if df is None or df.empty:
                raise ValueError(f"No DataFrame available for {export_format.upper()} export.")

            # --- DEBUG: inspect df ---
            console.print(f"[cyan]💡 Debug: DataFrame shape={df.shape}, columns={df.columns.tolist()}[/cyan]")
            console.print(df.head(5))  # show first 5 rows
            total_rows = len(df)

            # Optional: show tqdm progress for row export
            for i, start in enumerate(tqdm(range(0, total_rows, chunk_size),
                                            desc="Preparing Parquet chunks",
                                            unit="rows")):
                chunk = df.iloc[start:start+chunk_size]
                tqdm.write(f"Chunk {i+1}: shape={chunk.shape}")

            # --- Build PyArrow table ---
            import pyarrow as pa
            import pyarrow.parquet as pq

            table = pa.Table.from_pandas(df)
            meta_bytes = json.dumps({"metadata": metadata, "summary": summary_info}, ensure_ascii=False).encode("utf-8")
            table = table.replace_schema_metadata({**(table.schema.metadata or {}), b"indexly_meta": meta_bytes})

            # --- Write table ---
            pq.write_table(table, export_path, compression="snappy" if compress else None)
            console.print(f"[green]✅ Parquet export complete: {export_path} ({total_rows} rows)[/green]")



    else:
        raise ValueError(f"Unsupported export format: {export_format}")







