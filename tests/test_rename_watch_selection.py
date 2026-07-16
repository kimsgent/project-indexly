import json
import os
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexly.rename_watch.config import (
    RenameWatchConfigError,
    initialize_settings,
    load_settings,
)
from indexly.rename_watch.selection import MAX_INDEXLYIGNORE_BYTES
from indexly.rename_watch.service import RenameWatchService
from indexly.rename_watch import service as service_module


def _config(tmp_path: Path, **values):
    watch = tmp_path / "watch"
    watch.mkdir(exist_ok=True)
    job = {
        "id": "selection",
        "watch_path": "watch",
        "destination_subfolder": "processed",
        "settle_seconds": 0.01,
        "scan_interval_seconds": 10,
    }
    job.update(values)
    path = tmp_path / "rename-watch.json"
    path.write_text(
        json.dumps({"version": 1, "jobs": [job]}),
        encoding="utf-8",
    )
    return path, watch


def _load(tmp_path: Path, **values):
    path, watch = _config(tmp_path, **values)
    return load_settings(str(path)).jobs[0], watch


def _acquire(service: RenameWatchService):
    service._prepare_watch_paths()
    service._acquire_root_locks()
    return service


def test_selection_defaults_preserve_existing_candidate_contract(tmp_path):
    job, watch = _load(tmp_path)

    assert job.include is None
    assert job.exclude == ()
    assert job.respect_indexlyignore is False
    assert job.recursive is False
    assert job.max_file_size_bytes is None

    root_file = watch / "anything.bin"
    nested_file = watch / "nested" / "nested.bin"
    root_file.write_bytes(b"data")
    nested_file.parent.mkdir()
    nested_file.write_bytes(b"data")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == [root_file.resolve()]


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("include", [], "at least one glob"),
        ("include", "*.pdf", "list of glob strings"),
        ("include", [""], "non-empty string"),
        ("include", [1], "non-empty string"),
        ("include", ["../*.pdf"], "stay below watch_path"),
        ("include", [r"folder\*.pdf"], "path separator"),
        ("include", None, "list of glob strings"),
        ("exclude", "Thumbs.db", "list of glob strings"),
        ("exclude", ["/tmp/*"], "relative POSIX glob"),
        ("respect_indexlyignore", 1, "boolean"),
        ("respect_indexlyignore", None, "boolean"),
        ("recursive", "false", "boolean"),
        ("max_file_size_bytes", True, "positive integer"),
        ("max_file_size_bytes", 0, "positive integer"),
        ("max_file_size_bytes", 1.5, "positive integer"),
        ("max_file_size_bytes", None, "positive integer"),
    ],
)
def test_selection_configuration_is_strict(tmp_path, key, value, message):
    path, _watch = _config(tmp_path, **{key: value})

    with pytest.raises(RenameWatchConfigError, match=message):
        load_settings(str(path))


def test_explicit_empty_exclude_is_allowed(tmp_path):
    job, _watch = _load(tmp_path, exclude=[])

    assert job.exclude == ()


def test_init_template_has_recommended_document_selection(tmp_path):
    path = initialize_settings(str(tmp_path / "rename-watch.json"))
    job = json.loads(path.read_text(encoding="utf-8"))["jobs"][0]

    assert job["include"] == ["*.docx", "*.pdf", "*.txt", "*.md"]
    assert job["exclude"] == [
        "Thumbs.db",
        "desktop.ini",
        ".DS_Store",
        ".thumbnails/",
    ]
    assert job["respect_indexlyignore"] is True
    assert job["recursive"] is False
    assert "max_file_size_bytes" not in job


def test_explicit_globs_are_case_insensitive_and_excludes_win(tmp_path):
    job, watch = _load(
        tmp_path,
        include=["*.pdf", "docs/*.md"],
        exclude=["secret*.pdf", "docs/private/*"],
        recursive=True,
    )
    keep_pdf = watch / "REPORT.PDF"
    blocked_pdf = watch / "Secret-Report.PDF"
    keep_md = watch / "docs" / "Guide.MD"
    blocked_md = watch / "docs" / "private" / "notes.md"
    for path in (keep_pdf, blocked_pdf, keep_md, blocked_md):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == sorted(
        [keep_md.resolve(), keep_pdf.resolve()],
        key=lambda path: os.path.normcase(os.path.abspath(os.fspath(path))),
    )


def test_path_globs_are_segment_aware_and_globstar_is_recursive(tmp_path):
    job, watch = _load(
        tmp_path,
        include=["docs/*.pdf", "**/*.md"],
        recursive=True,
    )
    direct_pdf = watch / "docs" / "direct.pdf"
    deep_pdf = watch / "docs" / "private" / "deep.pdf"
    root_markdown = watch / "README.md"
    deep_markdown = watch / "docs" / "private" / "notes.md"
    for path in (direct_pdf, deep_pdf, root_markdown, deep_markdown):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == sorted(
        [direct_pdf.resolve(), root_markdown.resolve(), deep_markdown.resolve()],
        key=lambda path: os.path.normcase(os.path.abspath(os.fspath(path))),
    )


