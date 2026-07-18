import pytest
from packaging.version import InvalidVersion

from scripts.release_versions import is_prerelease, normalize_version


@pytest.mark.parametrize(
    "version",
    ["v2.1.5a0", "2.1.5b1", "v2.1.5rc2", "2.1.5.dev3", "v0.0.0-test"],
)
def test_prerelease_versions_are_never_routed_as_stable(version):
    assert is_prerelease(version) is True


@pytest.mark.parametrize("version", ["2.1.5", "v2.2.0", "  v3.0.0  "])
def test_stable_release_versions_remain_stable(version):
    assert is_prerelease(version) is False


def test_invalid_release_version_fails_closed():
    with pytest.raises(InvalidVersion):
        is_prerelease("not-a-release")


def test_normalize_version_removes_only_one_leading_tag_prefix():
    assert normalize_version(" v2.1.5a0 ") == "2.1.5a0"
