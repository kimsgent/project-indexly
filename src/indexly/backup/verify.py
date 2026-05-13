from pathlib import Path
import hashlib


def checksum_path_for(archive: Path) -> Path:
    """Return the checksum path that matches the full archive filename."""
    return Path(str(archive) + ".sha256")


def legacy_checksum_path_for(archive: Path) -> Path:
    """Return the pre-2.1.2 checksum path for backward-compatible restores."""
    return archive.with_suffix(".sha256")


def find_checksum_file(archive: Path) -> Path:
    checksum = checksum_path_for(archive)
    if checksum.exists():
        return checksum
    return legacy_checksum_path_for(archive)


def write_checksum(archive: Path) -> Path:
    h = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    checksum = checksum_path_for(archive)
    checksum.write_text(h.hexdigest(), encoding="utf-8")
    return checksum


def verify_checksum(archive: Path, checksum_file: Path):
    if not checksum_file.exists():
        raise FileNotFoundError("Missing checksum.sha256")

    expected = checksum_file.read_text().strip().split()[0]

    h = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    actual = h.hexdigest()
    if actual != expected:
        raise ValueError("❌ Checksum verification failed")

    print("🔐 Checksum verified")
