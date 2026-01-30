# indexly/observers/registry.py

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

# ---------------------------
# Registration API
# ---------------------------


def register_observer(observer: BaseObserver) -> None:
    """Add observer to registry."""
    _OBSERVERS.append(observer)


def get_observers() -> list[BaseObserver]:
    """Return all registered observers."""
    return list(_OBSERVERS)


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
