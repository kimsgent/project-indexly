import tarfile
import subprocess
from pathlib import Path

def detect_best_compression() -> str:
    try:
        subprocess.run(["zstd", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "zst"
    except Exception:
        return "gz"

def create_tar_zst(src_dir: Path, output_file: Path):
    tar_path = output_file.with_suffix(".tar")
    with tarfile.open(tar_path, "w") as tar:
        tar.add(src_dir, arcname=".")
    subprocess.run(["zstd", "-19", tar_path, "-o", output_file], check=True)
    tar_path.unlink()

def create_tar_gz(src_dir: Path, output_file: Path):
    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(src_dir, arcname=".")
