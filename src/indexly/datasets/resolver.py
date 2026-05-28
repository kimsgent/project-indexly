from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from indexly.csv_analyzer import detect_delimiter
from indexly.db_utils import _get_db_connection
from indexly.path_utils import normalize_path

from .registry import (
    get_columns,
    get_dataset_by_file_name,
    get_dataset_by_name,
    get_dataset_by_source_path,
)
from .schema import DatasetRecord, DatasetResolutionError, ResolvedDataset
from .storage import read_artifact


def resolve_dataset(
    identifier: str,
    *,
    use_cleaned: bool = True,
    use_raw: bool = False,
    columns: list[str] | None = None,
) -> ResolvedDataset:
    """
    Resolve an inference dataset by catalog name, legacy cleaned_data file_name,
    source_path, or an existing CSV path loaded ephemerally.
    """
    columns = _dedupe(columns)
    version = "raw" if use_raw else "cleaned"

    conn = _get_db_connection()
    try:
        record = get_dataset_by_name(conn, identifier)
        if record:
            df = _load_catalog_record(conn, record, version, columns)
            return ResolvedDataset(identifier, "dataset_registry.name", df, record)

        file_name = os.path.basename(identifier)
        legacy_row = conn.execute(
            "SELECT * FROM cleaned_data WHERE file_name = ?",
            (identifier,),
        ).fetchone()
        if legacy_row:
            df = _load_legacy_row(legacy_row, use_cleaned=use_cleaned, use_raw=use_raw)
            return ResolvedDataset(identifier, "cleaned_data.file_name", df, None)

        record = get_dataset_by_file_name(conn, file_name)
        if record:
            df = _load_catalog_record(conn, record, version, columns)
            return ResolvedDataset(identifier, "dataset_registry.file_name", df, record)

        source_record = get_dataset_by_source_path(conn, identifier)
        if source_record:
            df = _load_catalog_record(conn, source_record, version, columns)
            return ResolvedDataset(
                identifier, "dataset_registry.source_path", df, source_record
            )

        legacy_source = _find_legacy_source_row(conn, identifier)
        if legacy_source:
            df = _load_legacy_row(
                legacy_source,
                use_cleaned=use_cleaned,
                use_raw=use_raw,
            )
            return ResolvedDataset(identifier, "cleaned_data.source_path", df, None)

    finally:
        conn.close()

    path = Path(identifier).expanduser()
    if path.exists() and path.is_file():
        if path.suffix.lower() == ".csv":
            df = _load_ephemeral_csv(path, columns)
            return ResolvedDataset(identifier, "ephemeral.csv", df, None)
        raise DatasetResolutionError(
            f"Dataset '{identifier}' exists but is not a CSV file. "
            "Run 'indexly analyze-csv <path>' for CSV inputs before inference."
        )

    raise DatasetResolutionError(_not_found_message(identifier))


def _load_catalog_record(
    conn,
    record: DatasetRecord,
    version: str,
    columns: list[str] | None,
) -> pd.DataFrame:
    artifact_path = (
        record.raw_artifact_path if version == "raw" else record.cleaned_artifact_path
    )
    if artifact_path:
        if columns and record.id is not None:
            available = get_columns(conn, record.id, version)
            missing = [column for column in columns if column not in available]
            if missing:
                raise DatasetResolutionError(
                    f"Dataset '{record.dataset_name}' is missing column(s): "
                    f"{', '.join(missing)}."
                )
        return read_artifact(artifact_path, columns=columns)

    row = conn.execute(
        "SELECT * FROM cleaned_data WHERE file_name = ?",
        (record.file_name,),
    ).fetchone()
    if row:
        return _load_legacy_row(
            row,
            use_cleaned=(version == "cleaned"),
            use_raw=(version == "raw"),
        )

    raise DatasetResolutionError(
        f"Dataset '{record.dataset_name}' is registered, but no {version} artifact "
        "or legacy JSON payload is available."
    )


def _load_legacy_row(row, *, use_cleaned: bool, use_raw: bool) -> pd.DataFrame:
    raw_json = row["raw_data_json"]
    cleaned_json = row["cleaned_data_json"]
    data_json = raw_json if use_raw else cleaned_json if use_cleaned else raw_json

    if not data_json:
        version = "raw" if use_raw else "cleaned"
        raise DatasetResolutionError(
            f"The {version} dataset for '{row['file_name']}' is not available."
        )

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as exc:
        raise DatasetResolutionError(
            f"The stored dataset payload for '{row['file_name']}' is invalid JSON."
        ) from exc
    return pd.DataFrame(data)


def _find_legacy_source_row(conn, identifier: str):
    normalized = normalize_path(identifier)
    rows = conn.execute(
        "SELECT * FROM cleaned_data WHERE source_path IS NOT NULL"
    ).fetchall()
    for row in rows:
        if normalize_path(row["source_path"]) == normalized:
            return row
    return None


def _load_ephemeral_csv(path: Path, columns: list[str] | None) -> pd.DataFrame:
    delimiter = detect_delimiter(path)
    try:
        return pd.read_csv(path, sep=delimiter or ",", usecols=columns)
    except ValueError:
        return pd.read_csv(path, sep=delimiter or ",")


def _not_found_message(identifier: str) -> str:
    file_name = os.path.basename(identifier)
    examples = [
        f"indexly analyze-csv {identifier}",
        f"indexly infer-csv {file_name}",
    ]
    return (
        f"Dataset '{identifier}' was not found in dataset_registry, "
        "cleaned_data.file_name, or cleaned_data.source_path, and it is not an "
        "existing CSV path.\n"
        "Register it first with analyze-csv, or pass an existing CSV file path for "
        "ephemeral inference.\n"
        f"Examples: {examples[0]} ; {examples[1]}"
    )


def _dedupe(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return list(dict.fromkeys(value for value in values if value))
