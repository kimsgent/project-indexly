"""Manage a user-owned optional-dependency overlay for Indexly.

The overlay is deliberately separate from the running installation. This is
especially important for package-manager installations whose environment must
remain immutable (for example, a Homebrew ``libexec`` virtual environment).
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from indexly.runtime_paths import resolve_base_dir

SUPPORTED_GROUPS = (
    "documents",
    "analysis",
    "visualization",
    "pdf_export",
    "backup",
)
EXTRA_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "documents": (
        "pymupdf>=1.23,<2.0",
        "pytesseract>=0.3.13,<0.4",
        "Pillow>=10.0,<12.0",
        "python-docx>=1.2,<2.0",
        "openpyxl>=3.1,<4.0",
        "extract_msg>=0.25,<1.0",
        "eml-parser>=1.0,<2.0",
        "python-pptx>=0.6,<1.0",
        "ebooklib>=0.18,<1.0",
        "odfpy>=1.4,<2.0",
    ),
    "analysis": (
        "pandas>=2.1,<3.0",
        "numpy>=1.26,<3.0",
        "scipy>=1.12,<2.0",
        "statsmodels>=0.14,<0.15",
        "tabulate>=0.9,<1.0",
        "pyarrow>=16.0,<20.0; python_version < '3.14'",
        "pyarrow>=23.0,<26.0; python_version >= '3.14'",
    ),
    "visualization": (
        "matplotlib>=3.8,<4.0",
        "plotly>=5.22,<6.0",
        "seaborn>=0.13,<0.14",
        "plotext>=5.2,<6.0",
    ),
    "pdf_export": (
        "reportlab>=4.0,<5.0",
        "fpdf2>=2.8,<3.0",
    ),
    "backup": ("cryptography>=42.0,<49.0",),
}
MANIFEST_SCHEMA = 2
OVERLAY_DIRECTORY = "environment"
MUTATION_LOCK_FILE = ".mutation.lock"
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_SAFE_COMPONENT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-!"
)
_HEX_CHARS = frozenset("0123456789abcdef")
_TEMP_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


class ExtrasError(RuntimeError):
    """Base error for optional-extras management."""


class ExtrasInstallError(ExtrasError):
    """Raised when pip cannot prepare an optional-extras overlay."""


@dataclass(frozen=True)
class ExtraStatus:
    """Current-runtime status for one supported extra group."""

    group: str
    state: str
    path: Path
    manifest: dict[str, Any] | None = None
    error: str | None = None

    @property
    def installed(self) -> bool:
        return self.state == "installed"

    @property
    def selected(self) -> bool:
        selected = self.manifest.get("selected_groups", []) if self.manifest else []
        return self.group in selected

    def as_dict(self) -> dict[str, Any]:
        """Return stable, JSON-serializable fields for CLI and doctor output."""

        return {
            "group": self.group,
            "state": self.state,
            "installed": self.installed,
            "selected": self.selected,
            "path": str(self.path),
            "manifest": self.manifest,
            "error": self.error,
        }


@dataclass(frozen=True)
class StaleOverlay:
    """An overlay directory that is not valid for this runtime."""

    path: Path
    indexly_version: str
    python_abi: str
    platform_tag: str
    groups: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return stable, JSON-serializable fields for status output."""

        return {
            "path": str(self.path),
            "indexly_version": self.indexly_version,
            "python_abi": self.python_abi,
            "platform_tag": self.platform_tag,
            "groups": list(self.groups),
            "reason": self.reason,
        }


def running_version() -> str:
    """Return the installed Indexly distribution version."""

    try:
        version = importlib.metadata.version("indexly")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ExtrasError(
            "Cannot manage extras because the running Indexly distribution "
            "metadata is unavailable."
        ) from exc
    return _validate_component(version, "Indexly version")


def python_abi() -> str:
    """Return the interpreter ABI tag used to scope overlays."""

    cache_tag = getattr(sys.implementation, "cache_tag", None)
    if not cache_tag:
        raise ExtrasError("Cannot determine the running Python ABI tag.")
    return _validate_component(cache_tag, "Python ABI tag")


def platform_tag() -> str:
    """Return the interpreter platform tag used to scope native wheels."""

    value = sysconfig.get_platform()
    if not value:
        raise ExtrasError("Cannot determine the running Python platform tag.")
    return _validate_component(value, "Python platform tag")


