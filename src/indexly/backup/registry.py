from pathlib import Path
import json
import time

def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"backups": []}
    return json.loads(path.read_text(encoding="utf-8"))

def register_backup(registry_path: Path, entry: dict):
    reg = load_registry(registry_path)
    entry["registered_at"] = time.time()
    reg["backups"].append(entry)
    registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")

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
