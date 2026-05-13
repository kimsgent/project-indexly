import json
import time
from pathlib import Path
from typing import Any
from typing import Optional

from indexly.db_utils import connect_db
from .snapshot_store import ensure_snapshot_table
from indexly.compare.hash_utils import sha256
from indexly.backup.logging_utils import get_logger, OBSERVER_EVENT, OBSERVER_ERROR
from indexly.time_utils import utc_now

from .aggregator import aggregate_events
from .config import should_emit_event
from .metrics import MetricsCollector, ObserverMetrics
from .registry import emit_event, get_enabled_observers
from .snapshot_store import load_snapshot, save_snapshot

_TS = utc_now().strftime("%Y%m%dT%H%M%SZ")

observer_logger = get_logger(
    name="indexly.observers",
    log_dir=Path.home() / ".indexly" / "logs",
    ts=_TS,
    component="observer",
)


def _observer_sort_key(observer) -> int:
    return 1 if getattr(observer, "dependencies", []) else 0


def _validate_state(observer_name: str, state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise TypeError(
            f"{observer_name}.extract() must return dict, got {type(state)}"
        )
    return state


def _validate_events(observer_name: str, events: Any) -> list[dict]:
    if not isinstance(events, list):
        raise TypeError(
            f"{observer_name}.compare() must return list, got {type(events)}"
        )
    if not all(isinstance(event, dict) for event in events):
        raise TypeError(f"{observer_name}.compare() events must all be dicts")
    return events


def _snapshot_identity(state: dict[str, Any]) -> str | None:
    identity = state.get("identity")
    if identity is not None:
        return str(identity)

    for key in ("patient_id", "entity_key"):
        value = state.get(key)
        if value is not None:
            return str(value)

    return None


def run_observers(
    file_path: Path, metadata: dict[str, Any] | None = None
) -> list[dict]:
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
    observer_outputs: dict[str, tuple[dict | None, dict, list[dict]]] = {}
    emitted_events: list[dict] = []

    for observer in sorted(get_enabled_observers(), key=_observer_sort_key):
        start = time.perf_counter()
        try:
            if not observer.applies_to(file_path, metadata):
                continue

            dependencies = getattr(observer, "dependencies", [])
            if dependencies:
                if hasattr(observer, "_dependency_outputs"):
                    observer._dependency_outputs = {}

                missing = [dep for dep in dependencies if dep not in observer_outputs]
                if missing:
                    observer_logger.warning(
                        "Observer dependency output missing",
                        extra={
                            "event": OBSERVER_ERROR,
                            "context": {
                                "path": raw_path,
                                "observer": observer.name,
                                "missing_dependencies": missing,
                            },
                        },
                    )

                for dep_name in dependencies:
                    if dep_name in observer_outputs and hasattr(
                        observer, "set_dependency_output"
                    ):
                        dep_old, dep_new, dep_events = observer_outputs[dep_name]
                        observer.set_dependency_output(
                            dep_name,
                            dep_old,
                            dep_new,
                            dep_events,
                        )

            # Load observer-specific historical snapshots when available.
            if getattr(observer, "load_previous_snapshot", None):
                old_state = observer.load_previous_snapshot(
                    raw_path, snapshot_ts=metadata.get("snapshot_ts")
                )
            else:
                old_state = load_snapshot(observer.name, raw_path)

            new_state = _validate_state(
                observer.name, observer.extract(file_path, metadata) or {}
            )
            events = _validate_events(
                observer.name, observer.compare(old_state, new_state) or []
            )
            events = [
                event for event in events if should_emit_event(observer.name, event)
            ]
            events = aggregate_events(
                events,
                strategy=metadata.get("event_aggregation", "none"),
            )
            observer_outputs[observer.name] = (old_state, new_state, events)

            # Log events in structured logging
            for event in events:
                emitted_events.append({"observer": observer.name, **event})
                emit_event(observer.name, event)
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
                identity=_snapshot_identity(new_state),
                hash_value=hash_value,
                state=new_state,
            )

            observer_save = getattr(observer, "save", None)
            if callable(observer_save) and new_state:
                observer_save(file_path, new_state)

            # --- User-friendly terminal output ----
            if events:
                print(f"\n📄 [{observer.name}] changes detected for: {raw_path}")
                for ev in events:
                    try:
                        rendered = observer.format_event(ev)
                    except Exception:
                        rendered = str(ev)
                    print(f"  - {rendered}")
            else:
                print(f"\n📄 [{observer.name}] no changes detected for: {raw_path}")

            elapsed_ms = (time.perf_counter() - start) * 1000
            MetricsCollector.record(
                ObserverMetrics(
                    observer_name=observer.name,
                    execution_time_ms=elapsed_ms,
                    event_count=len(events),
                    error=False,
                )
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            MetricsCollector.record(
                ObserverMetrics(
                    observer_name=observer.name,
                    execution_time_ms=elapsed_ms,
                    event_count=0,
                    error=True,
                    error_msg=str(e),
                )
            )
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

    return emitted_events


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

        _TS = utc_now().strftime("%Y%m%dT%H%M%SZ")
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


def run_observers_batch(
    file_paths: list[Path],
    metadata_dict: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict]]:
    """
    Run observers for multiple files and return emitted events by path.

    This keeps the public API simple while preserving per-file observer
    isolation and existing snapshot behavior.
    """
    metadata_dict = metadata_dict or {}
    results: dict[str, list[dict]] = {}

    for file_path in file_paths:
        metadata = metadata_dict.get(str(file_path), {})
        results[str(file_path)] = run_observers(file_path, metadata)

    return results


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
        cur = conn.execute("""
            SELECT observer, identity, file_path, hash, state_json, timestamp
            FROM observer_snapshots
            ORDER BY timestamp ASC
            """)

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
