from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest


def _read_project_version(project_root):
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_update_homebrew_tap_accepts_pypi_sdist_version_without_tag(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is required for the Homebrew tap update script")
    if shutil.which("bash") is None:
        pytest.skip("bash is required for the Homebrew tap update script")

    project_root = Path(__file__).resolve().parents[1]
    tap_repo = tmp_path / "homebrew-indexly"
    tap_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(tap_repo)], check=True)

    result = subprocess.run(
        [
            "bash",
            str(project_root / "scripts/update_homebrew_tap.sh"),
            "--tap-repo",
            str(tap_repo),
            "--dry-run",
        ],
        cwd=project_root,
        text=True,
        capture_output=True,
    )

    version = _read_project_version(project_root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        f"Formula source URL references {version} (tap tag v{version})" in result.stdout
    )
    assert (tap_repo / "Formula/indexly.rb").read_text(encoding="utf-8") == (
        project_root / "Formula/indexly.rb"
    ).read_text(encoding="utf-8")
