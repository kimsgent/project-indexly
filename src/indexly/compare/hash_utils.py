import hashlib
from pathlib import Path

BUF_SIZE = 1024 * 1024  # 1MB


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(BUF_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def files_identical(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    return sha256(a) == sha256(b)
