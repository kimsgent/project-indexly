# src/indexly/backup/manifest.py

from pathlib import Path
import hashlib
import json

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def build_manifest(root_path: Path) -> dict:
    manifest = {}
    for p in root_path.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root_path).as_posix()
            manifest[rel] = {
                "hash": _hash_file(p),
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            }
    return manifest

def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))



def diff_manifests(previous: dict, current: dict, include_deletions: bool = False) -> tuple[dict, list]:
    """
    Compute incremental changes between previous and current manifest.

    Returns:
        - diff: dict of added/modified files
        - deleted: list of deleted files

    Notes:
        - Missing checksum fields are treated as changed.
        - Files removed from source are tracked in `deleted` if include_deletions=True.
    """
    diff = {}
    deleted = []

    # Detect new or modified files
    for f, meta in current.items():
        prev_meta = previous.get(f)
        if not prev_meta:
            # New file
            diff[f] = meta
        else:
            # Modified file if checksum differs
            prev_checksum = prev_meta.get("checksum")
            curr_checksum = meta.get("checksum")
            if prev_checksum != curr_checksum:
                diff[f] = meta

    # Detect deletions
    if include_deletions:
        deleted = [f for f in previous if f not in current]

    return diff, deleted


