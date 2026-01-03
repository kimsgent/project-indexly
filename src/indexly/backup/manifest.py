# src/indexly/backup/manifest.py

from __future__ import annotations
from pathlib import Path
import hashlib
import json
import logging
import tempfile
import shutil
from .extract import extract_archive

logger = logging.getLogger("indexly_manifest")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def build_manifest(root_path: Path) -> dict:
    manifest = {}
    for p in root_path.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root_path).as_posix()
            manifest[rel] = {
                "checksum": _hash_file(p),
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            }
    return manifest


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))



def diff_manifests(previous: dict, current: dict, include_deletions: bool = False) -> tuple[dict, list]:
    """
    Compute incremental changes between previous and current manifest.

    Returns:
        - diff: dict of added/modified files
        - deleted: list of deleted files

    Notes:
        - Missing checksum fields are treated as changed.
        - Files removed from source are tracked in `deleted` if include_deletions=True.
    """
    diff = {}
    deleted = []

    # Detect new or modified files
    for f, meta in current.items():
        prev_meta = previous.get(f)
        if not prev_meta:
            # New file
            diff[f] = meta
        else:
            # Modified file if checksum differs
            prev_checksum = prev_meta.get("checksum")
            curr_checksum = meta.get("checksum")
            if prev_checksum != curr_checksum:
                diff[f] = meta

    # Detect deletions
    if include_deletions:
        deleted = [f for f in previous if f not in current]

    return diff, deleted



def has_effective_changes(archive: Path) -> bool:
    """
    Pre-flight check to determine whether restoring this archive
    would have any effect on the resulting snapshot.

    Semantics:

    - FULL backup:
      Always returns True. A full backup defines the base snapshot
      and must be applied.

    - INCREMENTAL backup (current format):
      Returns False if:
        * manifest.json exists AND
        * there is no "data/" directory OR "data/" is empty.

      In that case, the archive has no changed files to apply.
      (Deletions are already reflected in the snapshot-style manifest
       and are encoded by the absence of entries.)

    This function performs a lightweight extraction into a temporary
    directory, inspects the manifest and the "data/" directory, then
    discards the extracted files.

    NOTE: This is intentionally conservative and will err on the side
    of returning True if anything looks unusual.
    """

    archive = Path(archive)

    # Defensive logging: help diagnose why a step was or was not applied.
    logger.info(f"Pre-flight change check for archive: {archive}")

    if not archive.exists():
        logger.warning(f"Archive does not exist on disk: {archive}")
        # If the archive is missing, let the caller handle it.
        # From this function's perspective, avoid claiming "no changes".
        return True

    # Temporary directory for inspection only.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        try:
            extract_archive(archive, tmp)
        except Exception as e:
            # If extraction fails here, log a warning and force True so that
            # the main restore flow can handle and report the failure.
            logger.error(
                f"Pre-flight extraction failed for {archive}: {e}. "
                f"Treating as having changes to avoid silently skipping.",
                exc_info=True,
            )
            return True

        manifest_file = tmp / "manifest.json"
        if not manifest_file.exists():
            logger.error(
                f"manifest.json missing in archive {archive}. "
                f"Treating as having changes so restore can detect and fail visibly."
            )
            return True

        try:
            manifest_data = json.loads(manifest_file.read_text("utf-8"))
        except Exception as e:
            logger.error(
                f"Failed to parse manifest.json in {archive}: {e}. "
                f"Treating as having changes.",
                exc_info=True,
            )
            return True

        logger.info(
            f"Manifest loaded for {archive}. "
            f"Entries: {len(manifest_data) if isinstance(manifest_data, dict) else 'unknown'}"
        )

        # Check the data directory for any changed files.
        data_dir = tmp / "data"
        if not data_dir.exists():
            logger.info(
                f"No 'data/' directory in {archive}. "
                f"Assuming snapshot-only or empty incremental → no effective changes."
            )
            return False

        # If 'data/' exists but has no files, then this incremental carries no file changes.
        # Deletions are already encoded in the snapshot manifest produced by backup.
        has_files = any(data_dir.rglob("*"))
        if not has_files:
            logger.info(
                f"'data/' directory in {archive} is empty. "
                f"No changed files → archive has no effective changes."
            )
            return False

        logger.info(
            f"'data/' in {archive} contains changed files. "
            f"Archive has effective changes and should be applied."
        )
        return True