def overlay_root(
    *,
    base_dir: Path | None = None,
    version: str | None = None,
    abi: str | None = None,
    platform_name: str | None = None,
) -> Path:
    """Return the overlay scope for the current version, ABI, and platform."""

    safe_version = (
        running_version()
        if version is None
        else _validate_component(version, "Indexly version")
    )
    safe_abi = (
        python_abi() if abi is None else _validate_component(abi, "Python ABI tag")
    )
    safe_platform = (
        platform_tag()
        if platform_name is None
        else _validate_component(platform_name, "Python platform tag")
    )
    runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    return runtime_root / "extras" / safe_version / safe_abi / safe_platform


def group_overlay_path(group: str, *, base_dir: Path | None = None) -> Path:
    """Return the shared overlay path used by ``group``."""

    _validate_group(group)
    return _validated_scope(base_dir=base_dir, create=False) / OVERLAY_DIRECTORY


def activate_installed_extras(*, base_dir: Path | None = None) -> tuple[Path, ...]:
    """Append the valid shared overlay once without blocking core CLI startup."""

    original_paths = list(sys.path)
    try:
        path, manifest, error = _inspect_overlay(base_dir=base_dir)
        if manifest is None or error:
            return ()
        package_dir = path / "site-packages"
        package_path = str(package_dir)
        if package_path not in sys.path:
            sys.path.append(package_path)
        importlib.invalidate_caches()
        return (package_dir,)
    except Exception:
        sys.path[:] = original_paths
        return ()


def install_extra(group: str, *, base_dir: Path | None = None) -> ExtraStatus:
    """Select ``group`` and atomically rebuild the shared dependency union."""

    safe_group = _validate_group(group)
    with _mutation_lock(base_dir=base_dir):
        _recover_interrupted_swap(base_dir=base_dir)
        selected = list(_selected_groups_for_mutation(base_dir=base_dir))
        if safe_group not in selected:
            selected.append(safe_group)
        selected = [group for group in SUPPORTED_GROUPS if group in selected]
        _rebuild_overlay(tuple(selected), base_dir=base_dir)
        return extra_status(safe_group, base_dir=base_dir)


def uninstall_extra(group: str, *, base_dir: Path | None = None) -> bool:
    """Deselect ``group`` and rebuild the remaining shared dependency union."""

    safe_group = _validate_group(group)
    with _mutation_lock(base_dir=base_dir):
        _recover_interrupted_swap(base_dir=base_dir)
        selected = _selected_groups_for_mutation(base_dir=base_dir)
        if safe_group not in selected:
            return False
        remaining = tuple(group for group in selected if group != safe_group)
        if remaining:
            _rebuild_overlay(remaining, base_dir=base_dir)
        else:
            scope = _validated_scope(base_dir=base_dir, create=False)
            destination = scope / OVERLAY_DIRECTORY
            if destination.is_symlink():
                raise ExtrasError(
                    f"Refusing to remove symlinked overlay path: {destination}"
                )
            _remove_directory(destination, scope)
        return True


def reset_extras(*, base_dir: Path | None = None) -> bool:
    """Safely remove the current shared overlay without reading its manifest."""

    with _mutation_lock(base_dir=base_dir):
        _recover_interrupted_swap(base_dir=base_dir)
        scope = _validated_scope(base_dir=base_dir, create=False)
        destination = scope / OVERLAY_DIRECTORY
        if not destination.exists() and not destination.is_symlink():
            return False
        if destination.is_symlink():
            raise ExtrasError(
                f"Refusing to remove symlinked overlay path: {destination}"
            )
        _remove_directory(destination, scope)
        return True


def list_extras(*, base_dir: Path | None = None) -> tuple[ExtraStatus, ...]:
    """Return selection and validity status for every supported group."""

    path, manifest, error = _inspect_overlay(base_dir=base_dir)
    selected = _manifest_selected_groups(manifest)
    statuses: list[ExtraStatus] = []
    for group in SUPPORTED_GROUPS:
        is_selected = group in selected
        if error and (is_selected or not selected):
            state = "invalid"
            status_error = error
        else:
            state = "installed" if is_selected else "not-installed"
            status_error = None
        statuses.append(
            ExtraStatus(
                group=group,
                state=state,
                path=path,
                manifest=manifest,
                error=status_error,
            )
        )
    return tuple(statuses)


