from pathlib import Path

from indexly.ignore import IgnoreRules
from indexly.ignore_defaults.loader import load_ignore_template


def _rules(preset: str) -> IgnoreRules:
    return IgnoreRules(load_ignore_template(preset).splitlines())


def test_standard_preset_ignores_office_lock_files(tmp_path: Path):
    lock_file = tmp_path / "~$-00151_931_adresse.docx"

    assert _rules("standard").should_ignore(lock_file, root=tmp_path)
    assert "~$*" in load_ignore_template("standard").splitlines()


def test_aggressive_preset_ignores_office_lock_files(tmp_path: Path):
    lock_file = tmp_path / "01_adresse" / "~$-00151_931_adresse.docx"

    assert _rules("aggressive").should_ignore(lock_file, root=tmp_path)


def test_minimal_preset_also_blocks_office_lock_files(tmp_path: Path):
    lock_file = tmp_path / "~$-00151_931_adresse.docx"

    assert _rules("minimal").should_ignore(lock_file, root=tmp_path)


def test_project_local_rules_also_block_office_lock_files(tmp_path: Path):
    lock_file = tmp_path / "01_adresse" / "~$-00151_931_adresse.docx"

    assert IgnoreRules(["*.log"]).should_ignore(lock_file, root=tmp_path)
