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
from scipy.stats import iqr
from tabulate import tabulate


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
    """Detect CSV delimiter safely."""
    import csv
    with open(file_path, 'r', encoding='utf-8') as f:
        sample = f.read(2048)
        sniffer = csv.Sniffer()
        try:
            return sniffer.sniff(sample).delimiter
        except csv.Error:
            for delim in [';', ',', '\t', '|']:
                if delim in sample:
                    return delim
            return ','


def analyze_csv(file_or_df, from_df=False):
    """
    Analyze a CSV file or a provided DataFrame.
    - If from_df=True, file_or_df is treated as a DataFrame (already cleaned)
    - Otherwise, file_or_df is treated as a file path to read CSV
    Returns: df, df_stats, table_output
    """
    file_path = None  
    console = Console()

    if from_df:
        df = file_or_df.copy()
    else:
        # --- Resolve and validate file path ---
        try:
            file_path = Path(file_or_df).expanduser().resolve(strict=False)
        except Exception:
            print(f"[!] Invalid file path: {file_or_df}")
            return None, None, None

        # --- Handle missing file clearly ---
        if not file_path.exists():
            print(f"[!] File not found: {file_or_df}")
            # Try relative to current working directory as fallback
            alt_path = Path.cwd() / file_or_df
            if alt_path.exists():
                file_path = alt_path
                print(f"ℹ️ Using fallback path: {alt_path}")
            else:
                return None, None, None

        # --- Detect delimiter and read CSV safely ---
        try:
            delimiter = detect_delimiter(file_path)
            df = pd.read_csv(file_path, delimiter=delimiter, encoding="utf-8")
        except FileNotFoundError:
            print(f"[!] Could not locate file after fallback: {file_path}")
            return None, None, None
        except Exception as e:
            print(f"[!] Failed to read CSV: {e}")
            return None, None, None

    # --- Handle empty DataFrame case ---
    if df.empty:
        print("[!] No data to analyze.")
        return None, None, None

    # --- Convert numeric columns safely ---
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    # --- Enhanced numeric column detection including datetime-derived timestamps ---
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        datetime_numeric_cols = [c for c in df.columns if c.endswith("_timestamp")]
        if datetime_numeric_cols:
            numeric_cols = datetime_numeric_cols
            console.print("ℹ️ Using datetime-derived numeric columns for analysis...", style="bold cyan")

    if not numeric_cols:
        console.print("⚠️ No numeric or datetime-derived columns found.", style="bold yellow")
        return df, None, None

    numeric_df = df[numeric_cols]

    stats = []
    for col in numeric_df.columns:
        values = numeric_df[col].dropna()
        if values.empty:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
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

    # --- 👇 NEW: auto-fit table and compact large numbers ---
    def format_number(val):
        """Compact numeric representation."""
        if isinstance(val, (int, float, np.number)):
            if np.isnan(val):
                return "-"
            if abs(val) >= 1e6 or abs(val) < 1e-3:
                return f"{val:.3e}"
            return f"{val:,.3f}".rstrip('0').rstrip('.')
        return str(val)

    df_stats = df_stats.apply(lambda col: col.map(format_number))

    # Determine terminal width and adjust per-column max width
    term_width = shutil.get_terminal_size((120, 20)).columns
    max_width = term_width - 4
    col_count = len(df_stats.columns)
    max_col_width = max(8, int(max_width / col_count))

    for c in df_stats.columns:
        df_stats[c] = df_stats[c].apply(
            lambda v: v[:max_col_width - 1] + "…" if len(str(v)) > max_col_width else v
        )

    # Render the compact ASCII table
    table_output = tabulate(df_stats, headers="keys", tablefmt="grid", showindex=False)

    return df, df_stats, table_output


def export_results(results, export_path, export_format):
    with open(export_path, 'w', encoding='utf-8') as f:
        if export_format == 'md':
            f.write(results.replace('+', '|'))
        else:
            f.write(results)
    print(f"[+] Exported to: {export_path}")
