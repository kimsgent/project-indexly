import tarfile
from pathlib import Path
import io
import os
import shutil
import subprocess
import tempfile

from .compress import ZSTD_INSTALL_HINT

try:
    import zstandard as zstd
except ImportError:
    zstd = None


def _is_within_directory(parent: Path, child: Path) -> bool:
    try:
        return os.path.commonpath([str(parent), str(child)]) == str(parent)
    except ValueError:
        return False


def _safe_extractall(tar: tarfile.TarFile, target: Path) -> None:
    resolved_target = target.resolve()
    for member in tar.getmembers():
        destination = (target / member.name).resolve(strict=False)
        if not _is_within_directory(resolved_target, destination):
            raise RuntimeError(f"Refusing to extract unsafe archive member: {member.name}")

        if member.issym() or member.islnk():
            link_destination = (destination.parent / member.linkname).resolve(strict=False)
            if not _is_within_directory(resolved_target, link_destination):
                raise RuntimeError(f"Refusing to extract unsafe archive link: {member.name}")

    try:
        tar.extractall(path=target, filter="data")
    except TypeError:
        tar.extractall(path=target)


def extract_archive(archive: Path, target: Path):
    """
    Extract tar archives to target.
    Supports: .tar, .tar.gz, .tar.bz2, .tar.xz, .tar.zst
    """
    suffixes = archive.suffixes  # list of suffixes like ['.tar', '.zst']
    
    # Handle .tar.zst separately
    if suffixes[-2:] == ['.tar', '.zst']:
        if zstd is not None:
            with open(archive, "rb") as f:
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(f) as reader:
                    # Wrap decompressed stream in BytesIO for tarfile
                    with tarfile.open(fileobj=io.BytesIO(reader.read()), mode="r:") as tar:
                        _safe_extractall(tar, target)
            return

        zstd_exe = shutil.which("zstd")
        if not zstd_exe:
            raise RuntimeError(
                f"Cannot extract {archive.name}: zstd support is unavailable. "
                f"Install the Python 'zstandard' package or the zstd CLI. {ZSTD_INSTALL_HINT}"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = Path(tmp_dir) / archive.with_suffix("").name
            with tar_path.open("wb") as out:
                subprocess.run([zstd_exe, "-dc", str(archive)], stdout=out, check=True)
            with tarfile.open(tar_path, mode="r:") as tar:
                _safe_extractall(tar, target)
        return

    # For standard tar formats
    mode = "r:*"
    with tarfile.open(archive, mode) as tar:
        _safe_extractall(tar, target)
