# Clean description + stat functions

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
from scipy.stats import iqr
from tabulate import tabulate
from datetime import datetime, date
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
    Handles irregular/mixed CSVs more reliably.
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        sample = f.read(4096)

    # --- Step 1: Regex-based scoring ---
    possible_delims = [",", ";", "\t", "|", ":", "~"]
    line_splits = [re.split(r"[\r\n]+", sample.strip())[:10]]  # first 10 lines
    freq_scores = {}

    for delim in possible_delims:
        counts = [line.count(delim) for line in line_splits[0] if line]
        if counts:
            avg = sum(counts) / len(counts)
            variance = sum((c - avg) ** 2 for c in counts) / len(counts)
            # Lower variance + higher avg = more consistent delimiter
            freq_scores[delim] = avg / (1 + variance)

    if freq_scores:
        best_delim = max(freq_scores, key=freq_scores.get)
    else:
        best_delim = None

    # --- Step 2: Validate with Sniffer ---
    try:
        sniffer_delim = csv.Sniffer().sniff(sample).delimiter
    except csv.Error:
        sniffer_delim = None

    # --- Step 3: Merge logic ---
    delimiter = best_delim or sniffer_delim or ","

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
            console.print("ℹ️ Using datetime-derived numeric columns for analysis...", style="bold cyan")

    if not numeric_cols:
        console.print("⚠️ No valid numeric or date columns available for analysis.", style="bold yellow")
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

        stats.append([
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
        ])

    headers = [
        "Column", "Count", "Nulls", "Mean", "Median", "Std Dev",
        "Sum", "Min", "Max", "Q1", "Q3", "IQR"
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
            return f"{val:,.3f}".rstrip('0').rstrip('.')
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
            lambda v: str(v)[:max_col_width - 1] + "…" if len(str(v)) > max_col_width else str(v)
        )

    # ---------------------------
    # 📋 Render table
    # ---------------------------
    table_output = tabulate(df_stats, headers="keys", tablefmt="grid", showindex=False)

    return df, df_stats, table_output


## JSON Export

def _json_safe(obj):
    """Recursively convert Pandas / NumPy / Timestamp / NaT / scalar types to native Python."""
    import pandas as pd
    import numpy as np
    from datetime import datetime, date

    if obj is None or obj is pd.NaT:
        return None
    if isinstance(obj, float) and np.isnan(obj):
        return None
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, np.datetime64):
        return pd.Timestamp(obj).isoformat()
    if isinstance(obj, (np.integer, np.int64, int)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, float)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return type(obj)(_json_safe(x) for x in obj)
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return str(obj)


def export_results(results, export_path=None, export_format="txt", df=None, source_file=None, chunk_size=10000):
    """
    Export analysis results to text, markdown, or JSON formats.
    Supports memory-efficient chunked JSON export with progress bar for large datasets.
    """
    if not export_path or export_path.strip() == "":
        base_name = "csv_analysis"
        if source_file:
            base_name = os.path.splitext(os.path.basename(source_file))[0]
        export_path = f"{base_name}.{export_format}"

    if os.path.isdir(export_path):
        filename = f"csv_analysis.{export_format}"
        export_path = os.path.join(export_path, filename)

    os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)

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

        # Open JSON file for streaming
        with open(export_path, "w", encoding="utf-8") as f:
            f.write('{\n')
            f.write(f'"metadata": {json.dumps(metadata)},\n')

            # Write summary statistics if available
            if isinstance(results, pd.DataFrame):
                summary_data = results.to_dict(orient="records")
            else:
                summary_data = {"text_summary": results}
            f.write(f'"summary_statistics": {json.dumps(_json_safe(summary_data), ensure_ascii=False)},\n')

            # Stream sample_data or full data row by row
            f.write('"sample_data": [\n')
            if df is not None and len(df) > 0:
                total_chunks = math.ceil(len(df) / chunk_size)
                for i, chunk in enumerate(np.array_split(df, total_chunks)):
                    for j, row in enumerate(tqdm(chunk.itertuples(index=False), desc=f"Exporting chunk {i+1}/{total_chunks}", unit="rows")):
                        row_dict = _json_safe(row._asdict())
                        row_json = json.dumps(row_dict, ensure_ascii=False)
                        # Determine if comma is needed
                        last_chunk = (i == total_chunks - 1)
                        last_row = (j == len(chunk) - 1)
                        if not (last_chunk and last_row):
                            row_json += ',\n'
                        else:
                            row_json += '\n'
                        f.write(row_json)
            f.write(']\n')  # close sample_data array
            f.write('}\n')  # close top-level JSON object

    else:
        raise ValueError(f"Unsupported export format: {export_format}")

    print(f"✅ Exported to: {export_path}")


