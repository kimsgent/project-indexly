from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from indexly.config import get_analysis_db_file
from indexly.path_utils import normalize_path


def analytical_store_dir() -> Path:
    """Return the artifact directory beside the legacy analysis database."""
    base = Path(get_analysis_db_file()).expanduser().parent
    path = base / "datasets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(file_path: str | os.PathLike[str]) -> str | None:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_path_for(source_path: str, version: str, source_hash: str | None) -> Path:
    source = Path(source_path)
    stem = source.stem or "dataset"
    normalized = normalize_path(source_path) or str(source_path)
    key = source_hash or hashlib.sha256(normalized.encode()).hexdigest()
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return analytical_store_dir() / f"{safe_stem}-{key[:16]}-{version}.parquet"


def write_parquet_artifact(
    df: Any,
    source_path: str,
    version: str,
    source_hash: str | None,
) -> str | None:
    if df is None or df.empty:
        return None

    try:
        artifact_path = artifact_path_for(source_path, version, source_hash)
        artifact_df = df.copy()
        artifact_df.attrs = {}
        artifact_df.to_parquet(artifact_path, index=False)
        return str(artifact_path)
    except Exception:
        return None


def read_artifact(path: str, columns: list[str] | None = None) -> Any:
    try:
        import pandas as pd

        return pd.read_parquet(path, columns=columns)
    except Exception as exc:
        raise ValueError(f"Failed to read dataset artifact '{path}': {exc}") from exc


def infer_column_types(df: Any) -> dict[str, str]:
    return {str(column): str(dtype) for column, dtype in df.dtypes.items()}
