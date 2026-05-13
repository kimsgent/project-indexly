import tarfile
import subprocess
import shutil
from pathlib import Path

ZSTD_INSTALL_HINT = (
    "Install zstd and retry. On Windows: winget install Facebook.Zstandard. "
    "On macOS: brew install zstd. "
    "On Debian/Ubuntu: sudo apt-get install zstd."
)

def detect_best_compression() -> str:
    zstd_exe = shutil.which("zstd")
    if not zstd_exe:
        return "gz"
    try:
        result = subprocess.run(
            [zstd_exe, "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return "gz"
    return "zst" if result.returncode == 0 else "gz"

def create_tar_zst(src_dir: Path, output_file: Path):
    zstd_exe = shutil.which("zstd")
    if not zstd_exe:
        raise RuntimeError(f"Cannot create {output_file.name}: zstd is not installed. {ZSTD_INSTALL_HINT}")

    tar_path = output_file.with_suffix(".tar")
    try:
        with tarfile.open(tar_path, "w") as tar:
            tar.add(src_dir, arcname=".")
        subprocess.run([zstd_exe, "-19", str(tar_path), "-o", str(output_file)], check=True)
    finally:
        tar_path.unlink(missing_ok=True)

def create_tar_gz(src_dir: Path, output_file: Path):
    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(src_dir, arcname=".")
