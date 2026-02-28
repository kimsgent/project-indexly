import json
import pandas as pd
from indexly.db_utils import _get_db_connection


def load_dataframe(file_name: str, use_cleaned: bool = True) -> pd.DataFrame:
    conn = _get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT raw_data_json, cleaned_data_json
        FROM cleaned_data
        WHERE file_name = ?
        """,
        (file_name,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(
            f"Dataset '{file_name}' not found.\n"
            f"Tip: Did you mean '{file_name}.csv'?\n"
            f"Run 'indexly analyze-csv {file_name}.csv' first if not indexed."
        )

    raw_json, cleaned_json = row
    data_json = cleaned_json if use_cleaned else raw_json

    if not data_json:
        version = "cleaned" if use_cleaned else "raw"
        raise ValueError(
            f"The {version} dataset for '{file_name}' is not available."
        )

    data = json.loads(data_json)
    return pd.DataFrame(data)
