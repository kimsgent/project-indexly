import os
from datetime import datetime

from indexly.cli_utils import build_parser
from indexly.db_utils import connect_db
from indexly.path_utils import normalize_path
from indexly.pipeline.rename_plan import RenameEntry, RenamePlan
from indexly.rename_utils import generate_new_filename, rename_file, rename_files_in_dir


def _insert_index_rows(path, db_path=None):
    conn = connect_db(str(db_path) if db_path else None)
    cur = conn.cursor()
    norm = normalize_path(str(path))
    cur.execute("INSERT INTO file_metadata (path) VALUES (?)", (norm,))
    cur.execute("INSERT INTO file_tags (path, tags) VALUES (?, ?)", (norm, "alpha"))
    cur.execute(
        """
        INSERT INTO file_index (path, content, clean_content, modified, hash, tag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (norm, "content", "content", "2026-05-12", "hash", "alpha"),
    )
    conn.commit()
    conn.close()
    return norm


def _set_mtime(path, year=2026, month=3, day=12):
    timestamp = datetime(year, month, day, 12, 0, 0).timestamp()
    os.utime(path, (timestamp, timestamp))


def test_rename_files_without_db_update_does_not_require_metadata_schema(tmp_path):
    source = tmp_path / "report.txt"
    source.write_text("hello", encoding="utf-8")

    entries = rename_files_in_dir(
        str(tmp_path),
        pattern="{title}-renamed",
        dry_run=False,
        update_db=False,
    )

    renamed = tmp_path / "report-renamed.txt"
    assert renamed.exists()
    assert not source.exists()
    assert entries[0].renamed_path == renamed


def test_directory_rename_uses_implicit_counter_only_for_collisions(tmp_path):
    work_dir = tmp_path / "files"
    work_dir.mkdir()
    for name in ("autodoctor.db", "report.json", "sakila.db"):
        path = work_dir / name
        path.write_text("hello", encoding="utf-8")
        _set_mtime(path)

    entries = rename_files_in_dir(
        str(work_dir),
        pattern="{date}-{title}",
        date_format="%y%m%d",
        dry_run=True,
    )

    renamed_names = [entry.renamed_path.name for entry in entries]
    assert renamed_names == [
        "260312-autodoctor.db",
        "260312-report.json",
        "260312-sakila.db",
    ]


def test_directory_rename_tracks_planned_dry_run_collisions(tmp_path):
    work_dir = tmp_path / "files"
    work_dir.mkdir()
    for name in ("alpha.txt", "alpha!.txt"):
        path = work_dir / name
        path.write_text("hello", encoding="utf-8")
        _set_mtime(path)

    entries = rename_files_in_dir(
        str(work_dir),
        pattern="{date}-{title}",
        date_format="%y%m%d",
        dry_run=True,
    )

    renamed_names = {entry.renamed_path.name for entry in entries}
    assert renamed_names == {"260312-alpha.txt", "260312-alpha-1.txt"}


def test_rename_file_update_db_syncs_metadata_tags_and_search_index(tmp_path):
    source = tmp_path / "Report.txt"
    source.write_text("hello", encoding="utf-8")
    old_norm = _insert_index_rows(source)

    new_path = rename_file(
        str(source),
        pattern="{title}-renamed",
        dry_run=False,
        update_db=True,
    )

    assert new_path == tmp_path / "report-renamed.txt"
    assert new_path.exists()
    assert not source.exists()

    new_norm = normalize_path(str(new_path))
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT path, alias FROM file_metadata WHERE path = ?", (new_norm,))
    metadata = cur.fetchone()
    cur.execute("SELECT tags FROM file_tags WHERE path = ?", (new_norm,))
    tags = cur.fetchone()
    cur.execute("SELECT path FROM file_index WHERE path = ?", (new_norm,))
    search = cur.fetchone()
    cur.execute("SELECT path FROM file_metadata WHERE path = ?", (old_norm,))
    old_metadata = cur.fetchone()
    conn.close()

    assert metadata["alias"] == "Report.txt"
    assert tags["tags"] == "alpha"
    assert search["path"] == new_norm
    assert old_metadata is None


def test_rename_file_update_db_uses_explicit_database_path(tmp_path):
    source = tmp_path / "Report.txt"
    source.write_text("hello", encoding="utf-8")
    explicit_db = tmp_path / "fts_index.db"
    _insert_index_rows(source, db_path=explicit_db)

    new_path = rename_file(
        str(source),
        pattern="{title}-renamed",
        dry_run=False,
        update_db=True,
        db_path=str(explicit_db),
    )

    new_norm = normalize_path(str(new_path))
    conn = connect_db(str(explicit_db))
    cur = conn.cursor()
    cur.execute("SELECT path FROM file_index WHERE path = ?", (new_norm,))
    search = cur.fetchone()
    conn.close()

    assert search["path"] == new_norm


def test_rename_file_update_db_preflight_blocks_destination_db_conflict(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    _insert_index_rows(source)

    conflicting_path = tmp_path / "source-renamed.txt"
    conn = connect_db()
    conn.execute(
        "INSERT INTO file_metadata (path) VALUES (?)",
        (normalize_path(str(conflicting_path)),),
    )
    conn.commit()
    conn.close()

    result = rename_file(
        str(source),
        pattern="{title}-renamed",
        dry_run=False,
        update_db=True,
    )

    assert result is None
    assert source.exists()
    assert not conflicting_path.exists()


def test_rename_plan_exports_current_organizer_shape(tmp_path):
    original = tmp_path / "old.txt"
    renamed = tmp_path / "new.txt"
    plan = RenamePlan(
        entries=[RenameEntry(original_path=original, renamed_path=renamed)],
        dry_run=True,
        root=tmp_path,
    )

    assert plan.as_organizer_input() == {
        "files": [
            {
                "original_path": str(original),
                "renamed_path": str(renamed),
            }
        ]
    }


def test_business_prefix_applies_when_pattern_omits_prefix_placeholder(tmp_path):
    source = tmp_path / "receipt.txt"
    source.write_text("hello", encoding="utf-8")

    new_name = generate_new_filename(
        source,
        pattern="{date}-{title}",
        prefix="receipt",
    )

    assert new_name.endswith("-receipt.txt")
    assert new_name.startswith("receipt-")


def test_rename_cli_help_exposes_documented_options():
    parser = build_parser()

    args = parser.parse_args(
        [
            "rename-file",
            ".",
            "--date-format",
            "%Y-%m-%d",
            "--counter-format",
            "03d",
            "--update-db",
            "--db",
            "fts_index.db",
        ]
    )

    assert args.date_format == "%Y-%m-%d"
    assert args.counter_format == "03d"
    assert args.update_db is True
    assert args.db == "fts_index.db"
