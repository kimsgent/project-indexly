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

    """
    Detects CSV delimiter using regex scoring and csv.Sniffer fallback.
    Returns None if no plausible delimiter found.
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        sample = f.read(4096)

    # Step 1: Regex scoring
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

    # Step 2: CSV Sniffer check
    try:
        sniffer_delim = csv.Sniffer().sniff(sample).delimiter
    except csv.Error:
        sniffer_delim = None

    # Step 3: Decide
    delimiter = best_delim or sniffer_delim
    if not delimiter:
        print("❌ Could not detect a valid CSV delimiter.")
        return None

    print(f"📄 Detected delimiter (regex): '{delimiter}'")
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
):
    """
    Export analysis results to text, markdown, or JSON formats.
    Supports memory-efficient chunked JSON export with progress bar for large datasets.
    Performs a small cleaning pass on text summary statistics before JSON export,
    with tqdm progress visible to the user.
    """

    # --- Normalize export path ---
    if not export_path or str(export_path).strip() == "":
        base_name = "analysis"
        if source_file:
            base_name = os.path.splitext(os.path.basename(source_file))[0]
        export_path = f"{base_name}.{export_format}"

    if os.path.isdir(export_path):
        filename = f"analysis.{export_format}"
        export_path = os.path.join(export_path, filename)

    export_path = str(export_path)
    os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)

    # --- Case-insensitive cleanup (avoid conflicts like test.JSON vs test.json) ---
    dir_name = os.path.dirname(export_path) or "."
    base_name = os.path.basename(export_path).lower()
    try:
        for f in os.listdir(dir_name):
            if f.lower() == base_name and f != os.path.basename(export_path):
                os.remove(os.path.join(dir_name, f))
    except Exception:
        # best-effort only
        pass

    # Helper: clean the textual summary block (returns cleaned string)
    def _clean_summary_text(text: str) -> str:
        if not text or not isinstance(text, str):
            return text or ""

        lines = text.splitlines()

        cleaned = []
        # Show progress for potentially large summary blocks
        for line in tqdm(lines, desc="Cleaning summary_statistics", unit="lines"):
            s = line.strip()

            # Skip long border lines entirely (those that are only +- and = characters)
            if re.fullmatch(r"^[\+\-\=\| ]+$", s):
                continue

            # Convert scientific notation like 1.000e+10 or 6.744e+09 to integer when obvious:
            # - pattern: digits with optional decimal followed by e+NN
            def _sci_to_full(match):
                token = match.group(0)
                try:
                    # If it's close to integer, cast to int
                    val = float(token)
                    if abs(val) >= 1e6 and float(val).is_integer():
                        return str(int(val))
                    # For large floats that are not integer, format without exponent with reasonable precision
                    return ("{:.6f}".format(val)).rstrip("0").rstrip(".")
                except Exception:
                    return token

            s = re.sub(r"\b\d+\.?\d*e[+\-]?\d+\b", _sci_to_full, s, flags=re.IGNORECASE)

            # Normalize sequences like "1.000e+10" that may include commas elsewhere
            # Also remove trailing commas used in tables
            s = s.replace(", ", ",")  # make consistent for further regexes
            # Restore spacing for readability
            s = re.sub(r",", ", ", s)

            # Collapse multiple spaces to single (but keep single spaces between numbers/labels)
            s = re.sub(r"\s{2,}", " ", s)

            cleaned.append(s)

        return "\n".join(cleaned)

    # --- Export formats ---
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

        # Prepare summary_statistics payload (apply cleaning if textual summary exists)
        if isinstance(results, dict) and "text_summary" in results:
            # results is already a dict with 'text_summary' etc.
            raw_summary = results.get("text_summary", "")
            cleaned_summary = _clean_summary_text(raw_summary)
            summary_data = {"text_summary": cleaned_summary}
        elif isinstance(results, str):
            # plain string summary — clean it as well
            summary_data = {"text_summary": _clean_summary_text(results)}
        elif isinstance(results, (pd.DataFrame, list, dict)):
            # If results is a DataFrame or structured, convert to JSON-safe directly
            summary_data = results
        else:
            summary_data = {"text_summary": str(results)}

        # Write JSON top-level and stream sample_data in chunks
        with open(export_path, "w", encoding="utf-8") as f:
            f.write("{\n")
            f.write(f'"metadata": {json.dumps(metadata)},\n')
            f.write(
                f'"summary_statistics": {json.dumps(_json_safe(summary_data, preserve_numeric=True), ensure_ascii=False, allow_nan=False)},\n'
            )

            f.write('"sample_data": [\n')
            if df is not None and len(df) > 0:
                # split into chunks
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
                        row_json = json.dumps(row_dict, ensure_ascii=False, allow_nan=False)

                        last_chunk = i == total_chunks - 1
                        last_row = j == len(chunk) - 1
                        if not (last_chunk and last_row):
                            f.write(row_json + ",\n")
                        else:
                            f.write(row_json + "\n")

            f.write("]\n}\n")

    else:
        raise ValueError(f"Unsupported export format: {export_format}")



