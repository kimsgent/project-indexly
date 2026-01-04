from pathlib import Path
import hashlib


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
