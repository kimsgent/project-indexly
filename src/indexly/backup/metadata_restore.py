import os
import shutil
from pathlib import Path


def apply_metadata(meta: dict, root: Path):
    for rel, info in meta.items():
        path = root / rel

        symlink_target = info.get("symlink_target") or info.get("symlink")
        if symlink_target:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            path.symlink_to(symlink_target, target_is_directory=bool(info.get("target_is_directory")))
            continue

        if info.get("is_dir"):
            path.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            continue

        if "mode" in info:
            os.chmod(path, info["mode"])

        if "mtime" in info:
            os.utime(path, (info.get("atime", info["mtime"]), info["mtime"]))
