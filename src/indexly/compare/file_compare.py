from pathlib import Path
from collections import deque
from itertools import zip_longest

from .constants import CompareTier
from .models import DiffLine, FileCompareResult
from .hash_utils import files_identical
from .extract_adapter import extract_text
from .similarity import similarity_ratio, unified_diff

DEFAULT_MAX_TEXT_COMPARE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_LARGE_TEXT_CHANGES = 50


def compare_files(
    a: Path,
    b: Path,
    *,
    threshold: float | None = None,
    full_diff: bool = False,
    context: int = 3,
    max_text_compare_bytes: int = DEFAULT_MAX_TEXT_COMPARE_BYTES,
    max_large_text_changes: int = DEFAULT_MAX_LARGE_TEXT_CHANGES,
) -> FileCompareResult:
    """Compare two files and return a structured comparison result."""
    try:
        # Detect file type first
        tier = _detect_tier_for_compare(a) or CompareTier.BINARY

        # Exact binary check first
        if files_identical(a, b):
            return FileCompareResult(
                path_a=a,
                path_b=b,
                tier=tier,
                identical=True,
            )

        # For binary files, no text comparison
        if tier == CompareTier.BINARY:
            return FileCompareResult(
                path_a=a,
                path_b=b,
                tier=tier,
                identical=False,
            )

        if not full_diff and tier == CompareTier.TEXT:
            large_text_warning = _large_text_warning(a, b, max_text_compare_bytes)
            if large_text_warning:
                diffs, preview_warning = _large_text_line_preview(
                    a,
                    b,
                    context=context,
                    max_changes=max_large_text_changes,
                    scan_all=False,
                )
                return FileCompareResult(
                    path_a=a,
                    path_b=b,
                    tier=tier,
                    identical=False,
                    diffs=diffs,
                    comparison_warning=f"{large_text_warning} {preview_warning}",
                )
        elif full_diff and tier == CompareTier.TEXT:
            large_text_warning = _large_text_warning(a, b, max_text_compare_bytes)
            if large_text_warning:
                diffs, preview_warning = _large_text_line_preview(
                    a,
                    b,
                    context=context,
                    max_changes=max_large_text_changes,
                    scan_all=True,
                )
                return FileCompareResult(
                    path_a=a,
                    path_b=b,
                    tier=tier,
                    identical=False,
                    diffs=diffs,
                    comparison_warning=f"{large_text_warning} {preview_warning}",
                )

        # Extract text for comparison
        extracted_a = extract_text(a)
        extracted_b = extract_text(b)
        extraction_errors = [
            error
            for error in (extracted_a.error, extracted_b.error)
            if error
        ]
        if extraction_errors:
            return FileCompareResult(
                path_a=a,
                path_b=b,
                tier=tier,
                identical=False,
                diffs=[
                    DiffLine(sign="!", text=f"Extraction failed: {error}")
                    for error in extraction_errors
                ],
                extraction_error="; ".join(extraction_errors),
            )

        text_a = extracted_a.text
        text_b = extracted_b.text
        if not full_diff:
            large_text_warning = _large_extracted_text_warning(
                text_a,
                text_b,
                max_text_compare_bytes,
            )
            if large_text_warning:
                return FileCompareResult(
                    path_a=a,
                    path_b=b,
                    tier=tier,
                    identical=False,
                    diffs=[DiffLine(sign="!", text=large_text_warning)],
                    comparison_warning=large_text_warning,
                )

        similarity = similarity_ratio(text_a, text_b)

        # Threshold is a tolerance: 0.0 requires exact text, 1.0 accepts any text.
        if threshold is not None and similarity >= (1.0 - threshold):
            return FileCompareResult(
                path_a=a,
                path_b=b,
                tier=tier,
                identical=False,
                similarity=similarity,
            )

        # Compute diffs if files are not identical or within the supplied tolerance.
        diffs = unified_diff(text_a, text_b, a.name, b.name)

        return FileCompareResult(
            path_a=a,
            path_b=b,
            tier=tier,
            identical=False,
            similarity=similarity,
            diffs=diffs,
        )

    except Exception as e:
        # Return error info safely; tier is always set.
        return FileCompareResult(
            path_a=a,
            path_b=b,
            tier=CompareTier.BINARY,
            identical=False,
            diffs=[DiffLine(sign="!", text=f"Error: {e}")],
            extraction_error=str(e),
        )


