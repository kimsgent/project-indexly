from pathlib import Path
from typing import Any

from indexly.compare.hash_utils import sha256
from indexly.log_utils import _unified_log_entry

from .registry import get_observers
from .snapshot_store import load_snapshot, save_snapshot


def run_observers(file_path: Path, metadata: dict[str, Any] | None = None) -> None:
    """
    Run all registered observers on a file.
    """
    metadata = metadata or {}
    raw_path = str(file_path)

    # Ensure hash exists
    hash_value = metadata.get("hash")
    if hash_value is None and file_path.exists():
        hash_value = sha256(file_path)

    metadata["hash"] = hash_value

    for observer in get_observers():
        try:
            if not observer.applies_to(file_path, metadata):
                continue

            old_state = load_snapshot(observer.name, raw_path)
            new_state = observer.extract(file_path, metadata)

            events = observer.compare(old_state, new_state)

            for event in events:
                entry = _unified_log_entry(
                    "OBSERVER_EVENT",
                    raw_path,
                )
                entry.update(
                    {
                        "observer": observer.name,
                        "semantic_event": event,
                    }
                )
                # emit log
                print(entry)  # replace with your logger sink

            save_snapshot(
                observer.name,
                raw_path,
                identity=new_state.get("identity"),
                hash_value=hash_value,
                state=new_state,
            )

        except Exception as e:
            # Observer failures must never break indexly
            entry = _unified_log_entry(
                "OBSERVER_ERROR",
                raw_path,
            )
            entry["error"] = str(e)
            print(entry)
