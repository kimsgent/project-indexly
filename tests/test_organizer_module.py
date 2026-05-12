from pathlib import Path

from indexly.cli_utils import build_parser
from indexly.organize.cli_wrapper import handle_organize
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


def test_data_project_name_is_used_as_safe_project_folder(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "raw_measurements.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    plan = execute_profile_placement(
        source_root=root,
        destination_root=root,
        profile="data",
        project_name="Bridge Study",
        executed_by="pytest",
        apply=False,
        dry_run=True,
    )

    destination = plan[0]["destination"].replace("\\", "/")
    assert "Data/Projects/Bridge Study/Data/Raw/raw_measurements.csv" in destination


def test_profile_name_segments_reject_paths(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "raw.csv").write_text("x", encoding="utf-8")

    try:
        execute_profile_placement(
            source_root=root,
            destination_root=root,
            profile="data",
            project_name="../escape",
            executed_by="pytest",
            apply=False,
            dry_run=True,
        )
    except ValueError as exc:
        assert "--project-name must be a name" in str(exc)
    else:
        raise AssertionError("expected path-like project name to fail")


def test_health_patient_id_scaffold_rejects_path_segments(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    try:
        execute_profile_scaffold(root, "health", patient_id="../patient", dry_run=True)
    except ValueError as exc:
        assert "--patient-id must be a name" in str(exc)
    else:
        raise AssertionError("expected path-like patient id to fail")


def test_media_shoot_name_scaffold_rejects_path_segments(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    try:
        execute_profile_scaffold(root, "media", shoot_name="client/escape", dry_run=True)
    except ValueError as exc:
        assert "--shoot-name must be a name" in str(exc)
    else:
        raise AssertionError("expected path-like shoot name to fail")


def test_classify_requires_profile_in_cli_wrapper(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    try:
        handle_organize(str(root), classify=True, dry_run=True)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected classify without profile to fail")


def test_classify_raw_requires_media_photographer_profile(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "image.jpg").write_text("image", encoding="utf-8")

    try:
        execute_profile_placement(
            source_root=root,
            destination_root=root,
            profile="media",
            category=None,
            classify_raw="camera",
            executed_by="pytest",
            apply=False,
            dry_run=True,
        )
    except ValueError as exc:
        assert "--classify-raw requires --profile media --category photographer" in str(exc)
    else:
        raise AssertionError("expected invalid classify_raw combination to fail")


def test_classify_raw_groups_only_existing_00_raw_images(tmp_path, monkeypatch):
    import indexly.organize.profiles.media_rules as media_rules

    root = tmp_path / "workspace"
    raw_dir = root / "Media" / "Shoots" / "2026-05-client" / "00_RAW"
    raw_dir.mkdir(parents=True)
    raw_image = raw_dir / "frame.jpg"
    raw_image.write_text("image", encoding="utf-8")
    non_raw = root / "loose.jpg"
    non_raw.write_text("image", encoding="utf-8")

    monkeypatch.setattr(
        media_rules,
        "extract_image_metadata",
        lambda _: {"camera": "Nikon/Z 8"},
    )

    plan = execute_profile_placement(
        source_root=root,
        destination_root=root,
        profile="media",
        category="photographer",
        classify_raw="camera",
        executed_by="pytest",
        recursive=True,
        apply=False,
        dry_run=True,
    )

    assert len(plan) == 1
    destination = plan[0]["destination"].replace("\\", "/")
    assert destination.endswith("00_RAW/Nikon_Z 8/frame.jpg")
    assert "loose.jpg" not in destination


def test_classify_raw_without_classify_routes_to_classification(tmp_path, monkeypatch):
    import indexly.organize.profiles.media_rules as media_rules

    root = tmp_path / "workspace"
    raw_dir = root / "Media" / "Shoots" / "2026-05-client" / "00_RAW"
    raw_dir.mkdir(parents=True)
    (raw_dir / "frame.jpg").write_text("image", encoding="utf-8")
    monkeypatch.setattr(media_rules, "extract_image_metadata", lambda _: {"camera": "Leica"})

    result = handle_organize(
        str(root),
        profile="media",
        category="photographer",
        classify_raw="camera",
        recursive=True,
        dry_run=True,
    )

    assert result == (None, {})
    assert not (root / "log").exists()