def test_explicit_globs_normalize_unicode_before_matching(tmp_path):
    job, watch = _load(tmp_path, include=["r\u00e9sum\u00e9.pdf"])
    decomposed = watch / unicodedata.normalize("NFD", "r\u00e9sum\u00e9.pdf")
    decomposed.write_bytes(b"data")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == [decomposed.resolve()]


def test_trailing_slash_exclude_vetoes_files_for_discovery_and_events(tmp_path):
    job, watch = _load(
        tmp_path,
        include=["*.pdf"],
        exclude=[".thumbnails/"],
        recursive=True,
    )
    blocked = watch / ".thumbnails" / "preview.pdf"
    blocked.parent.mkdir()
    blocked.write_bytes(b"preview")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == []
    assert service._eligible(job, blocked) is False
    service.schedule(job, blocked)
    assert service.pending == {}


def test_basename_directory_exclude_prunes_its_subtree(tmp_path):
    job, watch = _load(
        tmp_path,
        include=["*.pdf"],
        exclude=["node_modules"],
        recursive=True,
    )
    blocked = watch / "nested" / "node_modules" / "manual.pdf"
    blocked.parent.mkdir(parents=True)
    blocked.write_bytes(b"data")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == []
    assert service._eligible(job, blocked) is False


def test_recursive_discovery_prunes_destination_excluded_and_symlink_directories(
    tmp_path,
):
    job, watch = _load(
        tmp_path,
        include=["*.pdf"],
        exclude=[".thumbnails/"],
        recursive=True,
    )
    keep = watch / "nested" / "keep.pdf"
    destination = watch / "processed" / "old.pdf"
    thumbnail = watch / ".thumbnails" / "preview.pdf"
    for path in (keep, destination, thumbnail):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "outside.pdf").write_bytes(b"data")
    linked = watch / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("directory symlinks are unavailable")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._discover_candidates(job) == [keep.resolve()]


def test_maximum_size_allows_exact_boundary_and_rejects_larger_file(tmp_path):
    job, watch = _load(tmp_path, max_file_size_bytes=4)
    boundary = watch / "boundary.bin"
    oversized = watch / "oversized.bin"
    boundary.write_bytes(b"1234")
    oversized.write_bytes(b"12345")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    assert service._eligible(job, boundary) is True
    assert service._eligible(job, oversized) is False


def test_final_policy_recheck_can_stop_a_move_after_settling(tmp_path, monkeypatch):
    job, watch = _load(tmp_path)
    source = watch / "report.pdf"
    source.write_bytes(b"data")
    service = RenameWatchService([job], state_root=tmp_path / "state")
    key = (job.job_id, str(source.resolve()))
    file_stat = source.stat()
    service.snapshots[key] = (file_stat.st_size, file_stat.st_mtime_ns)
    eligibility = iter((True, False))
    monkeypatch.setattr(service, "_eligible", lambda *_args: next(eligibility))
    monkeypatch.setattr(
        service.movers[job.job_id],
        "recover_pending",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        service.movers[job.job_id],
        "plan_and_move_operation",
        lambda *_args, **_kwargs: pytest.fail("selection veto must prevent moving"),
    )

    service._process(job, source.resolve(), 0)

    assert source.exists()
    assert key not in service.snapshots


def test_recovery_runs_before_current_selection_is_applied(tmp_path, monkeypatch):
    job, watch = _load(tmp_path, include=["*.pdf"])
    source = watch / "excluded.txt"
    source.write_text("data", encoding="utf-8")
    service = RenameWatchService([job], state_root=tmp_path / "state")
    recovered = []
    monkeypatch.setattr(
        service.movers[job.job_id],
        "recover_pending",
        lambda *_args, **_kwargs: recovered.append(True) or [],
    )

    service._process(job, source.resolve(), 0)

    assert recovered == [True]
    assert source.exists()


