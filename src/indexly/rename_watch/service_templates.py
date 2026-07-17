"""Safe rendering of packaged service-manager templates."""

from __future__ import annotations

import html
import math
import os
import re
import sys
from importlib import resources
from pathlib import Path

from indexly.runtime_paths import resolve_base_dir

from .config import RenameWatchConfigError, load_settings
from .error_contract import RenameWatchUsageError

_RESOURCES = {
    "windows": "templates/windows/indexly-rename-watch.xml.in",
    "systemd": "templates/systemd/indexly-rename-watch.service.in",
    "launchd": "templates/launchd/com.projectindexly.rename-watch.plist.in",
    "launchd-newsyslog": "templates/launchd/indexly-rename-watch.newsyslog.conf.in",
}
_REQUIRED_ACCOUNTS = {
    "windows": (True, False),
    "systemd": (True, True),
    "launchd": (True, True),
    "launchd-newsyslog": (True, True),
}
_TOKEN = re.compile(r"@@[A-Z0-9_]+@@")
_POSIX_ACCOUNT = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
_WINDOWS_GMSA = re.compile(r"[^\\/]+\\[^\\/]+\$\Z")


def _clean(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RenameWatchUsageError("{0} is required".format(name))
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise RenameWatchConfigError("{0} contains a control character".format(name))
    if _TOKEN.search(value):
        raise RenameWatchConfigError("{0} contains an unexpanded placeholder".format(name))
    return value


def _systemd_escape(value: str) -> str:
    safe = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-:@")
    escaped = []
    for character in value:
        if character == "%":
            escaped.append("%%")
        elif character == "$":
            escaped.append("$$")
        elif character in safe:
            escaped.append(character)
        elif ord(character) < 128:
            escaped.append("\\x{0:02x}".format(ord(character)))
        else:
            escaped.append(character)
    return "".join(escaped)


def _render_value(platform: str, value: str, name: str) -> str:
    value = _clean(value, name)
    if platform == "windows":
        if "%" in value:
            raise RenameWatchConfigError(
                "{0} cannot contain percent expansion syntax for WinSW".format(name)
            )
        return html.escape(value, quote=True)
    if platform == "launchd":
        return html.escape(value, quote=True)
    if platform == "systemd":
        return _systemd_escape(value)
    if any(character.isspace() for character in value) or "#" in value:
        raise RenameWatchConfigError(
            "{0} cannot be represented safely in newsyslog fields".format(name)
        )
    return value


def render_service_template(
    config_path: str,
    *,
    platform: str,
    service_user: str = None,
    service_group: str = None,
) -> str:
    if platform not in _RESOURCES:
        raise RenameWatchUsageError("unsupported service template platform")
    needs_user, needs_group = _REQUIRED_ACCOUNTS[platform]
    if needs_user and service_user is None:
        raise RenameWatchUsageError("--service-user is required for {0}".format(platform))
    if needs_group and service_group is None:
        raise RenameWatchUsageError("--service-group is required for {0}".format(platform))
    if platform != "windows":
        for value, name in ((service_user, "--service-user"), (service_group, "--service-group")):
            if value is not None and not _POSIX_ACCOUNT.fullmatch(value):
                raise RenameWatchConfigError("{0} is not a safe POSIX account name".format(name))
    elif (
        service_user.casefold() != "nt authority\\localservice"
        and not _WINDOWS_GMSA.fullmatch(service_user)
    ):
        raise RenameWatchConfigError(
            "--service-user must be NT AUTHORITY\\LocalService or a DOMAIN\\account$ gMSA"
        )

    settings = load_settings(config_path)
    indexly_home = resolve_base_dir().expanduser().resolve()
    python_executable = Path(sys.executable).expanduser().resolve()
    values = {
        "@@PYTHON_EXECUTABLE@@": os.fspath(python_executable),
        "@@CONFIG_PATH@@": os.fspath(settings.config_path),
        "@@INDEXLY_HOME@@": os.fspath(indexly_home),
        "@@SERVICE_USER@@": service_user or "",
        "@@SERVICE_GROUP@@": service_group or "",
        "@@SERVICE_LOG_DIR@@": os.fspath(indexly_home / "service-logs"),
        "@@MANAGER_STOP_TIMEOUT_SECONDS@@": str(
            int(math.ceil(settings.service.shutdown_drain_timeout_seconds + 10.0))
        ),
    }
    package_root = resources.files("indexly.rename_watch")
    template = package_root.joinpath(_RESOURCES[platform]).read_text(encoding="utf-8")
    rendered = template
    for token, value in values.items():
        if token in rendered:
            rendered = rendered.replace(token, _render_value(platform, value, token))
    if _TOKEN.search(rendered):
        raise RenameWatchConfigError("service template contains an unexpanded placeholder")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in rendered):
        raise RenameWatchConfigError("service template contains a control character")
    return rendered


def export_service_template(
    config_path: str,
    *,
    platform: str,
    output: str,
    service_user: str = None,
    service_group: str = None,
) -> int:
    if output is None:
        raise RenameWatchUsageError("--output is required with --export-service-template")
    rendered = render_service_template(
        config_path,
        platform=platform,
        service_user=service_user,
        service_group=service_group,
    )
    target = Path(output).expanduser().resolve()
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    except FileExistsError as exc:
        raise RenameWatchConfigError("service template output already exists: {0}".format(target)) from exc
    except OSError as exc:
        raise RenameWatchConfigError("service template could not be written: {0} ({1})".format(target, exc)) from exc
    print("Exported rename-watch service template: {0}".format(target))
    return 0


__all__ = ["export_service_template", "render_service_template"]
