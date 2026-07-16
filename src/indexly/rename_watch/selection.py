"""Portable, read-only file selection for rename-watch jobs."""

from __future__ import annotations

import fnmatch
import os
import stat
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from indexly.ignore import IgnoreRules

from .config import RenameWatchConfigError, RenameWatchJob


INDEXLYIGNORE_FILENAME = ".indexlyignore"
MAX_INDEXLYIGNORE_BYTES = 1024 * 1024
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    return bool(
        getattr(file_stat, "st_file_attributes", 0)
        & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _identity(file_stat: os.stat_result) -> Tuple[int, int, int, int, int, int]:
    return (
        int(getattr(file_stat, "st_dev", 0)),
        int(getattr(file_stat, "st_ino", 0)),
        stat.S_IFMT(file_stat.st_mode),
        int(file_stat.st_size),
        int(getattr(file_stat, "st_mtime_ns", 0)),
        int(getattr(file_stat, "st_file_attributes", 0)),
    )


def _read_root_indexlyignore(root: Path) -> Optional[IgnoreRules]:
    """Read exactly ``root/.indexlyignore`` without following a file link."""
    path = root / INDEXLYIGNORE_FILENAME
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RenameWatchConfigError(
            "job .indexlyignore could not be inspected: {0} ({1})".format(path, exc)
        ) from exc

    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or _is_reparse_point(before)
    ):
        raise RenameWatchConfigError(
            "job .indexlyignore must be a regular file without links or reparse points: {0}".format(
                path
            )
        )
    if before.st_size > MAX_INDEXLYIGNORE_BYTES:
        raise RenameWatchConfigError(
            "job .indexlyignore is oversized: {0}".format(path)
        )

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(os.fspath(path), flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse_point(opened)
            or _identity(opened) != _identity(before)
        ):
            raise RenameWatchConfigError(
                "job .indexlyignore changed while opening: {0}".format(path)
            )
        chunks = []
        remaining = MAX_INDEXLYIGNORE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_INDEXLYIGNORE_BYTES:
            raise RenameWatchConfigError(
                "job .indexlyignore is oversized: {0}".format(path)
            )
        after = path.lstat()
        if (
            not stat.S_ISREG(after.st_mode)
            or stat.S_ISLNK(after.st_mode)
            or _is_reparse_point(after)
            or _identity(after) != _identity(opened)
        ):
            raise RenameWatchConfigError(
                "job .indexlyignore changed while being read: {0}".format(path)
            )
    except RenameWatchConfigError:
        raise
    except FileNotFoundError as exc:
        raise RenameWatchConfigError(
            "job .indexlyignore changed while being read: {0}".format(path)
        ) from exc
    except OSError as exc:
        raise RenameWatchConfigError(
            "job .indexlyignore could not be read: {0} ({1})".format(path, exc)
        ) from exc
    finally:
        if descriptor is not None:
            primary_error = sys.exc_info()[0] is not None
            try:
                os.close(descriptor)
            except OSError as exc:
                if not primary_error:
                    raise RenameWatchConfigError(
                        "job .indexlyignore could not be closed: {0} ({1})".format(
                            path, exc
                        )
                    ) from exc

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RenameWatchConfigError(
            "job .indexlyignore is not valid UTF-8: {0} ({1})".format(path, exc)
        ) from exc
    return IgnoreRules(text.splitlines())


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return ""


def _matches_globs(
    patterns: Tuple[str, ...],
    path: Path,
    root: Path,
    *,
    directory: bool = False,
) -> bool:
    relative = _relative_posix(path, root)
    if not relative:
        return False
    relative_folded = unicodedata.normalize("NFC", relative).casefold()
    basename_folded = unicodedata.normalize("NFC", path.name).casefold()
    for pattern in patterns:
        folded = unicodedata.normalize("NFC", pattern).casefold()
        if pattern.endswith("/"):
            directory_pattern = folded[:-1]
            if directory:
                if _matches_path_glob(directory_pattern, relative_folded):
                    return True
                continue
            parts = relative_folded.split("/")[:-1]
            if any(
                _matches_path_glob(directory_pattern, "/".join(parts[:index]))
                for index in range(1, len(parts) + 1)
            ):
                return True
            continue
        if "/" in pattern:
            matched = _matches_path_glob(folded, relative_folded)
        else:
            matched = fnmatch.fnmatchcase(basename_folded, folded)
        if matched:
            return True
    return False