def extra_status(group: str, *, base_dir: Path | None = None) -> ExtraStatus:
    """Return shared-overlay selection status for ``group``."""

    safe_group = _validate_group(group)
    return next(
        status
        for status in list_extras(base_dir=base_dir)
        if status.group == safe_group
    )


def list_stale_overlays(*, base_dir: Path | None = None) -> tuple[StaleOverlay, ...]:
    """Report, but never activate or modify, overlays from older runtimes."""

    runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    extras_root = runtime_root / "extras"
    if extras_root.is_symlink():
        raise ExtrasError(f"Refusing to scan symlinked extras root: {extras_root}")
    if not extras_root.exists():
        return ()
    if not extras_root.is_dir():
        raise ExtrasError(f"Extras root is not a directory: {extras_root}")

    current_version = running_version()
    current_abi = python_abi()
    current_platform = platform_tag()
    stale: list[StaleOverlay] = []
    try:
        for version_dir in sorted(extras_root.iterdir(), key=lambda path: path.name):
            if version_dir.is_symlink() or not version_dir.is_dir():
                continue
            for abi_dir in sorted(version_dir.iterdir(), key=lambda path: path.name):
                if abi_dir.is_symlink() or not abi_dir.is_dir():
                    continue
                for platform_dir in sorted(
                    abi_dir.iterdir(), key=lambda path: path.name
                ):
                    if platform_dir.is_symlink() or not platform_dir.is_dir():
                        continue
                    if (
                        version_dir.name == current_version
                        and abi_dir.name == current_abi
                        and platform_dir.name == current_platform
                    ):
                        continue
                    stale_overlay = platform_dir / OVERLAY_DIRECTORY
                    if stale_overlay.is_symlink() or not stale_overlay.is_dir():
                        continue
                    groups = _read_stale_selected_groups(platform_dir)
                    reason = (
                        "indexly-version"
                        if version_dir.name != current_version
                        else (
                            "python-abi" if abi_dir.name != current_abi else "platform"
                        )
                    )
                    stale.append(
                        StaleOverlay(
                            path=stale_overlay,
                            indexly_version=version_dir.name,
                            python_abi=abi_dir.name,
                            platform_tag=platform_dir.name,
                            groups=groups,
                            reason=reason,
                        )
                    )
    except OSError as exc:
        raise ExtrasError(f"Could not inspect stale extras overlays: {exc}") from exc
    return tuple(stale)


def external_tools_status() -> dict[str, bool]:
    """Report external tools used by extras without attempting installation."""

    return {"tesseract": shutil.which("tesseract") is not None}


