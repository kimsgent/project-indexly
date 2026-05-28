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
    required_columns: list[str] | None = None,
    ignore_hash: bool = False,
    materialize: bool = True,
) -> ResolvedDataset:
    """
    Resolve an inference dataset by catalog name, legacy cleaned_data file_name,
    source_path, or an existing CSV path loaded ephemerally.
    """
    columns = _dedupe(columns)
    required_columns = _dedupe(required_columns)
    version = "raw" if use_raw else "cleaned"
    path = Path(identifier).expanduser()

    conn = _get_db_connection()
    try:
        record = get_dataset_by_name(conn, identifier)
        if record:
            df, warnings, resolution, artifact_path, read_columns = (
                _load_catalog_record(
                    conn,
                    record,
                    version,
                    columns,
                    required_columns,
                    ignore_hash,
                    materialize,
                )
            )
            return ResolvedDataset(
                identifier,
                resolution,
                df,
                record,
                tuple(warnings),
                artifact_path=artifact_path,
                artifact_version=version if artifact_path else None,
                selected_columns=tuple(read_columns or ()),
            )

        file_name = os.path.basename(identifier)
        legacy_row = conn.execute(
            "SELECT * FROM cleaned_data WHERE file_name = ?",
            (identifier,),
        ).fetchone()
        if legacy_row:
            df = _load_legacy_row(legacy_row, use_cleaned=use_cleaned, use_raw=use_raw)
            df = _select_existing_columns(df, columns)
            return ResolvedDataset(identifier, _legacy_resolution(version), df, None)

        record = get_dataset_by_file_name(conn, file_name)
        if record:
            resolved = _try_load_catalog_or_existing_csv(
                conn,
                identifier=identifier,
                path=path,
                record=record,
                version=version,
                columns=columns,
                required_columns=required_columns,
                ignore_hash=ignore_hash,
                materialize=materialize,
            )
            if resolved:
                return resolved

        source_record = get_dataset_by_source_path(conn, identifier)
        if source_record:
            resolved = _try_load_catalog_or_existing_csv(
                conn,
                identifier=identifier,
                path=path,
                record=source_record,
                version=version,
                columns=columns,
                required_columns=required_columns,
                ignore_hash=ignore_hash,
                materialize=materialize,
            )
            if resolved:
                return resolved

        legacy_source = _find_legacy_source_row(conn, identifier)
        if legacy_source:
            df = _load_legacy_row(
                legacy_source,
                use_cleaned=use_cleaned,
                use_raw=use_raw,
            )
            df = _select_existing_columns(df, columns)
            return ResolvedDataset(identifier, _legacy_resolution(version), df, None)

    finally:
        conn.close()

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
    required_columns: list[str] | None,
    ignore_hash: bool,
    materialize: bool,
) -> tuple[pd.DataFrame | None, list[str], str, str | None, list[str] | None]:
    warnings = []
    artifact_path = (
        record.raw_artifact_path if version == "raw" else record.cleaned_artifact_path
    )
    if artifact_path:
        stale_warning = _freshness_warning(record)
        if stale_warning:
            if not ignore_hash:
                raise DatasetResolutionError(
                    f"{stale_warning}\n"
                    f"Run 'indexly analyze-csv {record.source_path or record.file_name}' "
                    "to refresh analytical artifacts, or pass --ignore-hash to warn "
                    "and continue with the existing artifact."
                )
            warnings.append(stale_warning)

        artifact_columns = _artifact_columns(conn, record, version)
        read_columns = _columns_for_dataset(
            available_columns=artifact_columns,
            requested_columns=columns,
            required_columns=required_columns,
            dataset_name=record.dataset_name,
        )
        return (
            read_artifact(artifact_path, columns=read_columns) if materialize else None,
            warnings,
            f"dataset_registry.{version}_artifact",
            artifact_path,
            read_columns,
        )

    if columns and record.id is not None:
        available = _artifact_columns(conn, record, version)
        if available:
            missing = [
                column
                for column in required_columns or []
                if column not in set(available)
            ]
            if missing:
                raise DatasetResolutionError(
                    f"Dataset '{record.dataset_name}' is missing required column(s): "
                    f"{', '.join(missing)}."
                )

    row = conn.execute(
        "SELECT * FROM cleaned_data WHERE file_name = ?",
        (record.file_name,),
    ).fetchone()
    if row:
        df = _load_legacy_row(
            row,
            use_cleaned=(version == "cleaned"),
            use_raw=(version == "raw"),
        )
        return (
            _select_existing_columns(df, columns),
            warnings,
            _legacy_resolution(version),
            None,
            columns,
        )

    raise DatasetResolutionError(
        f"Dataset '{record.dataset_name}' is registered, but no {version} artifact "
        "or legacy JSON payload is available."
    )


def _try_load_catalog_or_existing_csv(
    conn,
    *,
    identifier: str,
    path: Path,
    record: DatasetRecord,
    version: str,
    columns: list[str] | None,
    required_columns: list[str] | None,
    ignore_hash: bool,
    materialize: bool,
) -> ResolvedDataset | None:
    try:
        df, warnings, resolution, artifact_path, read_columns = _load_catalog_record(
            conn, record, version, columns, required_columns, ignore_hash, materialize
        )
        return ResolvedDataset(
            identifier,
            resolution,
            df,
            record,
            tuple(warnings),
            artifact_path=artifact_path,
            artifact_version=version if artifact_path else None,
            selected_columns=tuple(read_columns or ()),
        )
    except DatasetResolutionError as exc:
        if "no " not in str(exc) or "artifact or legacy JSON payload" not in str(exc):
            raise
        if not path.exists() or not path.is_file() or path.suffix.lower() != ".csv":
            raise
        df = _load_ephemeral_csv(path, columns)
        return ResolvedDataset(identifier, "ephemeral.csv", df, None)


def _legacy_resolution(version: str) -> str:
    if version == "raw":
        return "cleaned_data.raw_data_json"
    return "cleaned_data.cleaned_data_json"


def _artifact_columns(conn, record: DatasetRecord, version: str) -> list[str]:
    if record.id is None:
        return []
    return list(get_columns(conn, record.id, version).keys())


def _columns_for_dataset(
    *,
    available_columns: list[str],
    requested_columns: list[str] | None,
    required_columns: list[str] | None,
    dataset_name: str,
) -> list[str] | None:
    if not requested_columns:
        return None

    available = set(available_columns)
    missing_required = [
        column
        for column in required_columns or []
        if available_columns and column not in available
    ]
    if missing_required:
        raise DatasetResolutionError(
            f"Dataset '{dataset_name}' is missing required column(s): "
            f"{', '.join(missing_required)}."
        )

    if not available_columns:
        return requested_columns

    selected = [
        column
        for column in requested_columns
        if column in available or column in set(required_columns or [])
    ]
    return selected or None


def _select_existing_columns(
    df: pd.DataFrame, columns: list[str] | None
) -> pd.DataFrame:
    if not columns:
        return df
    selected = [column for column in columns if column in df.columns]
    return df[selected].copy() if selected else df


def _freshness_warning(record: DatasetRecord) -> str | None:
    from .storage import sha256_file

    if not record.source_path or not record.source_hash:
        return None

    current_hash = sha256_file(record.source_path)
    if current_hash is None or current_hash == record.source_hash:
        return None

    return (
        f"Analytical artifact for dataset '{record.dataset_name}' is stale: "
        "the source CSV hash has changed since the artifact was registered."
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