def _detect_tier_for_compare(path: Path) -> CompareTier:
    from .detector import detect_tier
    return detect_tier(path)


def _large_text_warning(a: Path, b: Path, max_bytes: int) -> str | None:
    size_a = a.stat().st_size
    size_b = b.stat().st_size
    if max(size_a, size_b) <= max_bytes:
        return None
    return _format_large_text_warning(size_a, size_b, max_bytes)


def _large_extracted_text_warning(
    text_a: str,
    text_b: str,
    max_bytes: int,
) -> str | None:
    size_a = len(text_a.encode("utf-8"))
    size_b = len(text_b.encode("utf-8"))
    if max(size_a, size_b) <= max_bytes:
        return None
    return _format_large_text_warning(size_a, size_b, max_bytes)


def _format_large_text_warning(size_a: int, size_b: int, max_bytes: int) -> str:
    return (
        "Large text comparison switched to line preview to keep the CLI responsive "
        f"(A: {_format_bytes(size_a)}, B: {_format_bytes(size_b)}, "
        f"limit: {_format_bytes(max_bytes)}). Exact byte identity was checked "
        "first and the files are different. Similarity scoring is skipped for "
        "large text files. Use --context to control preview context; use "
        "--full-diff to scan the whole file line-by-line while keeping output "
        "bounded."
    )


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _large_text_line_preview(
    a: Path,
    b: Path,
    *,
    context: int,
    max_changes: int,
    scan_all: bool,
) -> tuple[list[DiffLine], str]:
    """Stream large text files and return a bounded line-level diff preview."""
    context = max(context, 0)
    max_changes = max(max_changes, 1)
    diffs: list[DiffLine] = []
    before: deque[tuple[int, str]] = deque(maxlen=context)
    trailing = 0
    in_hunk = False
    changed_lines = 0
    captured_changes = 0
    omitted_changes = 0
    lines_seen = 0

    with a.open("r", encoding="utf-8", errors="ignore") as left, b.open(
        "r",
        encoding="utf-8",
        errors="ignore",
    ) as right:
        for line_no, (line_a, line_b) in enumerate(
            zip_longest(left, right),
            start=1,
        ):
            lines_seen = line_no
            text_a = _strip_newline(line_a) if line_a is not None else None
            text_b = _strip_newline(line_b) if line_b is not None else None

            if text_a == text_b:
                if in_hunk and trailing > 0 and text_a is not None:
                    diffs.append(DiffLine(sign=" ", text=text_a))
                    trailing -= 1
                    if trailing == 0:
                        in_hunk = False
                        before.clear()
                elif not in_hunk and text_a is not None:
                    before.append((line_no, text_a))
                continue

            changed_lines += 1
            if captured_changes >= max_changes:
                omitted_changes += 1
                if not scan_all:
                    break
                continue

            if not in_hunk:
                diffs.append(DiffLine(sign="!", text=f"@@ line {line_no} @@"))
                for _context_line_no, context_text in before:
                    diffs.append(DiffLine(sign=" ", text=context_text))
                before.clear()
                in_hunk = True

            if text_a is not None:
                diffs.append(DiffLine(sign="-", text=text_a))
            if text_b is not None:
                diffs.append(DiffLine(sign="+", text=text_b))
            trailing = context
            captured_changes += 1

    if omitted_changes:
        diffs.append(
            DiffLine(
                sign="!",
                text=(
                    f"Preview limited to {captured_changes} changed line(s); "
                    f"{omitted_changes} additional changed line(s) were "
                    f"{'counted' if scan_all else 'not scanned'}."
                ),
            )
        )

    scan_text = "Full line scan completed" if scan_all else "Line preview completed"
    warning = (
        f"{scan_text}: {changed_lines} changed line(s)"
        f"{' found' if scan_all else ' previewed'} across {lines_seen} scanned line(s)."
    )
    return diffs or [DiffLine(sign="!", text=warning)], warning


def _strip_newline(line: str) -> str:
    return line.rstrip("\r\n")
