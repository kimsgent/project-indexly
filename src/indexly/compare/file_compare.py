from pathlib import Path

from .constants import CompareTier
from .models import FileCompareResult
from .hash_utils import files_identical
from .extract_adapter import extract_text
from .similarity import similarity_ratio, unified_diff


def compare_files(
    a: Path,
    b: Path,
    *,
    threshold: float | None = None,
) -> FileCompareResult:
    """Compare two files and return a FileCompareResult."""
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

        # Extract text for comparison
        text_a = extract_text(a)
        text_b = extract_text(b)

        similarity = similarity_ratio(text_a, text_b)

        # Check threshold for “similar”
        if threshold is not None and similarity >= (1.0 - threshold):
            return FileCompareResult(
                path_a=a,
                path_b=b,
                tier=tier,
                identical=False,
                similarity=similarity,
            )

        # Compute diffs if files are not identical/similar
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
        # Return error info safely, tier is always set
        return FileCompareResult(
            path_a=a,
            path_b=b,
            tier=CompareTier.BINARY,
            identical=False,
            diffs=[type("Diff", (), {"sign": "!", "text": f"Error: {e}"})()],
        )


def _detect_tier_for_compare(path: Path) -> CompareTier:
    from .detector import detect_tier
    return detect_tier(path)