def _rebuild_overlay(
    selected_groups: tuple[str, ...], *, base_dir: Path | None
) -> None:
    version = running_version()
    abi = python_abi()
    platform_name = platform_tag()
    scope = _validated_scope(
        base_dir=base_dir,
        version=version,
        abi=abi,
        platform_name=platform_name,
        create=True,
    )
    destination = scope / OVERLAY_DIRECTORY
    staging = Path(tempfile.mkdtemp(prefix=".environment.staging-", dir=scope))
    package_dir = staging / "site-packages"
    package_dir.mkdir()
    requirements = _requirements_for_groups(selected_groups)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--target",
        str(package_dir),
        *requirements,
    ]

    try:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                shell=False,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = _subprocess_error_detail(exc)
            raise ExtrasInstallError(
                "Could not rebuild the optional-extras user overlay." + detail
            ) from exc

        manifest = {
            "schema": MANIFEST_SCHEMA,
            "selected_groups": list(selected_groups),
            "indexly_version": version,
            "python_abi": abi,
            "platform_tag": platform_name,
            "python_executable": sys.executable,
            "requirements_by_group": {
                group: list(EXTRA_REQUIREMENTS[group]) for group in selected_groups
            },
            "requested_requirements": list(requirements),
            "distributions": _distribution_inventory(package_dir),
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_manifest(staging / "manifest.json", manifest)
        verified_scope = _validated_scope(
            base_dir=base_dir,
            version=version,
            abi=abi,
            platform_name=platform_name,
            create=False,
        )
        if verified_scope != scope:
            raise ExtrasError("The extras overlay scope changed during installation.")
        _replace_directory(staging, destination, scope)
    finally:
        if staging.exists():
            try:
                _remove_directory(staging, scope)
            except ExtrasError:
                pass


def _recover_interrupted_swap(*, base_dir: Path | None) -> None:
    """Restore one validated backup left by an interrupted atomic swap."""

    scope = _validated_scope(base_dir=base_dir, create=False)
    destination = scope / OVERLAY_DIRECTORY
    backups = _remnant_candidates(scope, ".environment.backup-")
    staging = _remnant_candidates(scope, ".environment.staging-")

    if destination.exists() and not destination.is_symlink():
        _, error = _inspect_overlay_directory(destination)
        if error is None:
            _cleanup_safe_remnants(backups + staging, scope)
        return
    if destination.is_symlink():
        return
    if not backups:
        return
    if len(backups) != 1:
        raise ExtrasError(
            "Cannot recover extras overlay because multiple interrupted-swap "
            "backups exist."
        )

    backup = backups[0]
    if (
        not _is_owned_remnant_name(backup.name)
        or backup.is_symlink()
        or not backup.is_dir()
    ):
        raise ExtrasError(f"Cannot recover unsafe extras backup: {backup}")
    _, error = _inspect_overlay_directory(backup)
    if error:
        raise ExtrasError(f"Cannot recover invalid extras backup at {backup}: {error}")
    try:
        os.replace(backup, destination)
    except OSError as exc:
        raise ExtrasError(
            f"Could not restore interrupted extras backup: {exc}"
        ) from exc
    _cleanup_safe_remnants(staging, scope)


def _remnant_candidates(scope: Path, prefix: str) -> list[Path]:
    try:
        return sorted(
            (
                path
                for path in scope.iterdir()
                if path.name.startswith(prefix) and len(path.name) > len(prefix)
            ),
            key=lambda path: path.name,
        )
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise ExtrasError(f"Could not inspect extras recovery remnants: {exc}") from exc


def _cleanup_safe_remnants(paths: list[Path], scope: Path) -> None:
    for path in paths:
        if (
            not _is_owned_remnant_name(path.name)
            or path.is_symlink()
            or not path.is_dir()
        ):
            continue
        _remove_directory(path, scope)


def _is_owned_remnant_name(name: str) -> bool:
    backup_prefix = ".environment.backup-"
    staging_prefix = ".environment.staging-"
    if name.startswith(backup_prefix):
        suffix = name[len(backup_prefix) :]
        return len(suffix) == 32 and all(
            character in _HEX_CHARS for character in suffix
        )
    if name.startswith(staging_prefix):
        suffix = name[len(staging_prefix) :]
        return len(suffix) == 8 and all(
            character in _TEMP_CHARS for character in suffix
        )
    return False


@contextmanager
def _mutation_lock(*, base_dir: Path | None):
    """Hold an exclusive process- and thread-safe lock for the current scope."""

    scope = _validated_scope(base_dir=base_dir, create=True)
    lock_path = scope / MUTATION_LOCK_FILE
    thread_lock = _thread_lock_for(lock_path)
    with thread_lock:
        if lock_path.is_symlink():
            raise ExtrasError(f"Refusing symlinked extras mutation lock: {lock_path}")
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise ExtrasError(f"Could not open extras mutation lock: {exc}") from exc

        try:
            opened = os.fstat(descriptor)
            current = os.stat(lock_path, follow_symlinks=False)
            if (
                not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or opened.st_nlink != 1
                or current.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ExtrasError(
                    f"Extras mutation lock is not a safe regular file: {lock_path}"
                )
            _lock_descriptor(descriptor)
            try:
                yield
            finally:
                _unlock_descriptor(descriptor)
        finally:
            os.close(descriptor)


def _thread_lock_for(path: Path) -> threading.Lock:
    key = str(path.absolute())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


def _lock_descriptor(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        raise ExtrasError(f"Could not acquire extras mutation lock: {exc}") from exc


def _unlock_descriptor(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError as exc:
        raise ExtrasError(f"Could not release extras mutation lock: {exc}") from exc


def _inspect_overlay(
    *, base_dir: Path | None
) -> tuple[Path, dict[str, Any] | None, str | None]:
    scope = _validated_scope(base_dir=base_dir, create=False)
    path = scope / OVERLAY_DIRECTORY
    manifest, error = _inspect_overlay_directory(path)
    return path, manifest, error


def _inspect_overlay_directory(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    if path.is_symlink():
        return None, "Overlay path is a symlink."
    if not path.exists():
        return None, None
    if not path.is_dir():
        return None, "Overlay path is not a regular directory."

    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Manifest is unavailable or invalid: {exc}"
    if not isinstance(manifest, dict):
        return None, "Manifest must contain a JSON object."
    error = _validate_manifest(path, manifest)
    return manifest, error


def _validate_manifest(path: Path, manifest: dict[str, Any]) -> str | None:
    expected = {
        "schema": MANIFEST_SCHEMA,
        "indexly_version": running_version(),
        "python_abi": python_abi(),
        "platform_tag": platform_tag(),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        return (
            "Manifest does not match the running Indexly version, Python ABI, "
            "and platform."
        )

    selected = _manifest_selected_groups(manifest)
    raw_selected = manifest.get("selected_groups")
    if not selected or raw_selected != list(selected):
        return "Manifest selected groups are missing, unsupported, or out of order."
    requirements_by_group = {
        group: list(EXTRA_REQUIREMENTS[group]) for group in selected
    }
    if manifest.get("requirements_by_group") != requirements_by_group:
        return "Manifest group requirements do not match this Indexly version."
    if manifest.get("requested_requirements") != list(
        _requirements_for_groups(selected)
    ):
        return "Manifest union requirements do not match the selected groups."

    package_dir = path / "site-packages"
    if package_dir.is_symlink() or not package_dir.is_dir():
        return "Overlay site-packages directory is missing or unsafe."
    try:
        distributions = _distribution_inventory(package_dir)
    except ExtrasInstallError as exc:
        return str(exc)
    if manifest.get("distributions") != distributions:
        return "Installed distributions do not match the overlay manifest."
    return None


def _selected_groups_for_mutation(*, base_dir: Path | None) -> tuple[str, ...]:
    path, manifest, error = _inspect_overlay(base_dir=base_dir)
    if error:
        raise ExtrasError(f"Cannot modify invalid extras overlay at {path}: {error}")
    return _manifest_selected_groups(manifest)


def _manifest_selected_groups(
    manifest: dict[str, Any] | None,
) -> tuple[str, ...]:
    if not manifest:
        return ()
    value = manifest.get("selected_groups")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return ()
    return tuple(group for group in SUPPORTED_GROUPS if group in value)


def _requirements_for_groups(groups: tuple[str, ...]) -> tuple[str, ...]:
    requirements: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for requirement in EXTRA_REQUIREMENTS[group]:
            if requirement not in seen:
                requirements.append(requirement)
                seen.add(requirement)
    return tuple(requirements)


def _read_stale_selected_groups(platform_dir: Path) -> tuple[str, ...]:
    overlay = platform_dir / OVERLAY_DIRECTORY
    if overlay.is_symlink() or not overlay.is_dir():
        return ()
    manifest_path = overlay / "manifest.json"
    if manifest_path.is_symlink():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    return _manifest_selected_groups(manifest if isinstance(manifest, dict) else None)


def _validate_group(group: str) -> str:
    if group not in SUPPORTED_GROUPS:
        choices = ", ".join(SUPPORTED_GROUPS)
        raise ExtrasError(
            f"Unsupported extra group '{group}'. Choose one of: {choices}."
        )
    return group


def _validate_component(value: str, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or any(character not in _SAFE_COMPONENT_CHARS for character in value)
    ):
        raise ExtrasError(f"{label} is unsafe for an overlay path: {value!r}.")
    return value


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _validated_scope(
    *,
    base_dir: Path | None = None,
    version: str | None = None,
    abi: str | None = None,
    platform_name: str | None = None,
    create: bool,
) -> Path:
    """Return a scope whose managed ancestors are real directories, not links."""

    safe_version = (
        running_version()
        if version is None
        else _validate_component(version, "Indexly version")
    )
    safe_abi = (
        python_abi() if abi is None else _validate_component(abi, "Python ABI tag")
    )
    safe_platform = (
        platform_tag()
        if platform_name is None
        else _validate_component(platform_name, "Python platform tag")
    )
    runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    extras_root = runtime_root / "extras"
    version_root = extras_root / safe_version
    abi_root = version_root / safe_abi
    scope = abi_root / safe_platform

    if create:
        try:
            runtime_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExtrasError(
                f"Could not prepare the Indexly runtime directory: {exc}"
            ) from exc

    for path, label in (
        (extras_root, "extras root"),
        (version_root, "Indexly-version directory"),
        (abi_root, "Python-ABI directory"),
        (scope, "platform directory"),
    ):
        if path.is_symlink():
            raise ExtrasError(f"Refusing symlinked {label}: {path}")
        if path.exists() and not path.is_dir():
            raise ExtrasError(f"Extras {label} is not a directory: {path}")
        if create and not path.exists():
            try:
                path.mkdir(exist_ok=True)
            except OSError as exc:
                raise ExtrasError(f"Could not create {label} '{path}': {exc}") from exc
            if path.is_symlink() or not path.is_dir():
                raise ExtrasError(f"Could not safely create {label}: {path}")
    return scope


def _validate_scope_ancestors(scope: Path) -> None:
    for path, label in (
        (scope.parent.parent.parent, "extras root"),
        (scope.parent.parent, "Indexly-version directory"),
        (scope.parent, "Python-ABI directory"),
        (scope, "platform directory"),
    ):
        if path.is_symlink():
            raise ExtrasError(f"Refusing symlinked {label}: {path}")
        if not path.is_dir():
            raise ExtrasError(f"Extras {label} is not a directory: {path}")


def _replace_directory(staging: Path, destination: Path, scope: Path) -> None:
    _validate_scope_ancestors(scope)
    _require_direct_child(staging, scope)
    _require_direct_child(destination, scope)
    backup = scope / f".{destination.name}.backup-{uuid4().hex}"
    had_destination = destination.exists()
    if destination.is_symlink():
        raise ExtrasError(f"Refusing to replace symlinked overlay path: {destination}")
    if had_destination and not destination.is_dir():
        raise ExtrasError(
            f"Refusing to replace non-directory overlay path: {destination}"
        )

    try:
        if had_destination:
            os.replace(destination, backup)
        os.replace(staging, destination)
    except OSError as exc:
        if had_destination and backup.exists() and not destination.exists():
            try:
                os.replace(backup, destination)
            except OSError as rollback_exc:
                raise ExtrasError(
                    "Could not replace the extras overlay or restore the prior "
                    f"overlay. The prior data remains at {backup}: {rollback_exc}"
                ) from exc
        raise ExtrasError(
            f"Could not safely replace the extras overlay: {exc}"
        ) from exc
    if backup.exists():
        try:
            _remove_directory(backup, scope)
        except (ExtrasError, OSError):
            pass


def _remove_directory(path: Path, scope: Path) -> None:
    _validate_scope_ancestors(scope)
    _require_direct_child(path, scope)
    if path.is_symlink():
        raise ExtrasError(f"Refusing to remove symlinked overlay path: {path}")
    if path.exists():
        if not path.is_dir():
            raise ExtrasError(f"Refusing to remove non-directory overlay path: {path}")
        shutil.rmtree(path)


def _require_direct_child(path: Path, scope: Path) -> None:
    if path.parent != scope or path.name in {"", ".", ".."}:
        raise ExtrasError(f"Refusing unsafe extras path outside overlay scope: {path}")


def _subprocess_error_detail(exc: BaseException) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        output = (exc.stderr or exc.stdout or "").strip()
        if output:
            return f" pip reported: {output}"
    return f" {exc}"


def _distribution_inventory(package_dir: Path) -> list[dict[str, str]]:
    inventory: dict[tuple[str, str], dict[str, str]] = {}
    try:
        distributions = importlib.metadata.distributions(path=[str(package_dir)])
        for distribution in distributions:
            name = distribution.metadata.get("Name")
            version = distribution.version
            if not name or not version:
                continue
            inventory[(name.casefold(), version)] = {
                "name": name,
                "version": version,
            }
    except (OSError, UnicodeError) as exc:
        raise ExtrasInstallError(
            f"Could not inventory distributions in the staged overlay: {exc}"
        ) from exc
    return [
        inventory[key] for key in sorted(inventory, key=lambda item: (item[0], item[1]))
    ]
