# src/indexly/ignore_defaults/loader.py

from pathlib import Path
from functools import lru_cache

from .validator import validate_template
from . import presets


@lru_cache(maxsize=8)
def _read_preset(name: str) -> list[str]:
    """
    Load a preset template as list of non-empty lines.
    Used internally for creating IgnoreRules instances.
    """
    content = presets.load_preset(name)
    return [line for line in content.splitlines() if line.strip()]


def load_ignore_template(name: str = "standard") -> str:
    """
    Return the raw preset template string.
    Presets: minimal, standard, aggressive
    """
    return presets.load_preset(name)


def load_ignore_rules(
    root: Path,
    custom_ignore: Path | None = None,
    preset: str = "standard",
):
    """
    Return an IgnoreRules instance based on priority:

    1. Explicit ignore file (custom_ignore)
    2. Project-local .indexlyignore
    3. Built-in preset (cached)
    """
    from indexly.ignore.ignore_rules import IgnoreRules  # lazy import to avoid circular import

    # 1. Explicit ignore file
    if custom_ignore and custom_ignore.exists():
        content = custom_ignore.read_text(encoding="utf-8")
        validate_template(content)
        return IgnoreRules(content.splitlines())

    # 2. Project-local .indexlyignore
    local_ignore = root / ".indexlyignore"
    if local_ignore.exists():
        content = local_ignore.read_text(encoding="utf-8")
        validate_template(content)
        return IgnoreRules(content.splitlines())

    # 3. Built-in preset (cached)
    return IgnoreRules(_read_preset(preset))
