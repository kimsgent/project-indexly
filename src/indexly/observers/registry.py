# indexly/observers/registry.py

import logging
from collections.abc import Callable

from .base import BaseObserver
from .identity_observer import IdentityObserver
from .field_observer import FieldObserver
from .state_observer import StateObserver
from .csv.csv_observer import CSVObserver

from indexly.observers.health import (
    HealthIdentityObserver,
    HealthFieldObserver,
    HealthEventObserver,
)

_OBSERVERS: list[BaseObserver] = []
_DISABLED_OBSERVERS: set[str] = set()
_EVENT_HANDLERS: list[Callable[[str, dict], None]] = []
logger = logging.getLogger(__name__)

# ---------------------------
# Registration API
# ---------------------------


def register_observer(observer: BaseObserver) -> None:
    """Add observer to registry."""
    _OBSERVERS.append(observer)


def get_observers() -> list[BaseObserver]:
    """Return all registered observers."""
    return list(_OBSERVERS)


def disable_observer(name: str) -> None:
    """Disable observer by name until re-enabled."""
    _DISABLED_OBSERVERS.add(name)


def enable_observer(name: str) -> None:
    """Re-enable a disabled observer."""
    _DISABLED_OBSERVERS.discard(name)


def is_observer_enabled(name: str) -> bool:
    """Return whether an observer is currently enabled."""
    return name not in _DISABLED_OBSERVERS


def get_enabled_observers() -> list[BaseObserver]:
    """Return observers that are currently enabled."""
    return [observer for observer in _OBSERVERS if is_observer_enabled(observer.name)]


def register_event_handler(handler: Callable[[str, dict], None]) -> None:
    """Register a callback invoked for each emitted observer event."""
    _EVENT_HANDLERS.append(handler)


def emit_event(observer_name: str, event: dict) -> None:
    """Call all registered observer event handlers."""
    for handler in list(_EVENT_HANDLERS):
        try:
            handler(observer_name, event)
        except Exception as exc:
            logger.warning("Observer event handler failed: %s", exc)


# ---------------------------
# Register built-in observers
# ---------------------------
register_observer(IdentityObserver())
register_observer(FieldObserver())
register_observer(StateObserver())

# ---------------------------
# Health Register built-in observers
# ---------------------------
register_observer(HealthIdentityObserver())
register_observer(HealthFieldObserver())
register_observer(HealthEventObserver())

# ---------------------------
# csv Register built-in observers
# ---------------------------
register_observer(CSVObserver())
