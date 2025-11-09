# analyze_utils.py
import os
import json
import gzip
import yaml
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from rich.console import Console
from rich.table import Table
from .csv_analyzer import detect_delimiter
from .db_utils import _migrate_cleaned_data_schema, _get_db_connection
from .csv_analyzer import _json_safe
from datetime import datetime, date


from .db_utils import _get_db_connection


console = Console()


def validate_file_content(file_path: Path, file_type: str) -> bool:
    """
    Validate that a file's content matches its expected type.
    Supports CSV, JSON (.json/.json.gz), YAML (.yaml/.yml),
    SQLite (.db/.sqlite), and XML (.xml) files.
    Returns True if content looks valid, False otherwise.
    """
    import json
    import gzip
    import sqlite3
    import yaml
    import pandas as pd
    import xml.etree.ElementTree as ET
    from rich.console import Console

    console = Console()

    if not file_path.exists():
        console.print(f"[red]❌ File not found:[/red] {file_path}")
        return False

    # --- CSV / TSV style ---

    if file_type == "csv":
        from indexly.csv_analyzer import detect_delimiter  # local import
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
        
    # --- Parquet (.parquet) ---
    if file_type == "parquet" or file_path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(file_path, columns=None)  # just read schema & few rows
            df = table.to_pandas().head(5)  # preview first 5 rows
            if df.empty or df.shape[1] < 1:
                console.print(f"[red]❌ Parquet file appears empty or invalid.[/red]")
                return False
            return True
        except Exception as e:
            console.print(f"[red]❌ Invalid Parquet file:[/red] {e}")
            return False

    # --- Excel (.xlsx, .xls) ---
    if file_type in {"xlsx", "xls"} or file_path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            df = pd.read_excel(file_path, nrows=5, engine="openpyxl")
            if df.empty or df.shape[1] < 1:
                console.print(f"[red]❌ Excel file appears empty or invalid.[/red]")
                return False
            return True
        except Exception as e:
            console.print(f"[red]❌ Invalid Excel file:[/red] {e}")
            return False

    # --- JSON (.json or .json.gz) ---
    if file_type in {"json", "json_gz"} or file_path.suffixes[-2:] == [".json", ".gz"]:
        try:
            opener = gzip.open if str(file_path).endswith(".gz") else open
            with opener(file_path, "rt", encoding="utf-8") as f:
                json.load(f)
            return True
        except Exception as e:
            console.print(f"[red]❌ Invalid JSON structure:[/red] {e}")
            return False

    # --- YAML (.yaml or .yml) ---
    if file_type in {"yaml", "yml"} or file_path.suffix.lower() in {".yaml", ".yml"}:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            return True
        except Exception as e:
            console.print(f"[red]❌ Invalid YAML structure:[/red] {e}")
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

    # --- XML (.xml) ---
    if file_type == "xml" or file_path.suffix.lower() == ".xml":
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(file_path)
            root = tree.getroot()
            if not list(root):
                console.print(f"[red]❌ XML file contains no child elements.[/red]")
                return False
            return True
        except Exception as e:
            console.print(f"[red]❌ Invalid XML structure:[/red] {e}")
            return False



# ------------------------------------------------------
# 🧱 3. Unified Save Function
# ------------------------------------------------------
def save_analysis_result(
    file_path: str,
    file_type: str,
    summary=None,
    sample_data=None,
    metadata=None,
    row_count: int | None = None,
    col_count: int | None = None,
) -> None:
    """
    Save unified analysis results in JSON-safe format for CSV, JSON, SQLite, etc.
    Adds source_path tracking and honors '--no-persist' global flag.
    """
    import os
    import json
    import pandas as pd
    from rich.console import Console

    console = Console()

    # -------------------------------
    # 🧩 Global no-persist guard
    # -------------------------------
    import builtins
    no_persist_active = getattr(builtins, "__INDEXLY_NO_PERSIST__", False)
    if no_persist_active:
        file_name = os.path.basename(file_path)
        console.print(f"[yellow]⚙️ Persistence globally disabled (--no-persist active).[/yellow]")
        console.print(f"[dim]Skipped saving unified analysis result for {file_name} ({file_type})[/dim]")
        return

    # -------------------------------
    # 🧱 Standard persistence logic
    # -------------------------------
    try:
        conn = _get_db_connection()
        _migrate_cleaned_data_schema(conn)

        file_name = os.path.basename(file_path)
        source_path = os.path.abspath(file_path) if os.path.exists(file_path) else str(file_path)

        # Convert data to JSON-safe structures
        summary_json = (
            _json_safe(summary.to_dict(orient="index"))
            if isinstance(summary, pd.DataFrame)
            else _json_safe(summary or {})
        )
        sample_json = (
            _json_safe(sample_data.head(10).to_dict(orient="records"))
            if isinstance(sample_data, pd.DataFrame)
            else _json_safe(sample_data or [])
        )
        metadata_json = _json_safe(metadata or {})

        payload = {
            "file_name": file_name,
            "file_type": file_type,
            "source_path": source_path,  # ✅ Added
            "summary_json": json.dumps(summary_json, ensure_ascii=False, indent=2),
            "sample_json": json.dumps(sample_json, ensure_ascii=False, indent=2),
            "metadata_json": json.dumps(metadata_json, ensure_ascii=False, indent=2),
            "cleaned_data_json": json.dumps(
                _json_safe(sample_data if sample_data is not None else {}),
                ensure_ascii=False,
                indent=2,
            ),
            "raw_data_json": None,
            "cleaned_at": __import__("datetime").datetime.now().isoformat(),
            "row_count": row_count or 0,
            "col_count": col_count or 0,
            "data_json": json.dumps(
                {
                    "summary_statistics": summary_json,
                    "sample_data": sample_json,
                    "metadata": metadata_json,
                },
                ensure_ascii=False,
                indent=2,
            ),
        }

        conn.execute(
            """
            INSERT INTO cleaned_data (
                file_name, file_type, source_path, summary_json, sample_json,
                metadata_json, cleaned_at, row_count, col_count, data_json,
                cleaned_data_json, raw_data_json
            )
            VALUES (
                :file_name, :file_type, :source_path, :summary_json, :sample_json,
                :metadata_json, :cleaned_at, :row_count, :col_count, :data_json,
                :cleaned_data_json, :raw_data_json
            )
            ON CONFLICT(file_name)
            DO UPDATE SET
                file_type = excluded.file_type,
                source_path = excluded.source_path,
                summary_json = excluded.summary_json,
                sample_json = excluded.sample_json,
                metadata_json = excluded.metadata_json,
                cleaned_at = excluded.cleaned_at,
                row_count = excluded.row_count,
                col_count = excluded.col_count,
                data_json = excluded.data_json,
                cleaned_data_json = excluded.cleaned_data_json,
                raw_data_json = excluded.raw_data_json
            """,
            payload,
        )

        conn.commit()
        conn.close()

        console.print(f"[green]✔ Saved unified analysis result for {file_name} ({file_type})[/green]")
        console.print(f"[dim]↳ Source: {source_path}[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to save analysis result for {file_path}: {e}[/red]")