def test_root_indexlyignore_is_opt_in_exact_local_read_only_and_loaded_once(tmp_path):
    parent_ignore = tmp_path / ".indexlyignore"
    parent_ignore.write_text("parent-blocked.txt\n", encoding="utf-8")
    job, watch = _load(tmp_path, respect_indexlyignore=True, recursive=True)
    local_ignore = watch / ".indexlyignore"
    local_ignore.write_text("ignored.txt\nblocked/\n", encoding="utf-8")
    alias = watch / ".indexignore"
    ignored = watch / "ignored.txt"
    blocked = watch / "blocked" / "nested.txt"
    keep = watch / "keep.txt"
    parent_blocked = watch / "parent-blocked.txt"
    for path in (alias, ignored, blocked, keep, parent_blocked):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
    before = local_ignore.read_bytes(), local_ignore.stat().st_mtime_ns
    service = _acquire(RenameWatchService([job], state_root=tmp_path / "state"))
    try:
        first = service._discover_candidates(job)
        local_ignore.write_text("keep.txt\n", encoding="utf-8")
        second = service._discover_candidates(job)
    finally:
        service._release_root_locks()

    expected = sorted(
        [alias.resolve(), keep.resolve(), parent_blocked.resolve()],
        key=lambda path: os.path.normcase(os.path.abspath(os.fspath(path))),
    )
    assert first == expected
    assert second == expected
    assert before[0] == b"ignored.txt\nblocked/\n"
    assert local_ignore.read_bytes() == b"keep.txt\n"


def test_missing_local_indexlyignore_does_not_load_a_preset(tmp_path):
    job, watch = _load(tmp_path, respect_indexlyignore=True)
    artifact = watch / "Thumbs.db"
    artifact.write_bytes(b"data")
    service = _acquire(RenameWatchService([job], state_root=tmp_path / "state"))
    try:
        assert service._discover_candidates(job) == [artifact.resolve()]
    finally:
        service._release_root_locks()


def test_enabled_ignore_integration_protects_control_name_case_insensitively(tmp_path):
    job, watch = _load(tmp_path, respect_indexlyignore=True)
    control_alias = watch / ".INDEXLYIGNORE"
    control_alias.write_text("not the exact rules source", encoding="utf-8")
    service = _acquire(RenameWatchService([job], state_root=tmp_path / "state"))
    try:
        assert service._eligible(job, control_alias) is False
    finally:
        service._release_root_locks()


def test_indexlyignore_is_loaded_only_after_root_lock(tmp_path, monkeypatch):
    job, watch = _load(tmp_path, respect_indexlyignore=True)
    (watch / ".indexlyignore").write_text("*.tmp\n", encoding="utf-8")
    original = service_module.load_selection_policy
    service = RenameWatchService([job], state_root=tmp_path / "state")
    observations = []

    def checked_load(selected_job):
        observations.append(bool(service.root_locks))
        return original(selected_job)

    monkeypatch.setattr(service_module, "load_selection_policy", checked_load)
    _acquire(service)
    service._release_root_locks()

    assert observations == [True]


@pytest.mark.parametrize("payload", [b"\xff", b"x" * (MAX_INDEXLYIGNORE_BYTES + 1)])
def test_unsafe_indexlyignore_content_fails_closed(tmp_path, payload):
    job, watch = _load(tmp_path, respect_indexlyignore=True)
    ignore = watch / ".indexlyignore"
    ignore.write_bytes(payload)
    service = RenameWatchService([job], state_root=tmp_path / "state")

    with pytest.raises(RenameWatchConfigError, match="UTF-8|oversized"):
        _acquire(service)

    assert service.root_locks == []
    assert ignore.read_bytes() == payload


def test_linked_indexlyignore_fails_closed(tmp_path):
    job, watch = _load(tmp_path, respect_indexlyignore=True)
    target = tmp_path / "rules.txt"
    target.write_text("*.tmp\n", encoding="utf-8")
    try:
        (watch / ".indexlyignore").symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("file symlinks are unavailable")
    service = RenameWatchService([job], state_root=tmp_path / "state")

    with pytest.raises(RenameWatchConfigError, match="without links"):
        _acquire(service)

    assert service.root_locks == []
    assert target.read_text(encoding="utf-8") == "*.tmp\n"


def test_observer_uses_each_jobs_recursive_setting(tmp_path, monkeypatch):
    job, _watch = _load(tmp_path, recursive=True, mode="event")
    calls = []
    handlers = []

    class FakeObserver:
        def schedule(self, handler, path, recursive):
            calls.append((path, recursive))
            handlers.append(handler)

        def start(self):
            return None

        def stop(self):
            return None

        def is_alive(self):
            return False

    monkeypatch.setattr(service_module, "Observer", FakeObserver)
    service = RenameWatchService([job], state_root=tmp_path / "state")

    service._start_observers()

    assert calls == [(str(job.watch_path), True)]

    reconciled = []
    monkeypatch.setattr(
        service,
        "reconcile",
        lambda selected_job: reconciled.append(selected_job),
    )
    handlers[0].on_created(
        SimpleNamespace(is_directory=True, src_path=str(job.watch_path / "created"))
    )
    handlers[0].on_moved(
        SimpleNamespace(is_directory=True, dest_path=str(job.watch_path / "moved"))
    )

    assert reconciled == [job, job]
