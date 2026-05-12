import json
import os
import time
from pathlib import Path

from indexly.organize.lister import (
    _discover_log,
    _sort_files,
    list_organizer_log,
)
from indexly.organize.lister_cache import read_cache, write_cache


def _entry(path: Path, *, original_path: Path | None = None, ext: str = ".txt") -> dict:
    return {
        "original_path": str(original_path or path),
        "new_path": str(path),
        "alias": None,
        "extension": ext,
        "category": "document",
        "size": path.stat().st_size if path.exists() else 1,
        "hash": None,
        "used_date": "2026-05",
        "duplicate": False,
        "created_at": None,
        "modified_at": None,
    }


def _log(root: Path, files: list[dict]) -> dict:
    return {
        "meta": {
            "tool": "indexly",
            "module": "organizer",
            "version": "1.0",
            "sorted_by": "date",
            "root": str(root),
            "executed_at": "2026-05-12T00:00:00Z",
            "executed_by": "pytest",
        },
        "summary": {"total_files": len(files)},
        "files": files,
    }


def _write_log(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_discover_log_prefers_root_log_directory_over_newer_nested_log(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    root_file = root / "kept.txt"
    nested_file = root / "nested" / "kept.txt"
    root_file.write_text("root", encoding="utf-8")
    nested_file.parent.mkdir()
    nested_file.write_text("nested", encoding="utf-8")

    root_log = root / "log" / "organized_2026-05-12_root.json"
    nested_log = root / "nested" / "organized_2026-05-13_nested.json"
    _write_log(root_log, _log(root, [_entry(root_file)]))
    _write_log(nested_log, _log(root / "nested", [_entry(nested_file)]))

    later = time.time() + 60
    earlier = time.time()
    os_times = (later, later)
    nested_log.touch()
    root_log.touch()
    os.utime(nested_log, os_times)
    os.utime(root_log, (earlier, earlier))

    assert _discover_log(root) == root_log.resolve()


def test_cache_invalidates_when_manifest_changes_with_same_file_count(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "important.txt"
    source.write_text("original", encoding="utf-8")
    data = _log(root, [_entry(source)])

    write_cache(root, data, mode="dry-run")
    assert read_cache(root) is not None

    source.write_text("replacement content", encoding="utf-8")

    assert read_cache(root) is None


def test_cache_invalidates_when_indexlyignore_changes(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "events.log"
    ignore = root / ".indexlyignore"
    source.write_text("event", encoding="utf-8")
    ignore.write_text("# empty\n", encoding="utf-8")

    write_cache(root, _log(root, [_entry(source, ext=".log")]), mode="dry-run")
    assert read_cache(root) is not None

    ignore.write_text("*.log\n", encoding="utf-8")

    assert read_cache(root) is None


def test_filter_feedback_lists_available_values(tmp_path, capsys):
    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "report.pdf"
    source.write_text("pdf-ish", encoding="utf-8")
    log_path = root / "organized_2026-05-12_root.json"
    _write_log(log_path, _log(root, [_entry(source, ext=".pdf")]))

    listed = list_organizer_log(log_path, ext=".xyz", no_cache=True)

    out = capsys.readouterr().out
    assert listed == 0
    assert "No files matched the applied filters" in out
    assert "Available extensions" in out
    assert ".pdf" in out


def test_duplicate_detection_hashes_generated_logs_via_original_paths(tmp_path, capsys):
    root = tmp_path / "workspace"
    root.mkdir()
    first = root / "a.txt"
    second = root / "b.txt"
    first.write_text("same", encoding="utf-8")
    second.write_text("same", encoding="utf-8")

    listed = list_organizer_log(
        root,
        detect_duplicates=True,
        no_cache=True,
    )

    out = capsys.readouterr().out
    assert listed == 2
    assert "Duplicates detected: 2" in out
    assert "Skipping hash-based duplicate detection" not in out


def test_sort_by_extension_groups_extensionless_files_last(tmp_path):
    files = [
        {"new_path": str(tmp_path / "zeta"), "extension": ""},
        {"new_path": str(tmp_path / "b.pdf"), "extension": ".pdf"},
        {"new_path": str(tmp_path / "a.doc"), "extension": ".doc"},
        {"new_path": str(tmp_path / "a.pdf"), "extension": ".pdf"},
    ]

    assert _sort_files(files, "extension") is True
    assert [Path(f["new_path"]).name for f in files] == [
        "a.doc",
        "a.pdf",
        "b.pdf",
        "zeta",
    ]