def _matches_path_glob(pattern: str, value: str) -> bool:
    """Match POSIX path segments, reserving ``**`` for recursive matching."""
    pattern_parts = pattern.split("/")
    value_parts = value.split("/")
    matches = [
        [False] * (len(value_parts) + 1)
        for _ in range(len(pattern_parts) + 1)
    ]
    matches[-1][-1] = True
    for pattern_index in range(len(pattern_parts) - 1, -1, -1):
        pattern_part = pattern_parts[pattern_index]
        for value_index in range(len(value_parts), -1, -1):
            if pattern_part == "**":
                matches[pattern_index][value_index] = matches[pattern_index + 1][
                    value_index
                ] or (
                    value_index < len(value_parts)
                    and matches[pattern_index][value_index + 1]
                )
            elif value_index < len(value_parts):
                matches[pattern_index][value_index] = fnmatch.fnmatchcase(
                    value_parts[value_index], pattern_part
                ) and matches[pattern_index + 1][value_index + 1]
    return matches[0][0]


def _matches_ancestor_globs(
    patterns: Tuple[str, ...], path: Path, root: Path
) -> bool:
    relative = _relative_posix(path, root)
    if not relative:
        return False
    parts = unicodedata.normalize("NFC", relative).casefold().split("/")[:-1]
    for index in range(1, len(parts) + 1):
        ancestor_relative = "/".join(parts[:index])
        ancestor_name = parts[index - 1]
        for pattern in patterns:
            folded = unicodedata.normalize("NFC", pattern).casefold()
            if folded.endswith("/"):
                folded = folded[:-1]
            if "/" in folded:
                matched = _matches_path_glob(folded, ancestor_relative)
            else:
                matched = fnmatch.fnmatchcase(ancestor_name, folded)
            if matched:
                return True
    return False


@dataclass(frozen=True)
class SelectionPolicy:
    root: Path
    include: Optional[Tuple[str, ...]]
    exclude: Tuple[str, ...]
    max_file_size_bytes: Optional[int]
    root_ignore: Optional[IgnoreRules]
    protect_indexlyignore: bool
    quarantine_path: Optional[Path]

    def accepts_file(self, path: Path, size: int) -> bool:
        if self.quarantine_path is not None:
            try:
                path.resolve().relative_to(self.quarantine_path.resolve())
                return False
            except (ValueError, OSError):
                pass
        if (
            self.protect_indexlyignore
            and path.parent.resolve() == self.root.resolve()
            and path.name.casefold() == INDEXLYIGNORE_FILENAME.casefold()
        ):
            return False
        if self.include is not None and not _matches_globs(
            self.include, path, self.root
        ):
            return False
        if _matches_globs(self.exclude, path, self.root) or _matches_ancestor_globs(
            self.exclude, path, self.root
        ):
            return False
        if self.root_ignore is not None and self.root_ignore.should_ignore(
            path, root=self.root
        ):
            return False
        return self.max_file_size_bytes is None or size <= self.max_file_size_bytes

    def excludes_directory(self, path: Path) -> bool:
        if self.quarantine_path is not None:
            try:
                path.resolve().relative_to(self.quarantine_path.resolve())
                return True
            except (ValueError, OSError):
                pass
        if _matches_globs(self.exclude, path, self.root, directory=True):
            return True
        return self.root_ignore is not None and self.root_ignore.should_ignore(
            path, root=self.root
        )


def load_selection_policy(job: RenameWatchJob) -> SelectionPolicy:
    """Build one immutable policy; disk-backed ignore rules are read once."""
    root_ignore = (
        _read_root_indexlyignore(job.watch_path)
        if job.respect_indexlyignore
        else None
    )
    return SelectionPolicy(
        root=job.watch_path,
        include=job.include,
        exclude=job.exclude,
        max_file_size_bytes=job.max_file_size_bytes,
        root_ignore=root_ignore,
        protect_indexlyignore=job.respect_indexlyignore,
        quarantine_path=job.quarantine_path,
    )


__all__ = [
    "INDEXLYIGNORE_FILENAME",
    "MAX_INDEXLYIGNORE_BYTES",
    "SelectionPolicy",
    "load_selection_policy",
]
