"""
📄 indexly/observers/config.py

Purpose:
  This module handles reading the JSON configuration and providing observer rules.

"""

import json
import os
from pathlib import Path

CONFIG_FILENAME = ".indexly.observers.json"


def get_config_path() -> Path:
    """Return full path to the observer config file in the user home directory."""
    home = Path.home()
    return home / CONFIG_FILENAME


def default_config() -> dict:
    """Return a default config template."""
    return {
        "watch": [
            {
                "path": str(Path.home() / "Documents/Indexly/Health"),
                "profile": "health",
                "identity": "patient_id",
                "fields": {
                    "address": {"type": "regex", "pattern": "Address:\\s*(.*)"},
                    "version": {
                        "type": "multi",
                        "patterns": [
                            {"type": "toml", "key": "project.version"},
                            {"type": "markdown", "pattern": "Version:\\s*(.*)"},
                            {"type": "text", "pattern": "Version:\\s*(.*)"},
                        ],
                    },
                },
            },
            {
                "path": str(Path.home() / "Documents/Indexly/CSV"),
                "profile": "csv",
                "identity": None,
                "fields": {
                    "row_count": {"type": "metadata", "key": "row_count"},
                    "col_count": {"type": "metadata", "key": "col_count"},
                },
            },
        ]
    }


def load_config() -> dict:
    """Load observer config, auto-create default if missing."""
    config_path = get_config_path()

    if not config_path.exists():
        print(f"[INFO] Observer config not found. Creating default at {config_path}")
        save_config(default_config())

    try:
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"[WARN] Invalid JSON in {config_path}. Replacing with default.")
        save_config(default_config())
        return default_config()


def save_config(config: dict) -> None:
    """Save config JSON to user home directory."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_watch_entries(config: dict) -> list[dict]:
    """Return the list of watch entries from the config."""
    return config.get("watch", [])


def find_watch_entry(file_path: str, config: dict | None = None) -> dict | None:
    """Return the first watch entry whose path is a parent of file_path."""
    config = config or load_config()
    path = Path(file_path).resolve()
    for entry in get_watch_entries(config):
        watch_path = Path(entry["path"]).expanduser().resolve()
        if path.is_relative_to(watch_path):
            return entry
    return None


def init_config() -> None:
    """CLI-friendly initializer."""
    path = get_config_path()
    if path.exists():
        print(f"[INFO] Config already exists at {path}")
        return
    save_config(default_config())
    print(f"[INFO] Default observer config created at {path}")
    print("You can now edit it to change watch paths, profiles, or fields.")
