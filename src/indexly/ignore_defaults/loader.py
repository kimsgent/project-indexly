from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass

from .validator import validate_template
from . import presets


@dataclass
class IgnoreLoadInfo:
    source: str
    path: Path | None
    preset: str | None
    raw: str
    loaded_via: str
    validation: str
    lines_total: int
    active_rules: int
    comments: int
    blank_lines: int


@lru_cache(maxsize=8)
def _read_preset(name: str) -> list[str]:
    content = presets.load_preset(name)
    return [line for line in content.splitlines() if line.strip()]

def load_ignore_template(name: str = "standard") -> str:
    """
    Return the raw preset template string.
    Presets: minimal, standard, aggressive
    """
    return presets.load_preset(name)

def _analyze(content: str, validation_ok: bool) -> dict:
    lines = content.splitlines()
    stripped = [l.strip() for l in lines]

    return {
        "lines_total": len(lines),
        "active_rules": sum(1 for l in stripped if l and not l.startswith("#")),
        "comments": sum(1 for l in stripped if l.startswith("#")),
        "blank_lines": sum(1 for l in stripped if not l),
        "validation": "OK" if validation_ok else "FAIL",
    }

def load_ignore_rules(
    root: Path,
    custom_ignore: Path | None = None,
    preset: str = "standard",
    with_info: bool = False,
):
    from indexly.ignore.ignore_rules import IgnoreRules

    # 1. Explicit ignore
    if custom_ignore and custom_ignore.exists():
        raw = custom_ignore.read_text(encoding="utf-8")
        ok, _ = validate_template(raw)
        stats = _analyze(raw, ok)
        rules = IgnoreRules(raw.splitlines())
        info = IgnoreLoadInfo(
            source="explicit ignore file",
            path=custom_ignore,
            preset=None,
            raw=raw,
            loaded_via="filesystem",
            **stats,
        )
        return (rules, info) if with_info else rules

    # 2. Project-local
    local = root / ".indexlyignore"
    if local.exists():
        raw = local.read_text(encoding="utf-8")
        ok, _ = validate_template(raw)
        stats = _analyze(raw, ok)
        rules = IgnoreRules(raw.splitlines())
        info = IgnoreLoadInfo(
            source="project-local .indexlyignore",
            path=local,
            preset=None,
            raw=raw,
            loaded_via="filesystem",
            **stats,
        )
        return (rules, info) if with_info else rules

    # 3. Preset (cached internally, but irrelevant to user)
    raw = presets.load_preset(preset)
    ok, _ = validate_template(raw)
    stats = _analyze(raw, ok)
    rules = IgnoreRules(_read_preset(preset))
    info = IgnoreLoadInfo(
        source="preset",
        path=None,
        preset=preset,
        raw=raw,
        loaded_via="preset",
        **stats,
    )
    return (rules, info) if with_info else rules