def load_cleaned_data(file_path: str = None, limit: int = 5):
    """
    Load previously saved analysis results from the cleaned_data table.

    Returns:
        - If file_path is provided: (exists: bool, record: dict)
            record includes 'df' key with pd.DataFrame from cleaned_data_json
        - If file_path is None: list of records (up to `limit`)
    """
    conn = _get_db_connection()
    cursor = conn.cursor()

    if file_path:
        file_name = os.path.basename(file_path)
        cursor.execute("SELECT * FROM cleaned_data WHERE file_name = ?", (file_name,))
    else:
        cursor.execute(
            "SELECT * FROM cleaned_data ORDER BY cleaned_at DESC LIMIT ?", (limit,)
        )

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return (False, {}) if file_path else []

    results = []
    for row in rows:
        record = dict(row)

        # Load cleaned_data_json into a DataFrame
        try:
            record["df"] = pd.DataFrame(
                json.loads(record.get("cleaned_data_json") or "[]")
            )
        except (json.JSONDecodeError, TypeError):
            record["df"] = pd.DataFrame()
            console.print(
                f"[yellow]⚠️ Invalid cleaned_data_json for {record.get('file_name')}[/yellow]"
            )

        # Load auxiliary JSON fields safely
        for key in [
            "summary_json",
            "sample_json",
            "metadata_json",
            "data_json",
            "raw_data_json",
        ]:
            try:
                record[key] = json.loads(record[key]) if record.get(key) else {}
            except (json.JSONDecodeError, TypeError):
                record[key] = {}

        results.append(record)

    if file_path:
        return True, results[0]  # single record with df
    return results  # list of records



def handle_show_summary(file_path: str):
    """
    Unified summary viewer for both CSV and JSON analysis results.
    Fetches from DB and prints summary tables accordingly.
    """

    file_name = os.path.basename(file_path)
    exists, record = load_cleaned_data(file_name)
    if not exists:
        console.print(f"[red]No saved summary found for:[/red] {file_name}")
        return

    console.rule(f"[bold green]Summary for {file_name}[/bold green]")

    console.print(f"[dim]Cleaned/Analyzed at:[/dim] {record['cleaned_at']}")
    console.print(
        f"[dim]Rows:[/dim] {record.get('row_count', '-')}, [dim]Columns:[/dim] {record.get('col_count', '-')}"
    )

    data_json = record["data_json"]
    summary_stats = data_json.get("summary_statistics") or {}
    metadata = data_json.get("metadata") or {}
    sample_data = data_json.get("sample_data") or []

    # ------------------------------
    # Show metadata
    # ------------------------------
    if metadata:
        console.print("\n[bold cyan]Metadata[/bold cyan]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Field")
        table.add_column("Value")
        for k, v in metadata.items():
            table.add_row(str(k), str(v))
        console.print(table)

    # ------------------------------
    # Show summary stats
    # ------------------------------
    if summary_stats:
        console.print("\n[bold cyan]Summary Statistics[/bold cyan]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Field")
        table.add_column("Statistic")
        table.add_column("Value")

        for k, v in summary_stats.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    table.add_row(str(k), str(sk), str(sv))
            else:
                table.add_row(str(k), "-", str(v))
        console.print(table)

    # ------------------------------
    # Show sample data
    # ------------------------------
    if sample_data:
        console.print("\n[bold cyan]Sample Data[/bold cyan]")
        if (
            isinstance(sample_data, list)
            and sample_data
            and isinstance(sample_data[0], dict)
        ):
            table = Table(show_header=True, header_style="bold magenta")
            for col in sample_data[0].keys():
                table.add_column(str(col))
            for row in sample_data[:10]:
                table.add_row(*[str(row.get(c, "")) for c in sample_data[0].keys()])
            console.print(table)
        else:
            console.print(sample_data)
