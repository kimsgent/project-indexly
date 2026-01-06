from pathlib import Path
import fnmatch


class IgnoreRules:
    __slots__ = ("_rules",)

    def __init__(self, rules: list[str]):
        # Store only non-empty, non-comment rules
        self._rules = [
            r.strip()
            for r in rules
            if r.strip() and not r.lstrip().startswith("#")
        ]

    def should_ignore(self, path: Path, root: Path | None = None) -> bool:
        """
        Determine if a file or folder should be ignored.

        Args:
            path: Absolute path of file/folder to check
            root: Optional root path to compute relative paths for directory rules

        Returns:
            True if the path matches any ignore rule
        """
        path = path.resolve().as_posix()

        # Compute relative path if root provided
        rel_path = path
        if root:
            root_path = Path(root).resolve().as_posix()
            if path.startswith(root_path):
                rel_path = path[len(root_path):].lstrip("/")

        filename = Path(path).name

        for rule in self._rules:
            rule = rule.rstrip()

            # Directory rule (ends with '/')
            if rule.endswith("/"):
                rule_dir = rule.rstrip("/")
                if rel_path.startswith(rule_dir + "/") or path.endswith(rule_dir):
                    return True

            # Filename match (glob)
            elif fnmatch.fnmatch(filename, rule):
                return True

            # Full path match (glob)
            elif fnmatch.fnmatch(path, rule) or fnmatch.fnmatch(rel_path, rule):
                return True

        return False
