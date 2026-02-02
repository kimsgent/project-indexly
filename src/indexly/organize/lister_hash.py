import hashlib
from pathlib import Path
from rich.console import Console

console = Console()


def hash_file(path: Path, algo: str = "sha256") -> str | None:
    """
    Return the hash of a file using the specified algorithm.
    Returns None if the file cannot be read.
    """
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, FileNotFoundError) as e:
        console.print(f"⚠️ Cannot hash file (skipped): {path} — {e}", style="yellow")
        return None
