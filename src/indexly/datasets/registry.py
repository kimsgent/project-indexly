from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from indexly.path_utils import normalize_path

from .schema import DatasetRecord
from .storage import infer_column_types, sha256_file, write_parquet_artifact


def initialize_dataset_registry(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dataset_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_name TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            source_path TEXT UNIQUE,
            source_hash TEXT,
            row_count INTEGER,
            col_count INTEGER,
            cleaned_artifact_path TEXT,
            raw_artifact_path TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dataset_columns (
            dataset_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            column_name TEXT NOT NULL,
            inferred_type TEXT,
            ordinal INTEGER,
            PRIMARY KEY (dataset_id, version, column_name),
            FOREIGN KEY (dataset_id) REFERENCES dataset_registry(id)
                ON DELETE CASCADE
        );
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_dataset_registry_file_name
        ON dataset_registry(file_name);
        """)
    conn.commit()


def _row_to_record(row: sqlite3.Row | None) -> DatasetRecord | None:
    if row is None:
        return None
    metadata = {}
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return DatasetRecord(
        id=row["id"],
        dataset_name=row["dataset_name"],
        file_name=row["file_name"],
        source_path=row["source_path"],
        source_hash=row["source_hash"],
        row_count=row["row_count"],
        col_count=row["col_count"],
        cleaned_artifact_path=row["cleaned_artifact_path"],
        raw_artifact_path=row["raw_artifact_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=metadata,
    )


def get_dataset_by_name(
    conn: sqlite3.Connection, dataset_name: str
) -> DatasetRecord | None:
    try:
        row = conn.execute(
            "SELECT * FROM dataset_registry WHERE dataset_name = ?",
            (dataset_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return _row_to_record(row)


def get_dataset_by_file_name(
    conn: sqlite3.Connection, file_name: str
) -> DatasetRecord | None:
    try:
        row = conn.execute(
            "SELECT * FROM dataset_registry WHERE file_name = ?",
            (file_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return _row_to_record(row)


def get_dataset_by_source_path(
    conn: sqlite3.Connection, source_path: str
) -> DatasetRecord | None:
    normalized = normalize_path(source_path)
    try:
        row = conn.execute(
            "SELECT * FROM dataset_registry WHERE source_path = ?",
            (normalized,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return _row_to_record(row)


def get_columns(
    conn: sqlite3.Connection, dataset_id: int, version: str
) -> dict[str, str]:
    try:
        rows = conn.execute(
            """
            SELECT column_name, inferred_type
            FROM dataset_columns
            WHERE dataset_id = ? AND version = ?
            ORDER BY ordinal
            """,
            (dataset_id, version),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["column_name"]: row["inferred_type"] for row in rows}


def _replace_columns(
    conn: sqlite3.Connection,
    dataset_id: int,
    version: str,
    column_types: dict[str, str],
) -> None:
    conn.execute(
        "DELETE FROM dataset_columns WHERE dataset_id = ? AND version = ?",
        (dataset_id, version),
    )
    conn.executemany(
        """
        INSERT INTO dataset_columns(dataset_id, version, column_name, inferred_type, ordinal)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (dataset_id, version, column, dtype, ordinal)
            for ordinal, (column, dtype) in enumerate(column_types.items())
        ],
    )


def _candidate_dataset_name(file_name: str, existing_names: Iterable[str]) -> str:
    stem = Path(file_name).stem or file_name
    existing = set(existing_names)
    if stem not in existing:
        return stem
    if file_name not in existing:
        return file_name

    index = 2
    while f"{stem}-{index}" in existing:
        index += 1
    return f"{stem}-{index}"


def register_analysis_dataset(
    conn: sqlite3.Connection,
    file_path: str,
    file_type: str,
    cleaned_df: pd.DataFrame | None,
    raw_df: pd.DataFrame | None = None,
    metadata: dict | None = None,
) -> DatasetRecord | None:
    if file_type != "csv" or cleaned_df is None or cleaned_df.empty:
        return None

    initialize_dataset_registry(conn)

    source_path = (
        os.path.abspath(file_path) if os.path.exists(file_path) else str(file_path)
    )
    normalized_source = normalize_path(source_path)
    file_name = os.path.basename(str(file_path))
    source_hash = sha256_file(source_path)
    row_count = len(cleaned_df)
    col_count = len(cleaned_df.columns)
    now = datetime.now().isoformat()

    existing = get_dataset_by_source_path(conn, source_path)
    if existing:
        dataset_name = existing.dataset_name
        created_at = existing.created_at or now
    else:
        names = [
            row["dataset_name"]
            for row in conn.execute(
                "SELECT dataset_name FROM dataset_registry"
            ).fetchall()
        ]
        dataset_name = _candidate_dataset_name(file_name, names)
        created_at = now

    cleaned_artifact_path = write_parquet_artifact(
        cleaned_df, source_path, "cleaned", source_hash
    )
    raw_artifact_path = write_parquet_artifact(raw_df, source_path, "raw", source_hash)

    payload = {
        "dataset_name": dataset_name,
        "file_name": file_name,
        "source_path": normalized_source,
        "source_hash": source_hash,
        "row_count": row_count,
        "col_count": col_count,
        "cleaned_artifact_path": cleaned_artifact_path,
        "raw_artifact_path": raw_artifact_path,
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
        "created_at": created_at,
        "updated_at": now,
    }
    conn.execute(
        """
        INSERT INTO dataset_registry (
            dataset_name, file_name, source_path, source_hash, row_count, col_count,
            cleaned_artifact_path, raw_artifact_path, metadata_json, created_at, updated_at
        )
        VALUES (
            :dataset_name, :file_name, :source_path, :source_hash, :row_count, :col_count,
            :cleaned_artifact_path, :raw_artifact_path, :metadata_json, :created_at, :updated_at
        )
        ON CONFLICT(source_path)
        DO UPDATE SET
            file_name = excluded.file_name,
            source_hash = excluded.source_hash,
            row_count = excluded.row_count,
            col_count = excluded.col_count,
            cleaned_artifact_path = excluded.cleaned_artifact_path,
            raw_artifact_path = excluded.raw_artifact_path,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        payload,
    )

    record = get_dataset_by_source_path(conn, source_path)
    if record and record.id is not None:
        _replace_columns(conn, record.id, "cleaned", infer_column_types(cleaned_df))
        if raw_df is not None and not raw_df.empty:
            _replace_columns(conn, record.id, "raw", infer_column_types(raw_df))
    conn.commit()
    return record
