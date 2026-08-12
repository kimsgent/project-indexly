from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from indexly import cli_utils, extras_manager, optional_deps


def test_plain_library_import_does_not_mutate_sys_path(tmp_path) -> None:
    environment = os.environ.copy()
    environment["INDEXLY_HOME"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "before = list(sys.path); "
                "import indexly; "
                "print(json.dumps(before == sys.path))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert json.loads(result.stdout) is True


def test_parser_supports_extras_commands() -> None:
    parser = cli_utils.build_parser()

    install = parser.parse_args(["extras", "install", "documents"])
    status = parser.parse_args(["extras", "status", "analysis", "--json"])
    listing = parser.parse_args(["extras", "list"])
    uninstall = parser.parse_args(["extras", "uninstall", "backup"])
    reset = parser.parse_args(["extras", "reset"])

    assert (install.extras_action, install.group) == ("install", "documents")
    assert (status.extras_action, status.group, status.json) == (
        "status",
        "analysis",
        True,
    )
    assert listing.extras_action == "list"
    assert (uninstall.extras_action, uninstall.group) == ("uninstall", "backup")
    assert reset.extras_action == "reset"


def test_extras_list_json_is_serializable(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    status = extras_manager.ExtraStatus(
        group="documents",
        state="installed",
        path=tmp_path / "documents",
        manifest={
            "indexly_version": "2.1.6",
            "selected_groups": ["documents"],
        },
    )
    monkeypatch.setattr(extras_manager, "list_extras", lambda: (status,))
    monkeypatch.setattr(extras_manager, "list_stale_overlays", lambda: ())

    cli_utils._handle_extras(
        SimpleNamespace(extras_action="list", json=True, group=None)
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "current": [
            {
                "error": None,
                "group": "documents",
                "installed": True,
                "manifest": {
                    "indexly_version": "2.1.6",
                    "selected_groups": ["documents"],
                },
                "path": str(tmp_path / "documents"),
                "selected": True,
                "state": "installed",
            }
        ],
        "stale": [],
    }


def test_extras_install_reports_tesseract_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    status = extras_manager.ExtraStatus(
        group="documents",
        state="installed",
        path=tmp_path / "documents",
    )
    monkeypatch.setattr(extras_manager, "install_extra", lambda group: status)
    monkeypatch.setattr(
        extras_manager,
        "external_tools_status",
        lambda: {"tesseract": False},
    )

    cli_utils._handle_extras(
        SimpleNamespace(extras_action="install", group="documents", json=False)
    )

    output = capsys.readouterr().out
    assert "Installed 'documents' extras" in output
    assert "brew install tesseract" in output
    assert "Regular document extraction is available" in output


def test_extras_reset_reports_recovery_command(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(extras_manager, "reset_extras", lambda: True)

    cli_utils._handle_extras(
        SimpleNamespace(extras_action="reset", group=None, json=False)
    )

    output = capsys.readouterr().out
    assert "Removed all managed extras" in output
    assert "indexly extras install <pack>" in output


def test_extras_manager_errors_are_user_facing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_group: str):
        raise extras_manager.ExtrasInstallError("download failed")

    monkeypatch.setattr(extras_manager, "install_extra", fail)

    with pytest.raises(ValueError, match="download failed"):
        cli_utils._handle_extras(
            SimpleNamespace(extras_action="install", group="analysis", json=False)
        )


def test_optional_dependency_hint_uses_supported_extras_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_module_name: str):
        raise ModuleNotFoundError("missing")

    monkeypatch.setattr(optional_deps.importlib, "import_module", missing)

    with pytest.raises(RuntimeError) as exc_info:
        optional_deps.require_extra_dependency(
            "fitz",
            "pymupdf",
            "documents",
        )

    message = str(exc_info.value)
    assert "indexly extras install documents" in message
    assert 'python -m pip install "indexly[documents]"' in message
    assert "pip/virtualenv installation only" in message


def test_lazy_dependency_hint_is_shell_safe() -> None:
    exc = ModuleNotFoundError("missing")
    exc.name = "pandas"

    message = cli_utils._missing_dependency_message(exc, "analysis")

    assert message.startswith(
        "Missing optional dependency 'pandas'. "
        "Install with: indexly extras install analysis."
    )
    assert 'python -m pip install "indexly[analysis]"' in message
