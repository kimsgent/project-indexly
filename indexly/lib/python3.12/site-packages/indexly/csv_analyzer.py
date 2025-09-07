# Clean description + stat functions

import os
import sys
import csv
import importlib.util
import subprocess
import argparse
from pathlib import Path
import importlib.util
import subprocess


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
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        sample = f.read(2048)
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(sample)
        return dialect.delimiter
    except csv.Error:
        return ','


def analyze_csv(file_path):
    if not Path(file_path).exists():
        print(f"[!] File not found: {file_path}")
        return None

    delimiter = detect_delimiter(file_path)

    try:
        df = pd.read_csv(file_path, delimiter=delimiter)
    except Exception as e:
        print(f"[!] Failed to read CSV: {e}")
        return None

    if df.empty:
        print("[!] CSV file is empty.")
        return None

    numeric_df = df.select_dtypes(include=[np.number])

    if numeric_df.empty:
        print("[!] No numeric columns found for analysis.")
        return None

    stats = []
    for col in numeric_df.columns:
        values = numeric_df[col].dropna()
        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        col_iqr = iqr(values) if iqr else (q3 - q1)

        stats.append([
            col,
            values.count(),
            values.isnull().sum(),
            round(values.mean(), 3),
            round(values.median(), 3),
            round(values.std(), 3),
            round(values.sum(), 3),
            round(values.min(), 3),
            round(values.max(), 3),
            round(col_iqr, 3)
        ])

    headers = ["Column", "Count", "Nulls", "Mean", "Median", "Std Dev", "Sum", "Min", "Max", "IQR"]
    return tabulate(stats, headers=headers, tablefmt="grid")


def export_results(results, export_path, export_format):
    with open(export_path, 'w', encoding='utf-8') as f:
        if export_format == 'md':
            f.write(results.replace('+', '|'))
        else:
            f.write(results)
    print(f"[+] Exported to: {export_path}")
