from __future__ import annotations

from pathlib import Path
from fnmatch import fnmatch
from typing import Iterable
from indexly.path_utils import normalize_path


DEFAULT_IGNORE_FILENAME = ".indexlyignore"


class IgnoreRules:
    __slots__ = ("root", "rules", "enabled")

    def __init__(self, root: Path, ignore_file: Path | None = None):
        self.root = Path(normalize_path(str(root)))
        self.rules: list[str] = []
        self.enabled = False

        path = (
            ignore_file
            if ignore_file
            else self.root / DEFAULT_IGNORE_FILENAME
        )

        if path and path.exists():
            self._load(path)

    # ----------------------------- public API -----------------------------

    def should_ignore(self, path: Path) -> bool:
        if not self.enabled:
            return False

        norm = normalize_path(str(path))
        if not norm:
            return False

        rel = self._relative(norm)

        return any(
            self._match(rule, norm, rel)
            for rule in self.rules
        )

    # ----------------------------- internals ------------------------------

    def _load(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            self.rules = [
                line.strip()
                for line in lines
                if line.strip() and not line.strip().startswith("#")
            ]
            self.enabled = bool(self.rules)
        except Exception:
            self.rules = []
            self.enabled = False

    def _relative(self, norm_path: str) -> str:
        root = normalize_path(str(self.root)).lower()
        norm = normalize_path(norm_path).lower()

        if norm.startswith(root):
            return norm[len(root):].lstrip("/")
        return norm

    @staticmethod
    def _match(rule: str, abs_path: str, rel_path: str) -> bool:
        rule = rule.replace("\\", "/")

        # Directory rule
        if rule.endswith("/"):
            return (
                rel_path.startswith(rule.rstrip("/"))
                or abs_path.endswith(rule.rstrip("/"))
            )

        # Absolute path match
        if "/" in rule:
            return fnmatch(abs_path, rule) or fnmatch(rel_path, rule)

        # Filename / extension match
        return fnmatch(Path(rel_path).name, rule)


# ----------------------------- helpers -----------------------------------

def load_ignore_rules(
    index_root: Path,
    ignore_file: Path | None = None,
) -> IgnoreRules:
    return IgnoreRules(index_root, ignore_file)
