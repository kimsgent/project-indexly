import os
from pathlib import Path


def apply_metadata(meta: dict, root: Path):
    for rel, info in meta.items():
        path = root / rel
        if not path.exists():
            continue

        if "mode" in info:
            os.chmod(path, info["mode"])

        if "mtime" in info:
            os.utime(path, (info["mtime"], info["mtime"]))

        if info.get("symlink"):
            if path.exists():
                path.unlink()
            path.symlink_to(info["symlink"])
