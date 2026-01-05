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
    lines = difflib.unified_diff(
        text_a.splitlines(),
        text_b.splitlines(),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )

    diffs = []
    for line in lines:
        if line.startswith(("+++", "---", "@@")):
            continue
        diffs.append(DiffLine(sign=line[:1], text=line[1:].rstrip()))
    return diffs
