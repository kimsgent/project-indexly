import hashlib
from pathlib import Path

BUF_SIZE = 1024 * 1024  # 1MB


def sha256(path: Path) -> str:
    """Return the SHA-256 hex digest for callers that need a stable file hash."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(BUF_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def files_identical(a: Path, b: Path) -> bool:
    """
    Return True when two files have identical bytes.

    This avoids hashing both files in full. After a size check, it compares
    chunks directly and exits on the first difference, which is faster for
    large files that differ early and equivalent for equality checks.
    """
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            chunk_a = fa.read(BUF_SIZE)
            chunk_b = fb.read(BUF_SIZE)
            if chunk_a != chunk_b:
                return False
            if not chunk_a:
                return True
