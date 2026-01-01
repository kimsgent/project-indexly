import tarfile
from pathlib import Path
import io

try:
    import zstandard as zstd
except ImportError:
    zstd = None


def extract_archive(archive: Path, target: Path):
    """
    Extract tar archives to target.
    Supports: .tar, .tar.gz, .tar.bz2, .tar.xz, .tar.zst
    """
    suffixes = archive.suffixes  # list of suffixes like ['.tar', '.zst']
    
    # Handle .tar.zst separately
    if suffixes[-2:] == ['.tar', '.zst']:
        if zstd is None:
            raise RuntimeError(
                f"Cannot extract {archive.name}: 'zstandard' library is not installed"
            )
        with open(archive, "rb") as f:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(f) as reader:
                # Wrap decompressed stream in BytesIO for tarfile
                with tarfile.open(fileobj=io.BytesIO(reader.read()), mode="r:") as tar:
                    tar.extractall(path=target)
        return

    # For standard tar formats
    mode = "r:*"
    with tarfile.open(archive, mode) as tar:
        tar.extractall(target)
