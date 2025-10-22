# Clean description + stat functions

import os
import sys
import csv
import importlib.util
import subprocess
import argparse
import importlib.util
import subprocess
import pandas as pd
import numpy as np
from pathlib import Path
from tabulate import tabulate
from scipy.stats import iqr
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
    if from_df:
        df = file_or_df.copy()
    else:
        file_path = Path(file_or_df)
        if not file_path.exists():
            print(f"[!] File not found: {file_or_df}")
            return None, None, None

        delimiter = detect_delimiter(file_path)
        try:
            df = pd.read_csv(file_path, delimiter=delimiter, encoding="utf-8")
        except Exception as e:
            print(f"[!] Failed to read CSV: {e}")
            return None, None, None

    if df.empty:
        print("[!] No data to analyze.")
        return None, None, None

    # Convert numeric columns safely
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    # --- Enhanced numeric column detection including datetime-derived timestamps ---
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    console = Console()
    # If no numeric columns, check datetime-derived timestamps
    if not numeric_cols:
        datetime_numeric_cols = [c for c in df.columns if c.endswith("_timestamp")]
        if datetime_numeric_cols:
            numeric_cols = datetime_numeric_cols
            console.print(
                "ℹ️ Using datetime-derived numeric columns for analysis...",
                style="bold cyan"
            )

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
            round(values.mean(), 3),
            round(values.median(), 3),
            round(values.std(), 3),
            round(values.sum(), 3),
            round(values.min(), 3),
            round(values.max(), 3),
            round(q1, 3),
            round(q3, 3),
            round(col_iqr, 3),
        ])

    headers = [
        "Column", "Count", "Nulls", "Mean", "Median", "Std Dev",
        "Sum", "Min", "Max", "Q1", "Q3", "IQR"
    ]
    df_stats = pd.DataFrame(stats, columns=headers)
    table_output = tabulate(df_stats, headers="keys", tablefmt="grid", showindex=False)

    return df, df_stats, table_output


def export_results(results, export_path, export_format):
    with open(export_path, 'w', encoding='utf-8') as f:
        if export_format == 'md':
            f.write(results.replace('+', '|'))
        else:
            f.write(results)
    print(f"[+] Exported to: {export_path}")
