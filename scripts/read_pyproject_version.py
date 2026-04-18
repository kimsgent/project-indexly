#!/usr/bin/env python3
"""Print the project version from pyproject.toml."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def main() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    print(data["project"]["version"])


if __name__ == "__main__":
    main()
