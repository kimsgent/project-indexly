from pathlib import Path

from .models import FolderCompareResult, FolderCompareSummary, FileCompareResult
from .file_compare import compare_files


def compare_folders(
    a: Path,
    b: Path,
    *,
    threshold: float | None = None,
    extensions: set[str] | None = None,
    ignore: set[str] | None = None,
) -> FolderCompareResult:
    """Compare two folders with optional filters for extensions and ignored names."""
    summary = FolderCompareSummary()
    results: list[FileCompareResult] = []

    ignore = {i.lower() for i in (ignore or set())}

    # Collect files from both folders
    def collect_files(base: Path) -> dict[Path, Path]:
        files = {}
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.name.lower() in ignore:
                continue
            if extensions and p.suffix.lower() not in extensions:
                continue
            files[p.relative_to(base)] = p
        return files

    files_a = collect_files(a)
    files_b = collect_files(b)

    all_keys = set(files_a) | set(files_b)

    for rel in sorted(all_keys):
        pa = files_a.get(rel)
        pb = files_b.get(rel)

        if pa and not pb:
            summary.missing_b += 1
            continue

        if pb and not pa:
            summary.missing_a += 1
            continue

        result = compare_files(pa, pb, threshold=threshold)
        results.append(result)

        if result.identical:
            summary.identical += 1
        elif result.similarity is not None:
            summary.similar += 1
        else:
            summary.modified += 1

    return FolderCompareResult(
        path_a=a,
        path_b=b,
        summary=summary,
        files=results,
    )
