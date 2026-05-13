# ------------------------------
# src/indexly/backup/registry.py
# ------------------------------

from pathlib import Path
import json
import tempfile
import time

def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"backups": []}
    return json.loads(path.read_text(encoding="utf-8"))

def _normalize_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except Exception:
        return path.expanduser().absolute()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _assert_persistent_path(path: str, registry_root: Path):
    resolved_path = _normalize_path(Path(path))
    resolved_root = _normalize_path(registry_root)
    temp_root = _normalize_path(Path(tempfile.gettempdir()))

    # Backups tracked in the active registry root are always valid,
    # even when that root lives under OS temp paths in tests.
    if _is_within(resolved_path, resolved_root):
        return

    if _is_within(resolved_path, temp_root):
        raise ValueError(f"Refusing to register temporary path: {path}")

def register_backup(registry_path: Path, entry: dict):
    registry_root = registry_path.parent
    _assert_persistent_path(entry["archive"], registry_root)

    for link in entry.get("chain", []):
        _assert_persistent_path(link["archive"], registry_root)

    reg = load_registry(registry_path)
    entry["registered_at"] = time.time()
    reg["backups"].append(entry)
    registry_path.write_text(
        json.dumps(reg, indent=2),
        encoding="utf-8"
    )

def get_last_full_backup(registry: dict) -> dict | None:
    full_backups = [b for b in registry.get("backups", []) if b["type"] == "full"]
    if not full_backups:
        return None
    return max(full_backups, key=lambda b: b.get("registered_at", 0))


def save_registry(path: Path, registry: dict):
    path.write_text(
        json.dumps(registry, indent=2),
        encoding="utf-8"
    )
