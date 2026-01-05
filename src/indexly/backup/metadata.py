from pathlib import Path
import os
import stat
import json

def collect_metadata(path: Path) -> dict:
    st = path.lstat()
    return {
        "mode": stat.S_IMODE(st.st_mode),
        "is_symlink": path.is_symlink(),
        "mtime": st.st_mtime,
        "atime": st.st_atime,
    }

def serialize_metadata(root: Path) -> dict:
    meta = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        meta[rel] = collect_metadata(p)
    return meta
