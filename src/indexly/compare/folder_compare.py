from pathlib import Path

from indexly.ignore.ignore_rules import IgnoreRules
from indexly.ignore_defaults.loader import load_ignore_rules

from .models import FolderCompareResult, FolderCompareSummary, FileCompareResult
from .file_compare import compare_files


def _load_rules(
    base: Path,
    ignore_file: Path | None,
    use_project_ignore: bool,
) -> IgnoreRules | None:
    """Load explicit or project ignore rules for one comparison root."""
    if ignore_file and ignore_file.exists():
        return load_ignore_rules(base, custom_ignore=ignore_file)
    if use_project_ignore:
        return load_ignore_rules(base)
    return None


def _is_similar(result: FileCompareResult, threshold: float | None) -> bool:
    if threshold is None or result.similarity is None:
        return False
    return result.similarity >= (1.0 - threshold)


def compare_folders(
    a: Path,
    b: Path,
    *,
    threshold: float | None = None,
    extensions: set[str] | None = None,
    ignore: set[str] | None = None,
    ignore_file: Path | None = None,
    use_project_ignore: bool = True,
    full_diff: bool = False,
    context: int = 3,
) -> FolderCompareResult:
    """Compare folders with extension filters, explicit ignores, and .indexlyignore."""
    summary = FolderCompareSummary()
    results: list[FileCompareResult] = []

    explicit_ignore = {i.lower() for i in (ignore or set())}
    rules = [
        rules
        for rules in (
            _load_rules(a, ignore_file, use_project_ignore),
            _load_rules(b, ignore_file, use_project_ignore),
        )
        if rules is not None
    ]

    # Collect files from both folders
    def collect_files(base: Path) -> dict[Path, Path]:
        files = {}
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(base)
            if any(ignore_rules.should_ignore(p, root=base) for ignore_rules in rules):
                continue
            rel_key = rel.as_posix().lower()
            if p.name.lower() in explicit_ignore:
                continue
            if rel_key in explicit_ignore:
                continue
            if any(part.lower() in explicit_ignore for part in rel.parts):
                continue
            if extensions and p.suffix.lower() not in extensions:
                continue
            files[rel] = p
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

        if pa is None or pb is None:
            continue

        result = compare_files(
            pa,
            pb,
            threshold=threshold,
            full_diff=full_diff,
            context=context,
        )
        results.append(result)

        if result.identical:
            summary.identical += 1
        elif _is_similar(result, threshold):
            summary.similar += 1
        else:
            summary.modified += 1

    return FolderCompareResult(
        path_a=a,
        path_b=b,
        summary=summary,
        files=results,
    )
