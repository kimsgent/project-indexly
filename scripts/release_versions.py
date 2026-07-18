#!/usr/bin/env python3
"""Consistent release-version classification for scripts and workflows."""

from __future__ import annotations

import argparse

from packaging.version import InvalidVersion, Version


def normalize_version(value: str) -> str:
    """Return a version without the repository's optional ``v`` prefix."""
    candidate = value.strip()
    if candidate[:1].lower() == "v":
        candidate = candidate[1:]
    return candidate


def is_prerelease(value: str) -> bool:
    """Classify PEP 440 prereleases plus the legacy workflow dry-run suffix."""
    candidate = normalize_version(value)
    if candidate.lower().endswith("-test"):
        return True
    return Version(candidate).is_prerelease


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    args = parser.parse_args()
    try:
        prerelease = is_prerelease(args.version)
    except InvalidVersion as exc:
        parser.error(str(exc))
    print("true" if prerelease else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
