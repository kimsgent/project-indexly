import difflib
from typing import Iterable
from .models import DiffLine


def similarity_ratio(text_a: str, text_b: str) -> float:
    return difflib.SequenceMatcher(None, text_a, text_b).ratio()


def unified_diff(
    text_a: str,
    text_b: str,
    fromfile: str = "A",
    tofile: str = "B",
) -> list[DiffLine]:
    """Return structured unified diff lines without dropping real content lines."""
    lines = difflib.unified_diff(
        text_a.splitlines(),
        text_b.splitlines(),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )

    diffs = []
    for line in lines:
        if line.startswith(("--- ", "+++ ", "@@ ")):
            continue
        diffs.append(DiffLine(sign=line[:1], text=line[1:]))
    if text_a and not text_a.endswith(("\n", "\r")):
        diffs.append(DiffLine(sign="\\", text="No newline at end of file in A"))
    if text_b and not text_b.endswith(("\n", "\r")):
        diffs.append(DiffLine(sign="\\", text="No newline at end of file in B"))
    return diffs
