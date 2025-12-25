import tarfile
from pathlib import Path


def extract_archive(archive: Path, target: Path):
    mode = "r:*"
    with tarfile.open(archive, mode) as tar:
        tar.extractall(target)
