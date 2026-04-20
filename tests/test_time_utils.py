from datetime import timedelta

from indexly.time_utils import utc_now, utc_now_iso_z


def test_utc_now_returns_timezone_aware_utc_datetime():
    current = utc_now()

    assert current.tzinfo is not None
    assert current.utcoffset() == timedelta(0)


def test_utc_now_iso_z_returns_utc_z_suffix():
    current = utc_now_iso_z()

    assert current.endswith("Z")
    # Keep the serialized form stable for metadata/log fields that already
    # expect ISO timestamps with a literal UTC suffix.
    assert "+00:00" not in current
