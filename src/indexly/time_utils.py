from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    Return a timezone-aware UTC timestamp.

    Centralizing this avoids deprecated naive `datetime.utcnow()` calls and keeps
    emitted timestamps explicit about being in UTC.
    """
    return datetime.now(timezone.utc)


def utc_now_iso_z() -> str:
    """
    Return an ISO-8601 UTC timestamp using a `Z` suffix.

    The `Z` form preserves the repo's existing serialized timestamp shape while
    still originating from an aware UTC datetime.
    """
    return utc_now().isoformat().replace("+00:00", "Z")
