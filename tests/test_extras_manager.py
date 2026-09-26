from __future__ import annotations

import json
import subprocess
import sys
import threading
import tomllib
from pathlib import Path

import pytest

from indexly import extras_manager


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(extras_manager, "resolve_base_dir", lambda: tmp_path)
    monkeypatch.setattr(extras_manager, "running_version", lambda: "2.1.6")
    monkeypatch.setattr(extras_manager, "python_abi", lambda: "cpython-313")
    monkeypatch.setattr(extras_manager, "platform_tag", lambda: "macosx-15-arm64")
    return tmp_path


def _scope(
    runtime: Path,
    *,
    version: str = "2.1.6",
    abi: str = "cpython-313",
    platform: str = "macosx-15-arm64",
) -> Path:
    return runtime / "extras" / version / abi / platform


def _write_distribution(package_dir: Path, name: str, version: str = "1.0") -> None:
    metadata = package_dir / f"{name.replace('-', '_')}-{version}.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        encoding="utf-8",
    )


def _create_overlay(
    runtime: Path,
    groups: tuple[str, ...] = ("documents",),
    *,
    version: str = "2.1.6",
    abi: str = "cpython-313",
    platform: str = "macosx-15-arm64",
) -> Path:
    path = (
        _scope(runtime, version=version, abi=abi, platform=platform)
        / extras_manager.OVERLAY_DIRECTORY
    )
    package_dir = path / "site-packages"
    package_dir.mkdir(parents=True)
    for group in groups:
        _write_distribution(package_dir, f"{group}-dependency")
    requirements = extras_manager._requirements_for_groups(groups)
    manifest = {
        "schema": extras_manager.MANIFEST_SCHEMA,
        "selected_groups": list(groups),
        "indexly_version": version,
        "python_abi": abi,
        "platform_tag": platform,
        "requirements_by_group": {
            group: list(extras_manager.EXTRA_REQUIREMENTS[group]) for group in groups
        },
        "requested_requirements": list(requirements),
        "distributions": extras_manager._distribution_inventory(package_dir),
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _fake_pip(
    commands: list[list[str]], distribution_name: str = "resolved-dependency"
):
    def run(command: list[str], **kwargs: object) -> None:
        commands.append(command)
        assert kwargs == {
            "check": True,
            "capture_output": True,
            "text": True,
            "shell": False,
        }
        target = Path(command[command.index("--target") + 1])
        _write_distribution(target, distribution_name, "4.5.6")

    return run


def test_activation_appends_shared_overlay_once_and_retains_core_precedence(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents", "analysis"))
    original = ["core-first", "core-second"]
    monkeypatch.setattr(sys, "path", original.copy())
    invalidations: list[bool] = []
    monkeypatch.setattr(
        extras_manager.importlib,
        "invalidate_caches",
        lambda: invalidations.append(True),
    )

    first = extras_manager.activate_installed_extras()
    second = extras_manager.activate_installed_extras()

    assert first == (overlay / "site-packages",)
    assert second == first
    assert sys.path == original + [str(overlay / "site-packages")]
    assert invalidations == [True, True]


def test_activation_ignores_stale_overlay(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_overlay(runtime, version="2.1.5")
    original = sys.path.copy()
    monkeypatch.setattr(sys, "path", original.copy())

    assert extras_manager.activate_installed_extras() == ()
    assert sys.path == original


def test_install_builds_manifest_for_selected_group(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(extras_manager.subprocess, "run", _fake_pip(commands))

    status = extras_manager.install_extra("analysis")

    assert status.installed
    assert status.selected
    assert len(commands) == 1
    assert commands[0][:5] == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
    ]
    assert commands[0][7:] == list(extras_manager.EXTRA_REQUIREMENTS["analysis"])
    assert status.path.name == "environment"
    assert status.manifest is not None
    assert status.manifest["selected_groups"] == ["analysis"]
    assert status.manifest["requested_requirements"] == list(
        extras_manager.EXTRA_REQUIREMENTS["analysis"]
    )
    assert status.manifest["distributions"] == [
        {"name": "resolved-dependency", "version": "4.5.6"}
    ]


def test_install_second_group_rebuilds_one_union_overlay(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = _create_overlay(runtime, ("documents",))
    commands: list[list[str]] = []
    monkeypatch.setattr(extras_manager.subprocess, "run", _fake_pip(commands))

    status = extras_manager.install_extra("analysis")

    expected_groups = ("documents", "analysis")
    expected_requirements = extras_manager._requirements_for_groups(expected_groups)
    assert status.installed
    assert status.manifest is not None
    assert status.manifest["selected_groups"] == list(expected_groups)
    assert commands[0][7:] == list(expected_requirements)
    assert existing == status.path
    assert not (existing.parent / "documents").exists()
    assert not (existing.parent / "analysis").exists()
    installed = {item.group for item in extras_manager.list_extras() if item.installed}
    assert installed == {"documents", "analysis"}


def test_concurrent_installs_serialize_selection_and_preserve_union(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_pip_started = threading.Event()
    release_first_pip = threading.Event()
    second_pip_started = threading.Event()
    second_install_started = threading.Event()
    call_guard = threading.Lock()
    call_count = 0
    errors: list[BaseException] = []

    def controlled_pip(command: list[str], **kwargs: object) -> None:
        nonlocal call_count
        with call_guard:
            call_number = call_count
            call_count += 1
        if call_number == 0:
            first_pip_started.set()
            assert release_first_pip.wait(timeout=3)
        else:
            second_pip_started.set()
        target = Path(command[command.index("--target") + 1])
        _write_distribution(target, f"resolved-{call_number}", "1.0")

    def install(group: str) -> None:
        try:
            if group == "analysis":
                second_install_started.set()
            extras_manager.install_extra(group)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(extras_manager.subprocess, "run", controlled_pip)
    documents_thread = threading.Thread(target=install, args=("documents",))
    analysis_thread = threading.Thread(target=install, args=("analysis",))

    documents_thread.start()
    assert first_pip_started.wait(timeout=3)
    analysis_thread.start()
    assert second_install_started.wait(timeout=3)
    assert not second_pip_started.wait(timeout=0.2)
    release_first_pip.set()
    documents_thread.join(timeout=3)
    analysis_thread.join(timeout=3)

    assert not documents_thread.is_alive()
    assert not analysis_thread.is_alive()
    assert errors == []
    assert second_pip_started.is_set()
    manifest = extras_manager.extra_status("analysis").manifest
    assert manifest is not None
    assert manifest["selected_groups"] == ["documents", "analysis"]
    assert set(manifest["requested_requirements"]) == set(
        extras_manager._requirements_for_groups(("documents", "analysis"))
    )


def test_install_selected_group_rebuilds_for_repair(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("backup",))
    commands: list[list[str]] = []
    monkeypatch.setattr(extras_manager.subprocess, "run", _fake_pip(commands))

    assert extras_manager.install_extra("backup").installed
    assert len(commands) == 1
    assert commands[0][7:] == list(extras_manager.EXTRA_REQUIREMENTS["backup"])
    assert not (overlay / "site-packages" / "backup_dependency-1.0.dist-info").exists()


def test_uninstall_rebuilds_union_for_remaining_groups(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents", "analysis"))
    commands: list[list[str]] = []
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        _fake_pip(commands, "analysis-only"),
    )

    assert extras_manager.uninstall_extra("documents") is True

    assert commands[0][7:] == list(extras_manager.EXTRA_REQUIREMENTS["analysis"])
    assert overlay.exists()
    assert extras_manager.extra_status("documents").state == "not-installed"
    assert extras_manager.extra_status("analysis").installed
    manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["selected_groups"] == ["analysis"]


def test_uninstall_last_group_safely_removes_environment(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("backup",))
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip should not run"),
    )

    assert extras_manager.uninstall_extra("backup") is True
    assert not overlay.exists()
    assert extras_manager.uninstall_extra("backup") is False


def test_reset_removes_invalid_environment_without_reading_manifest(
    runtime: Path,
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    (overlay / "manifest.json").write_text("{broken", encoding="utf-8")

    assert extras_manager.extra_status("documents").state == "invalid"
    assert extras_manager.reset_extras() is True
    assert not overlay.exists()
    assert extras_manager.reset_extras() is False


def test_pip_failure_rolls_back_to_existing_union(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    marker = overlay / "site-packages" / "keep.txt"
    marker.write_text("old", encoding="utf-8")

    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, args[0], stderr="network unavailable")

    monkeypatch.setattr(extras_manager.subprocess, "run", fail)

    with pytest.raises(extras_manager.ExtrasInstallError, match="network unavailable"):
        extras_manager.install_extra("analysis")

    assert marker.read_text(encoding="utf-8") == "old"
    assert extras_manager.extra_status("documents").installed
    assert not list(overlay.parent.glob(".environment.staging-*"))
    lock_path = overlay.parent / extras_manager.MUTATION_LOCK_FILE
    assert lock_path.is_file()


def test_next_install_recovers_interrupted_swap_and_preserves_selection(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    backup = overlay.parent / f".environment.backup-{'a' * 32}"
    extras_manager.os.replace(overlay, backup)
    commands: list[list[str]] = []
    monkeypatch.setattr(extras_manager.subprocess, "run", _fake_pip(commands))

    status = extras_manager.install_extra("analysis")

    assert status.manifest is not None
    assert status.manifest["selected_groups"] == ["documents", "analysis"]
    assert commands[0][7:] == list(
        extras_manager._requirements_for_groups(("documents", "analysis"))
    )
    assert overlay.is_dir()
    assert not backup.exists()


def test_reset_recovers_interrupted_swap_before_removal(runtime: Path) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    backup = overlay.parent / f".environment.backup-{'c' * 32}"
    extras_manager.os.replace(overlay, backup)

    assert extras_manager.reset_extras() is True
    assert not overlay.exists()
    assert not backup.exists()


def test_recovery_refuses_invalid_interrupted_backup(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    backup = overlay.parent / f".environment.backup-{'b' * 32}"
    extras_manager.os.replace(overlay, backup)
    (backup / "manifest.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    with pytest.raises(extras_manager.ExtrasError, match="invalid extras backup"):
        extras_manager.install_extra("analysis")

    assert not overlay.exists()
    assert backup.exists()


def test_recovery_refuses_multiple_interrupted_backups(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_overlay = _create_overlay(runtime, ("documents",))
    first_backup = first_overlay.parent / f".environment.backup-{'1' * 32}"
    extras_manager.os.replace(first_overlay, first_backup)
    second_overlay = _create_overlay(runtime, ("analysis",))
    second_backup = second_overlay.parent / f".environment.backup-{'2' * 32}"
    extras_manager.os.replace(second_overlay, second_backup)
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    with pytest.raises(extras_manager.ExtrasError, match="multiple.*backups"):
        extras_manager.install_extra("backup")

    assert first_backup.exists()
    assert second_backup.exists()


def test_valid_environment_cleans_only_safe_owned_remnants(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    backup = overlay.parent / f".environment.backup-{'c' * 32}"
    staging = overlay.parent / ".environment.staging-abcd1234"
    backup.mkdir()
    staging.mkdir()
    similarly_named = overlay.parent / ".environment.backup-user-data"
    similarly_named.mkdir()
    outside = runtime / "outside-remnant"
    outside.mkdir()
    unsafe = overlay.parent / f".environment.backup-{'d' * 32}"
    try:
        unsafe.symlink_to(outside, target_is_directory=True)
    except OSError:
        unsafe = None
    commands: list[list[str]] = []
    monkeypatch.setattr(extras_manager.subprocess, "run", _fake_pip(commands))

    extras_manager.install_extra("analysis")

    assert not backup.exists()
    assert not staging.exists()
    assert similarly_named.exists()
    assert outside.exists()
    if unsafe is not None:
        assert unsafe.is_symlink()


def test_swap_failure_restores_existing_union(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    marker = overlay / "site-packages" / "keep.txt"
    marker.write_text("old", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(extras_manager.subprocess, "run", _fake_pip(commands))
    real_replace = extras_manager.os.replace

    def fail_new_environment(source: Path | str, destination: Path | str) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            source_path.name.startswith(".environment.staging-")
            and destination_path.name == "environment"
        ):
            raise OSError("simulated swap failure")
        real_replace(source, destination)

    monkeypatch.setattr(extras_manager.os, "replace", fail_new_environment)

    with pytest.raises(extras_manager.ExtrasError, match="safely replace"):
        extras_manager.install_extra("analysis")

    assert marker.read_text(encoding="utf-8") == "old"
    assert extras_manager.extra_status("documents").installed


def test_status_validates_union_requirements_and_inventory(runtime: Path) -> None:
    overlay = _create_overlay(runtime, ("visualization", "pdf_export"))
    manifest_path = overlay / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requested_requirements"] = ["unexpected-package"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    statuses = extras_manager.list_extras()

    assert extras_manager.extra_status("visualization").state == "invalid"
    assert (
        next(item for item in statuses if item.group == "pdf_export").state == "invalid"
    )
    assert next(item for item in statuses if item.group == "backup").state == (
        "not-installed"
    )

    manifest["requested_requirements"] = list(
        extras_manager._requirements_for_groups(("visualization", "pdf_export"))
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _write_distribution(overlay / "site-packages", "unexpected", "9.9")
    assert extras_manager.extra_status("visualization").state == "invalid"
    assert "distributions" in (extras_manager.extra_status("visualization").error or "")


def test_status_is_json_serializable_and_reports_selection(runtime: Path) -> None:
    _create_overlay(runtime, ("documents",))

    installed = extras_manager.extra_status("documents").as_dict()
    missing = extras_manager.extra_status("backup").as_dict()

    assert installed["selected"] is True
    assert installed["installed"] is True
    assert missing["selected"] is False
    assert missing["state"] == "not-installed"
    json.dumps(installed)
    json.dumps(missing)


def test_stale_report_reads_selected_groups_from_shared_manifest(
    runtime: Path, tmp_path: Path
) -> None:
    old_version = _create_overlay(runtime, ("documents", "backup"), version="2.1.5")
    old_abi = _create_overlay(runtime, ("analysis",), abi="cpython-312")
    old_platform = _create_overlay(
        runtime, ("pdf_export",), platform="macosx-15-x86_64"
    )
    outside = tmp_path / "outside-stale"
    outside.mkdir()
    symlink = _scope(runtime, version="2.1.4") / "environment"
    symlink.parent.mkdir(parents=True)
    try:
        symlink.symlink_to(outside, target_is_directory=True)
    except OSError:
        pass

    stale = extras_manager.list_stale_overlays()

    assert [item.as_dict() for item in stale] == [
        {
            "path": str(old_version),
            "indexly_version": "2.1.5",
            "python_abi": "cpython-313",
            "platform_tag": "macosx-15-arm64",
            "groups": ["documents", "backup"],
            "reason": "indexly-version",
        },
        {
            "path": str(old_abi),
            "indexly_version": "2.1.6",
            "python_abi": "cpython-312",
            "platform_tag": "macosx-15-arm64",
            "groups": ["analysis"],
            "reason": "python-abi",
        },
        {
            "path": str(old_platform),
            "indexly_version": "2.1.6",
            "python_abi": "cpython-313",
            "platform_tag": "macosx-15-x86_64",
            "groups": ["pdf_export"],
            "reason": "platform",
        },
    ]
    assert outside.exists()


def test_stale_report_ignores_lock_only_scope(runtime: Path) -> None:
    stale_scope = _scope(runtime, version="2.1.5")
    stale_scope.mkdir(parents=True)
    (stale_scope / extras_manager.MUTATION_LOCK_FILE).touch()

    assert extras_manager.list_stale_overlays() == ()


@pytest.mark.parametrize("ancestor", ["extras", "version", "abi", "platform"])
def test_managed_operations_refuse_symlinked_ancestors(
    runtime: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ancestor: str,
) -> None:
    extras_root = runtime / "extras"
    version_root = extras_root / "2.1.6"
    abi_root = version_root / "cpython-313"
    platform_root = abi_root / "macosx-15-arm64"
    paths = {
        "extras": extras_root,
        "version": version_root,
        "abi": abi_root,
        "platform": platform_root,
    }
    symlink_path = paths[ancestor]
    symlink_path.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / f"outside-{ancestor}"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")
    try:
        symlink_path.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    with pytest.raises(extras_manager.ExtrasError, match="symlinked"):
        extras_manager.extra_status("documents")
    with pytest.raises(extras_manager.ExtrasError, match="symlinked"):
        extras_manager.install_extra("documents")
    with pytest.raises(extras_manager.ExtrasError, match="symlinked"):
        extras_manager.uninstall_extra("documents")
    with pytest.raises(extras_manager.ExtrasError, match="symlinked"):
        extras_manager.reset_extras()
    assert extras_manager.activate_installed_extras() == ()
    assert marker.read_text(encoding="utf-8") == "unchanged"


def test_managed_operations_refuse_symlinked_environment(
    runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _scope(runtime)
    scope.mkdir(parents=True)
    outside = tmp_path / "outside-environment"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")
    environment = scope / extras_manager.OVERLAY_DIRECTORY
    try:
        environment.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    assert extras_manager.extra_status("documents").state == "invalid"
    with pytest.raises(extras_manager.ExtrasError, match="invalid extras overlay"):
        extras_manager.install_extra("documents")
    with pytest.raises(extras_manager.ExtrasError, match="invalid extras overlay"):
        extras_manager.uninstall_extra("documents")
    with pytest.raises(extras_manager.ExtrasError, match="symlinked overlay"):
        extras_manager.reset_extras()
    assert extras_manager.activate_installed_extras() == ()
    assert marker.read_text(encoding="utf-8") == "unchanged"


def test_mutation_refuses_symlinked_lock(
    runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _scope(runtime)
    scope.mkdir(parents=True)
    outside = tmp_path / "outside-lock"
    outside.mkdir()
    lock_path = scope / extras_manager.MUTATION_LOCK_FILE
    try:
        lock_path.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    with pytest.raises(extras_manager.ExtrasError, match="symlinked.*lock"):
        extras_manager.install_extra("documents")
    assert outside.exists()


def test_preexisting_unlocked_regular_lock_file_allows_recovery(
    runtime: Path,
) -> None:
    overlay = _create_overlay(runtime, ("documents",))
    (overlay / "manifest.json").write_text("{broken", encoding="utf-8")
    lock_path = overlay.parent / extras_manager.MUTATION_LOCK_FILE
    lock_path.touch()

    assert extras_manager.reset_extras() is True
    assert not overlay.exists()
    assert lock_path.is_file()


def test_mutation_refuses_nonregular_lock(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _scope(runtime)
    scope.mkdir(parents=True)
    (scope / extras_manager.MUTATION_LOCK_FILE).mkdir()
    monkeypatch.setattr(
        extras_manager.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    with pytest.raises(extras_manager.ExtrasError, match="mutation lock"):
        extras_manager.install_extra("documents")


@pytest.mark.parametrize("group", ["", "Documents", "../backup", "unknown"])
def test_group_validation_rejects_unsafe_or_unknown_values(
    runtime: Path, group: str
) -> None:
    with pytest.raises(extras_manager.ExtrasError, match="Unsupported extra group"):
        extras_manager.extra_status(group)


def test_extra_requirements_match_pyproject() -> None:
    with (Path(__file__).parents[1] / "pyproject.toml").open("rb") as pyproject_file:
        optional_dependencies = tomllib.load(pyproject_file)["project"][
            "optional-dependencies"
        ]
    assert {
        group: list(requirements)
        for group, requirements in extras_manager.EXTRA_REQUIREMENTS.items()
    } == optional_dependencies
    assert tuple(extras_manager.EXTRA_REQUIREMENTS) == extras_manager.SUPPORTED_GROUPS


def test_external_tesseract_is_status_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        extras_manager.shutil, "which", lambda name: "/usr/bin/tesseract"
    )
    assert extras_manager.external_tools_status() == {"tesseract": True}
