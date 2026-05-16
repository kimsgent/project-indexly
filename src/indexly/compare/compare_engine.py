from collections.abc import Iterable
from pathlib import Path

from .file_compare import compare_files
from .folder_compare import compare_folders
from .constants import CompareTier
from .models import DiffLine, FileCompareResult, FolderCompareResult
from .resolver import resolve_paths


def _coerce_csv_set(value: str | Iterable[str] | None) -> set[str] | None:
    """Normalize comma-separated strings or existing iterables into lowercase sets."""
    if value is None:
        return None
    items: Iterable[str]
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    normalized = {item.strip().lower() for item in items if item and item.strip()}
    return normalized or None


def run_compare(
    path_a: str | Path,
    path_b: str | Path | None = None,
    *,
    threshold: float | None = None,
    extensions: str | Iterable[str] | None = None,
    ignore: str | Iterable[str] | None = None,
    ignore_file: str | Path | None = None,
    use_project_ignore: bool = True,
    full_diff: bool = False,
    context: int = 3,  # New argument for foldable diff lines
) -> tuple[FileCompareResult | FolderCompareResult, int]:

    a, b, _mode = resolve_paths(path_a, path_b)

    ext_set = _coerce_csv_set(extensions)
    ignore_set = _coerce_csv_set(ignore)

    # Folder comparison
    if a.is_dir() and b.is_dir():
        folder_result = compare_folders(
            a,
            b,
            threshold=threshold,
            extensions=ext_set,
            ignore=ignore_set,
            ignore_file=Path(ignore_file) if ignore_file else None,
            use_project_ignore=use_project_ignore,
            full_diff=full_diff,
            context=context,
        )
        has_differences = any(
            (
                folder_result.summary.similar,
                folder_result.summary.modified,
                folder_result.summary.missing_a,
                folder_result.summary.missing_b,
                folder_result.summary.identical != len(folder_result.files),
            )
        )
        exit_code = 1 if has_differences else 0
        return folder_result, exit_code

    # File comparison
    if a.is_file() and b.is_file():
        file_result = compare_files(
            a,
            b,
            threshold=threshold,
            full_diff=full_diff,
            context=context,
        )
        exit_code = 0 if file_result.identical else 1
        return file_result, exit_code

    return (
        FileCompareResult(
            path_a=a,
            path_b=b,
            tier=CompareTier.INCOMPATIBLE,
            identical=False,
            similarity=None,
            diffs=[
                DiffLine(
                    sign="!",
                    text=f"Cannot compare: {a} and {b} are different types",
                )
            ],
        ),
        2,
    )
