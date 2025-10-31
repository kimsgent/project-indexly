# analyze_utils.py
import json
import sqlite3
import pandas as pd
from pathlib import Path
from rich.console import Console
from .csv_analyzer import detect_delimiter

console = Console()


def validate_file_content(file_path: Path, file_type: str) -> bool:
    """
    Validate that a file's content matches its expected type.
    Returns True if content looks valid, False otherwise.
    """

    if not file_path.exists():
        console.print(f"[red]❌ File not found:[/red] {file_path}")
        return False

    # --- CSV / TSV style ---
    if file_type == "csv":
        delimiter = detect_delimiter(file_path)
        if not delimiter:
            console.print(f"[red]❌ No valid CSV delimiter detected.[/red]")
            return False
        try:
            df = pd.read_csv(file_path, sep=delimiter, nrows=5, encoding="utf-8")
            if df.shape[1] < 2 and len("".join(df.columns)) < 3:
                console.print(f"[red]❌ File does not contain valid tabular CSV content.[/red]")
                return False
            return True
        except Exception as e:
            console.print(f"[red]❌ Failed to parse as CSV:[/red] {e}")
            return False

    # --- JSON ---
    if file_type == "json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
            return True
        except Exception as e:
            console.print(f"[red]❌ Invalid JSON structure:[/red] {e}")
            return False

    # --- SQLite / DB ---
    if file_type in {"sqlite", "db"}:
        try:
            with sqlite3.connect(file_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master LIMIT 1;")
            return True
        except Exception as e:
            console.print(f"[red]❌ Not a valid SQLite database:[/red] {e}")
            return False

    console.print(f"[yellow]⚠️ Unknown or unsupported file type: {file_type}[/yellow]")
    return False
