import importlib
import json
from datetime import date
from pathlib import Path

from indexly import config


def configure_indexly_home(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEXLY_HOME", str(tmp_path))
    importlib.reload(config)

    import indexly.db_utils as db_utils
    import indexly.delete_search as delete_search

    importlib.reload(db_utils)
    importlib.reload(delete_search)
    return db_utils, delete_search


def seed_search_row(conn, path, content="alpha beta", tag=""):
    conn.execute(
        """
        INSERT INTO file_index(path, content, clean_content, modified, hash, tag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (path, content, content, "2026-05-06T00:00:00", f"hash-{path}", tag),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO file_metadata(path, title, metadata)
        VALUES (?, ?, ?)
        """,
        (path, "Title", "{}"),
    )
    if tag:
        conn.execute(
            "INSERT OR REPLACE INTO file_tags(path, tags) VALUES (?, ?)",
            (path, tag),
        )
    conn.commit()


def table_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_clear_search_by_exact_path_deletes_all_search_tables(tmp_path, monkeypatch):
    db_utils, delete_search = configure_indexly_home(tmp_path, monkeypatch)
    monkeypatch.setattr(delete_search, "_log_deletions", lambda paths, reason: None)

    target = "C:/data/report.txt"
    other = "C:/data/keep.txt"
    conn = db_utils.connect_db()
    seed_search_row(conn, target, tag="review")
    seed_search_row(conn, other, tag="review")
    conn.close()

    result = delete_search.clear_search_results(path=target)

    assert result["matched_files"] == 1
    assert result["deleted_entries"] == 3

    conn = db_utils.connect_db()
    assert conn.execute("SELECT COUNT(*) FROM file_index WHERE path = ?", (target,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM file_tags WHERE path = ?", (target,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM file_metadata WHERE path = ?", (target,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM file_index WHERE path = ?", (other,)).fetchone()[0] == 1
    conn.close()


def test_clear_search_by_directory_like_path_supports_dry_run(tmp_path, monkeypatch):
    db_utils, delete_search = configure_indexly_home(tmp_path, monkeypatch)
    monkeypatch.setattr(delete_search, "_log_deletions", lambda paths, reason: None)

    conn = db_utils.connect_db()
    seed_search_row(conn, "C:/data/project/a.txt")
    seed_search_row(conn, "C:/data/project/nested/b.txt")
    seed_search_row(conn, "C:/data/other.txt")
    conn.close()

    result = delete_search.clear_search_results(path="C:/data/project", dry_run=True)

    assert result["matched_files"] == 2
    assert result["deleted_entries"] == 4

    conn = db_utils.connect_db()
    assert table_count(conn, "file_index") == 3
    assert table_count(conn, "file_metadata") == 3
    conn.close()


def test_clear_search_by_tag_matches_exact_comma_separated_tags(tmp_path, monkeypatch):
    db_utils, delete_search = configure_indexly_home(tmp_path, monkeypatch)
    monkeypatch.setattr(delete_search, "_log_deletions", lambda paths, reason: None)

    conn = db_utils.connect_db()
    seed_search_row(conn, "C:/data/delete.txt", tag="archive,review")
    seed_search_row(conn, "C:/data/keep.txt", tag="preview")
    conn.close()

    result = delete_search.clear_search_results(tag="review")

    assert result["matched_files"] == 1
    assert result["paths"] == ["C:/data/delete.txt"]

    conn = db_utils.connect_db()
    assert conn.execute("SELECT COUNT(*) FROM file_index WHERE path = ?", ("C:/data/delete.txt",)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM file_index WHERE path = ?", ("C:/data/keep.txt",)).fetchone()[0] == 1
    conn.close()


def test_clear_search_invalidates_cache_entries_for_deleted_paths(tmp_path, monkeypatch, capsys):
    db_utils, delete_search = configure_indexly_home(tmp_path, monkeypatch)
    monkeypatch.setattr(delete_search, "_log_deletions", lambda paths, reason: None)

    target = "C:/data/delete.txt"
    keep = "C:/data/keep.txt"
    conn = db_utils.connect_db()
    seed_search_row(conn, target)
    seed_search_row(conn, keep)
    conn.close()

    from indexly.cache_utils import save_cache, load_cache

    save_cache(
        {
            "remove-me": {"results": [{"path": target}]},
            "keep-me": {"results": [{"path": keep}]},
        },
        config.CACHE_FILE,
    )

    delete_search.clear_search_results(path=target)

    cache = load_cache(config.CACHE_FILE)
    assert "remove-me" not in cache
    assert "keep-me" in cache
    assert "Cleared 1 cache entry." in capsys.readouterr().out


def test_clear_search_all_clears_entire_search_cache(tmp_path, monkeypatch):
    db_utils, delete_search = configure_indexly_home(tmp_path, monkeypatch)
    monkeypatch.setattr(delete_search, "_log_deletions", lambda paths, reason: None)

    conn = db_utils.connect_db()
    seed_search_row(conn, "C:/data/delete.txt")
    conn.close()

    from indexly.cache_utils import save_cache, load_cache

    save_cache(
        {
            "indexed-result": {"results": [{"path": "C:/data/delete.txt"}]},
            "stale-result": {"results": [{"path": "C:/data/missing.txt"}]},
        },
        config.CACHE_FILE,
    )

    result = delete_search.clear_search_results(remove_all=True)

    assert result["matched_files"] == 1
    assert result["invalidated_cache_entries"] == 2
    assert load_cache(config.CACHE_FILE) == {}


def test_clear_search_logs_small_deletion_batch_to_ndjson(tmp_path, monkeypatch):
    db_utils, delete_search = configure_indexly_home(tmp_path, monkeypatch)

    import indexly.log_utils as log_utils

    importlib.reload(log_utils)

    target = "C:/data/delete.txt"
    conn = db_utils.connect_db()
    seed_search_row(conn, target)
    conn.close()

    result = delete_search.clear_search_results(path=target)

    today = date.today()
    log_file = (
        Path(config.BASE_DIR)
        / "log"
        / today.strftime("%Y")
        / today.strftime("%m")
        / f"{today.isoformat()}_index_events.ndjson"
    )
    assert result["matched_files"] == 1
    assert log_file.exists()

    entries = [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["event"] for entry in entries] == [
        "SEARCH_RESULT_DELETED",
        "SEARCH_DELETE_SUMMARY",
    ]
    assert entries[0]["path"] == target
    assert entries[0]["reason"] == f"path:{target}"
    assert entries[1]["timestamp"]
    assert entries[1]["count"] == 1


def test_clear_search_parser_accepts_supported_modes(tmp_path, monkeypatch):
    configure_indexly_home(tmp_path, monkeypatch)

    from indexly.cli_utils import build_parser

    parser = build_parser()
    assert parser.parse_args(["clear-search", "--path", "C:/data", "--dry-run"]).path == "C:/data"
    assert parser.parse_args(["clear-search", "--tag", "review", "archive"]).tag == ["review", "archive"]
    assert parser.parse_args(["clear-search", "--all", "--yes"]).all is True
