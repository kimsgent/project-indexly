from pathlib import Path
import os
import stat
import json

def collect_metadata(path: Path) -> dict:
    st = path.lstat()
    is_symlink = path.is_symlink()
    meta = {
        "mode": stat.S_IMODE(st.st_mode),
        "is_symlink": is_symlink,
        "is_dir": path.is_dir() and not is_symlink,
        "mtime": st.st_mtime,
        "atime": st.st_atime,
    }
    if is_symlink:
        meta["symlink_target"] = os.readlink(path)
        meta["target_is_directory"] = path.is_dir()
    return meta

def serialize_metadata(root: Path) -> dict:
    meta = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        meta[rel] = collect_metadata(p)
    return meta
