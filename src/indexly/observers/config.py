"""
📄 indexly/observers/config.py

Purpose:
  This module handles reading the JSON configuration and providing observer rules.

"""

import json
import os
import tempfile
from pathlib import Path

CONFIG_FILENAME = ".indexly.observers.json"


def _fallback_config_path() -> Path:
    return Path(tempfile.gettempdir()) / "indexly" / CONFIG_FILENAME


def _directory_is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(directory, os.W_OK | os.X_OK)


def get_config_path() -> Path:
    """Return full path to the observer config file."""
    home = Path.home()
    if _directory_is_writable(home):
        return home / CONFIG_FILENAME
    return _fallback_config_path()


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


def _validate_rule(rule: object, context: str) -> list[str]:
    """Validate one field extraction rule and return user-facing errors."""
    errors: list[str] = []

    if not isinstance(rule, dict):
        return [f"{context} must be an object"]

    rtype = rule.get("type")
    if not rtype:
        return [f"{context} missing 'type'"]

    if rtype in ("regex", "markdown", "text"):
        if not rule.get("pattern"):
            errors.append(f"{context} type '{rtype}' requires 'pattern'")
    elif rtype in ("toml", "metadata"):
        if not rule.get("key"):
            errors.append(f"{context} type '{rtype}' requires 'key'")
    elif rtype == "multi":
        patterns = rule.get("patterns")
        if not isinstance(patterns, list):
            errors.append(f"{context} type 'multi' requires 'patterns' list")
        else:
            for idx, subrule in enumerate(patterns):
                errors.extend(_validate_rule(subrule, f"{context}.patterns[{idx}]"))
    else:
        errors.append(f"{context} has unsupported type '{rtype}'")

    return errors


def validate_config(config: object) -> tuple[bool, list[str]]:
    """
    Validate observer config structure.

    Returns (is_valid, error_messages). Error messages are intended to be
    actionable for users editing ~/.indexly.observers.json by hand.
    """
    errors: list[str] = []

    if not isinstance(config, dict):
        return False, ["Config root must be an object"]

    if "watch" not in config:
        return False, ["Config missing 'watch' key"]

    watch = config.get("watch")
    if not isinstance(watch, list):
        return False, ["'watch' must be a list"]

    filters = config.get("event_filters", {})
    if filters and not isinstance(filters, dict):
        errors.append("'event_filters' must be an object")
    elif isinstance(filters, dict):
        for observer_name, event_types in filters.items():
            if not isinstance(observer_name, str) or not isinstance(event_types, list):
                errors.append("'event_filters' must map observer names to lists")
                break

    for idx, entry in enumerate(watch):
        context = f"watch[{idx}]"

        if not isinstance(entry, dict):
            errors.append(f"{context} must be an object")
            continue

        if not entry.get("path"):
            errors.append(f"{context} missing 'path'")
        if not entry.get("profile"):
            errors.append(f"{context} missing 'profile'")

        fields = entry.get("fields", {})
        if fields is None:
            continue
        if not isinstance(fields, dict):
            errors.append(f"{context}.fields must be an object")
            continue

        for field_name, rule in fields.items():
            errors.extend(_validate_rule(rule, f"{context}.fields[{field_name}]"))

    return len(errors) == 0, errors


def load_config() -> dict:
    """Load observer config, auto-create default if missing."""
    config_path = get_config_path()

    if not config_path.exists():
        print(f"[INFO] Observer config not found. Creating default at {config_path}")
        save_config(default_config())
        return default_config()

    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[WARN] Invalid JSON in {config_path}: {e}. Replacing with default.")
        save_config(default_config())
        return default_config()

    is_valid, errors = validate_config(config)
    if not is_valid:
        print(f"[WARN] Invalid observer config at {config_path}:")
        for error in errors:
            print(f"  - {error}")
        print("[WARN] Using default observer config instead.")
        return default_config()

    return config


def save_config(config: dict) -> None:
    """Save config JSON to disk, falling back to temp storage when needed."""
    config_path = get_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return
    except OSError:
        fallback_path = _fallback_config_path()
        if fallback_path == config_path:
            raise

    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    with fallback_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_watch_entries(config: dict) -> list[dict]:
    """Return the list of watch entries from the config."""
    return config.get("watch", [])


def get_event_filters(config: dict | None = None) -> dict[str, list[str]]:
    """Return event type filters keyed by observer name."""
    config = config or load_config()
    filters = config.get("event_filters", {})
    return filters if isinstance(filters, dict) else {}


def should_emit_event(
    observer_name: str,
    event: dict,
    config: dict | None = None,
) -> bool:
    """Return whether an event should be emitted after config filtering."""
    filters = get_event_filters(config)
    filtered_types = filters.get(observer_name)
    if not filtered_types:
        return True
    return event.get("type") not in filtered_types


def find_watch_entry(file_path: str, config: dict | None = None) -> dict | None:
    """Return the first watch entry whose path is a parent of file_path."""
    config = config or load_config()
    path = Path(file_path).resolve()
    for entry in get_watch_entries(config):
        try:
            watch_path = Path(entry["path"]).expanduser().resolve()
        except (KeyError, TypeError):
            continue

        try:
            if path.is_relative_to(watch_path):
                return entry
        except AttributeError:
            try:
                path.relative_to(watch_path)
                return entry
            except ValueError:
                continue
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
