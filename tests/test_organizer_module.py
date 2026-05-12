from pathlib import Path

from indexly.cli_utils import build_parser
from indexly.organize.organizer_exec import (
    execute_organizer,
    execute_profile_placement,
    execute_profile_scaffold,
)


def test_execute_organizer_handles_empty_folder_without_crashing(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    plan, backup_mapping = execute_organizer(root, dry_run=True)

    assert plan["files"] == []
    assert backup_mapping == {}


def test_legacy_organizer_dry_run_does_not_create_target_dirs(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "report.txt").write_text("content", encoding="utf-8")

    plan, _ = execute_organizer(root, dry_run=True)

    assert len(plan["files"]) == 1
    assert not (root / "document").exists()
    assert not (root / "log").exists()


def test_media_scaffold_dry_run_has_no_filesystem_side_effects(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    execute_profile_scaffold(root, "media", shoot_name="ClientShoot", dry_run=True)

    assert not (root / "Media").exists()
    assert not (root / "Shoots").exists()
    assert not (root / "log").exists()


def test_profile_classification_preview_writes_no_folders_or_logs(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "invoice_2026_unpaid.pdf").write_text("invoice", encoding="utf-8")

    plan = execute_profile_placement(
        source_root=root,
        destination_root=root,
        profile="business",
        category="solo",
        executed_by="pytest",
        apply=False,
        dry_run=False,
    )

    assert len(plan) == 1
    assert not (root / "Business").exists()
    assert not (root / "log").exists()


def test_backup_is_copied_before_move_using_original_relative_path(tmp_path):
    root = tmp_path / "workspace"
    backup_root = tmp_path / "backup"
    root.mkdir()
    source = root / "report.txt"
    source.write_text("important", encoding="utf-8")

    plan, backup_mapping = execute_organizer(root, backup_root=backup_root)

    destination = Path(plan["files"][0]["new_path"])
    assert destination.exists()
    assert not source.exists()
    assert (backup_root / "report.txt").read_text(encoding="utf-8") == "important"
    assert backup_mapping[str(source)] == str(backup_root / "report.txt")


def test_organizer_marks_content_duplicates_in_plan(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "alpha.txt").write_text("same", encoding="utf-8")
    (root / "beta.txt").write_text("same", encoding="utf-8")

    plan, _ = execute_organizer(root, dry_run=True)

    assert plan["summary"]["duplicates"] == 2
    assert all(entry["duplicate"] for entry in plan["files"])
    assert all(entry["hash"] for entry in plan["files"])


def test_researcher_and_engineer_profiles_have_classification_rules(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    research_file = root / "raw_experiment.csv"
    engineering_file = root / "bracket.step"
    research_file.write_text("x,y\n1,2\n", encoding="utf-8")
    engineering_file.write_text("cad", encoding="utf-8")

    research_plan = execute_profile_placement(
        source_root=root,
        destination_root=root,
        profile="researcher",
        executed_by="pytest",
        apply=False,
        dry_run=True,
    )
    engineering_plan = execute_profile_placement(
        source_root=root,
        destination_root=root,
        profile="engineer",
        executed_by="pytest",
        apply=False,
        dry_run=True,
    )

    assert any("Research" in entry["destination"] for entry in research_plan)
    assert any("Research/Data/Raw" in entry["destination"].replace("\\", "/") for entry in research_plan)
    assert any("Engineering/CAD" in entry["destination"].replace("\\", "/") for entry in engineering_plan)


def test_cli_help_choices_include_classifiable_profiles_for_organize_and_rename():
    parser = build_parser()

    organize_args = parser.parse_args(["organize", ".", "--profile", "engineer", "--classify"])
    rename_args = parser.parse_args(["rename-file", ".", "--organize", "--profile", "media"])

    assert organize_args.profile == "engineer"
    assert rename_args.profile == "media"
