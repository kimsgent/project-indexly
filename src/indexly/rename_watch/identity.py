"""Shared canonical identities for rename-watch roots and state."""

from __future__ import annotations

import hashlib
import os
import unicodedata
from pathlib import Path
from typing import Tuple


def _normalized_name(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _actual_filesystem_path(path: Path) -> Path:
    """Recover on-disk component spelling for case/Unicode-equivalent paths."""
    resolved = path.resolve()
    if os.name == "nt":
        return resolved
    current = Path(resolved.anchor)
    parts = resolved.parts[1:] if resolved.anchor else resolved.parts
    for part in parts:
        requested = current / part
        actual = part
        try:
            requested_stat = requested.stat()
            for candidate in current.iterdir():
                if _normalized_name(candidate.name) != _normalized_name(part):
                    continue
                candidate_stat = candidate.stat()
                if os.path.samestat(requested_stat, candidate_stat):
                    actual = candidate.name
                    break
        except OSError:
            pass
        current = current / actual
    return current


def canonical_root_identity(root: Path) -> str:
    actual = _actual_filesystem_path(Path(root))
    return unicodedata.normalize("NFC", os.path.normcase(str(actual)))


def root_identity_strings(root: Path) -> Tuple[str, ...]:
    resolved = Path(root).resolve()
    identities = ["path:{0}".format(canonical_root_identity(resolved))]
    try:
        stat = resolved.stat()
    except OSError:
        stat = None
    if stat is not None and stat.st_ino:
        identities.append("stat:{0}:{1}".format(stat.st_dev, stat.st_ino))
    return tuple(identities)


def identity_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def state_namespace(root: Path, job_id: str) -> str:
    identity = "{0}\0{1}".format(canonical_root_identity(root), job_id)
    return identity_hash(identity)
