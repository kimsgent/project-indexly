import json
from pathlib import Path
from typing import Any
from datetime import datetime
from typing import Optional

from indexly.db_utils import connect_db
from .snapshot_store import ensure_snapshot_table
from indexly.compare.hash_utils import sha256
from indexly.backup.logging_utils import get_logger, OBSERVER_EVENT, OBSERVER_ERROR

from .registry import get_observers
from .snapshot_store import load_snapshot, save_snapshot

_TS = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

observer_logger = get_logger(
    name="indexly.observers",
    log_dir=Path.home() / ".indexly" / "logs",
    ts=_TS,
    component="observer",
)


def run_observers(file_path: Path, metadata: dict[str, Any] | None = None) -> None:
    """
    Run all registered observers on a file and provide user-friendly terminal feedback.
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

            # Load historical snapshot if observer supports it and metadata has snapshot_ts
            if getattr(observer, "load_previous_snapshot", None) and metadata.get(
                "snapshot_ts"
            ):
                old_state = observer.load_previous_snapshot(
                    raw_path, snapshot_ts=metadata["snapshot_ts"]
                )
            else:
                old_state = load_snapshot(observer.name, raw_path)

            new_state = observer.extract(file_path, metadata)
            events = observer.compare(old_state, new_state)

            # Log events in structured logging
            for event in events:
                observer_logger.info(
                    f"{observer.name} emitted semantic event",
                    extra={
                        "event": OBSERVER_EVENT,
                        "context": {
                            "path": raw_path,
                            "observer": observer.name,
                            "semantic_event": event,
                            "hash": hash_value,
                            "snapshot_ts": metadata.get("snapshot_ts"),
                            "using_historical": bool(metadata.get("snapshot_ts")),
                        },
                    },
                )

            # Save new snapshot
            save_snapshot(
                observer.name,
                raw_path,
                identity=new_state.get("identity"),
                hash_value=hash_value,
                state=new_state,
            )

            # --- User-friendly terminal output ---
            if events:
                print(f"\n📄 [{observer.name}] changes detected for: {raw_path}")
                for ev in events:
                    print(
                        f"  - {ev['field']}: "
                        f"{ev['old']!r} → {ev['new']!r}"
                    )
            else:
                print(f"\n📄 [{observer.name}] no changes detected for: {raw_path}")

        except Exception as e:
            observer_logger.error(
                "Observer execution failed",
                extra={
                    "event": OBSERVER_ERROR,
                    "context": {
                        "path": raw_path,
                        "observer": observer.name,
                        "error": str(e),
                    },
                },
                exc_info=True,
            )
            # Print friendly error to terminal
            print(f"\n⚠️  [{observer.name}] observer failed for {raw_path}: {e}")


def handle_observe_run(
    path: str | Path,
    recursive: bool = False,
    metadata: dict[str, Any] | None = None,
    log_dir: str | Path | None = None,
    snapshot_ts: str | None = None,  # <-- new optional argument
) -> None:
    target = Path(path).expanduser().resolve()
    metadata = metadata or {}

    # Inject snapshot_ts into metadata for observers
    if snapshot_ts:
        metadata["snapshot_ts"] = snapshot_ts

    # Update logger if a custom log_dir is passed
    global observer_logger
    if log_dir:

        _TS = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        observer_logger = get_logger(
            name="indexly.observers",
            log_dir=Path(log_dir),
            ts=_TS,
            component="observer",
        )

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")

    if target.is_file():
        run_observers(target, metadata)
        return

    if target.is_dir():
        if recursive:
            for file in target.rglob("*"):
                if file.is_file():
                    run_observers(file, metadata)
        else:
            for file in target.iterdir():
                if file.is_file():
                    run_observers(file, metadata)
        return

    raise ValueError(f"Unsupported path type: {target}")


def handle_observe_audit(patient_id: Optional[str] = None) -> None:
    """
    Audit semantic observer snapshots.
    Optionally filter by identity / patient_id.
    """
    conn = connect_db()
    ensure_snapshot_table(conn)

    if patient_id:
        cur = conn.execute(
            """
            SELECT observer, identity, file_path, hash, state_json, timestamp
            FROM observer_snapshots
            WHERE identity = ?
            ORDER BY timestamp ASC
            """,
            (patient_id,),
        )
    else:
        cur = conn.execute(
            """
            SELECT observer, identity, file_path, hash, state_json, timestamp
            FROM observer_snapshots
            ORDER BY timestamp ASC
            """
        )

    rows = cur.fetchall()

    for row in rows:
        print(
            {
                "observer": row["observer"],
                "identity": row["identity"],
                "path": row["file_path"],
                "hash": row["hash"],
                "state": json.loads(row["state_json"]) if row["state_json"] else None,
                "timestamp": row["timestamp"],
            }
        )
