from pathlib import Path
import json

import pytest

from indexly.cli_utils import build_parser
from indexly.compare.cli_compare import handle_compare
from indexly.compare.compare_engine import run_compare
from indexly.compare.constants import CompareMode, CompareTier, ExitCode
from indexly.compare.extract_adapter import ExtractionResult
from indexly.compare.file_compare import compare_files
from indexly.compare.models import DiffLine, FileCompareResult, FolderCompareResult
from indexly.compare.resolver import ComparePathResolutionError, resolve_paths


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_compare_accepts_csv_filters_and_respects_project_ignore(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    ignore_text = "ignored.txt\n"

    _write(left / ".indexlyignore", ignore_text)
    _write(right / ".indexlyignore", ignore_text)
    _write(left / "keep.py", "print('same')\n")
    _write(right / "keep.py", "print('same')\n")
    _write(left / "ignored.txt", "left only\n")

    result, exit_code = run_compare(left, right, extensions=".py,.txt")

    assert isinstance(result, FolderCompareResult)
    assert exit_code == 0
    assert result.summary.missing_b == 0
    assert [file.path_a.name for file in result.files] == ["keep.py"]


def test_compare_can_disable_project_ignore(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    ignore_text = "ignored.txt\n"

    _write(left / ".indexlyignore", ignore_text)
    _write(right / ".indexlyignore", ignore_text)
    _write(left / "ignored.txt", "left only\n")

    result, exit_code = run_compare(
        left,
        right,
        extensions={".txt"},
        use_project_ignore=False,
    )

    assert isinstance(result, FolderCompareResult)
    assert exit_code == 1
    assert result.summary.missing_b == 1


def test_explicit_ignore_file_overrides_project_ignore(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    custom_ignore = tmp_path / "custom.indexlyignore"

    _write(left / ".indexlyignore", "project.txt\n")
    _write(right / ".indexlyignore", "project.txt\n")
    _write(custom_ignore, "custom.txt\n")
    _write(left / "project.txt", "left only\n")
    _write(left / "custom.txt", "left only\n")

    result, _exit_code = run_compare(
        left,
        right,
        extensions=".txt",
        ignore_file=custom_ignore,
    )

    assert isinstance(result, FolderCompareResult)
    assert result.summary.missing_b == 1


def test_explicit_ignore_names_are_additive(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"

    _write(left / "generated" / "cache.py", "left only\n")
    _write(left / "keep.py", "print('same')\n")
    _write(right / "keep.py", "print('same')\n")

    result, exit_code = run_compare(
        left,
        right,
        extensions={".py"},
        ignore={"generated"},
        use_project_ignore=False,
    )

    assert isinstance(result, FolderCompareResult)
    assert exit_code == 0
    assert result.summary.missing_b == 0


def test_extraction_failure_is_reported(monkeypatch, tmp_path):
    left = _write(tmp_path / "a.txt", "left\n")
    right = _write(tmp_path / "b.txt", "right\n")

    def fail_left(path: Path) -> ExtractionResult:
        if path == left:
            return ExtractionResult(success=False, text="", error="boom")
        return ExtractionResult(success=True, text="right")

    monkeypatch.setattr("indexly.compare.file_compare.extract_text", fail_left)

    result = compare_files(left, right)

    assert result.extraction_error == "boom"
    assert result.diffs == [DiffLine(sign="!", text="Extraction failed: boom")]


def test_mismatched_path_types_use_incompatible_tier(tmp_path):
    file_path = _write(tmp_path / "file.txt", "hello\n")
    dir_path = tmp_path / "folder"
    dir_path.mkdir()

    result, exit_code = run_compare(file_path, dir_path)

    assert isinstance(result, FileCompareResult)
    assert result.tier == CompareTier.INCOMPATIBLE
    assert exit_code == 2


def test_threshold_controls_folder_similar_count(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left / "data.py", "alpha\n")
    _write(right / "data.py", "beta\n")

    no_threshold, _ = run_compare(
        left,
        right,
        extensions={".py"},
        use_project_ignore=False,
    )
    loose_threshold, _ = run_compare(
        left,
        right,
        threshold=1.0,
        extensions={".py"},
        use_project_ignore=False,
    )

    assert isinstance(no_threshold, FolderCompareResult)
    assert isinstance(loose_threshold, FolderCompareResult)
    assert no_threshold.summary.modified == 1
    assert no_threshold.summary.similar == 0
    assert loose_threshold.summary.modified == 0
    assert loose_threshold.summary.similar == 1


def test_compare_parser_accepts_ignore_file_and_no_project_ignore():
    args = build_parser().parse_args(
        [
            "compare",
            "a",
            "b",
            "--ignore-file",
            "custom.indexlyignore",
            "--no-project-ignore",
        ]
    )

    assert args.ignore_file == "custom.indexlyignore"
    assert args.no_project_ignore is True


def test_resolver_auto_compare_uses_current_directory_peer(monkeypatch, tmp_path):
    workdir = tmp_path / "workdir"
    external = tmp_path / "external"
    local_file = _write(workdir / "report.txt", "same\n")
    external_file = _write(external / "report.txt", "same\n")

    monkeypatch.chdir(workdir)

    path_a, path_b, mode = resolve_paths(external_file, None)
    result, exit_code = run_compare(external_file)

    assert path_a == local_file.resolve()
    assert path_b == external_file.resolve()
    assert mode == CompareMode.AUTO
    assert isinstance(result, FileCompareResult)
    assert result.identical is True
    assert exit_code == 0


def test_resolver_rejects_auto_compare_to_self(monkeypatch, tmp_path):
    target = _write(tmp_path / "report.txt", "same\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ComparePathResolutionError, match="compare the path to itself"):
        run_compare(target)


def test_compare_cli_reports_auto_resolution_errors_as_json(monkeypatch, tmp_path, capsys):
    target = _write(tmp_path / "report.txt", "same\n")
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(["compare", str(target), "--json"])

    with pytest.raises(SystemExit) as exc:
        handle_compare(args)

    assert exc.value.code == int(ExitCode.ERROR)
    output = capsys.readouterr().out
    assert '"type": "error"' in output
    assert "compare the path to itself" in output


def test_compare_cli_reports_missing_manual_path_as_json(tmp_path, capsys):
    existing = _write(tmp_path / "existing.txt", "same\n")
    missing = tmp_path / "missing.txt"
    args = build_parser().parse_args(
        ["compare", str(existing), str(missing), "--json"]
    )

    with pytest.raises(SystemExit) as exc:
        handle_compare(args)

    assert exc.value.code == int(ExitCode.ERROR)
    output = capsys.readouterr().out
    assert '"type": "error"' in output
    assert "Path not found" in output


def test_compare_cli_outputs_folder_json(tmp_path, capsys):
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left / "same.txt", "same\n")
    _write(right / "same.txt", "same\n")
    args = build_parser().parse_args(
        [
            "compare",
            str(left),
            str(right),
            "--json",
            "--extensions",
            ".txt",
            "--no-project-ignore",
        ]
    )

    with pytest.raises(SystemExit) as exc:
        handle_compare(args)

    payload = json.loads(capsys.readouterr().out)
    assert exc.value.code == 0
    assert payload["type"] == "folder"
    assert payload["summary"] == {
        "identical": 1,
        "similar": 0,
        "modified": 0,
        "missing_a": 0,
        "missing_b": 0,
    }


def test_large_text_compare_skips_expensive_diff_by_default(tmp_path):
    left = _write(tmp_path / "large-a.csv", "a,b\n" + ("1,2\n" * 20))
    right = _write(tmp_path / "large-b.csv", "a,b\n" + ("1,3\n" * 20))

    result = compare_files(left, right, max_text_compare_bytes=10)

    assert result.identical is False
    assert result.similarity is None
    assert result.comparison_warning is not None
    assert "Large text comparison switched to line preview" in result.comparison_warning
    assert "--context" in result.comparison_warning
    assert "--full-diff" in result.comparison_warning
    assert any(diff.sign == "-" for diff in result.diffs)
    assert any(diff.sign == "+" for diff in result.diffs)


def test_full_diff_scans_large_text_without_similarity_diff_blowup(tmp_path):
    left = _write(tmp_path / "large-a.csv", "a,b\n" + ("1,2\n" * 20))
    right = _write(tmp_path / "large-b.csv", "a,b\n" + ("1,3\n" * 20))

    result = compare_files(
        left,
        right,
        full_diff=True,
        max_text_compare_bytes=10,
    )

    assert result.comparison_warning is not None
    assert "Full line scan completed" in result.comparison_warning
    assert result.similarity is None
    assert any(diff.sign == "-" for diff in result.diffs)


def test_compare_cli_outputs_large_file_warning_json(tmp_path, capsys):
    left = _write(tmp_path / "large-a.csv", "a,b\n" + ("1,2\n" * 600000))
    right = _write(tmp_path / "large-b.csv", "a,b\n" + ("1,3\n" * 600000))
    args = build_parser().parse_args(["compare", str(left), str(right), "--json"])

    with pytest.raises(SystemExit) as exc:
        handle_compare(args)

    payload = json.loads(capsys.readouterr().out)
    assert exc.value.code == 1
    assert payload["comparison_warning"] is not None
    assert "Large text comparison switched to line preview" in payload["comparison_warning"]
