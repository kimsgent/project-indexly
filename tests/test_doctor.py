import json
import sqlite3

from indexly import doctor
from indexly.db_update import apply_migrations
from indexly.db_utils import connect_db


def seed_search_db(db_path):
    conn = connect_db(str(db_path))
    conn.execute("DELETE FROM file_index")
    conn.execute(
        """
        INSERT INTO file_index(path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "C:/data/mobile.txt",
            "mobile phone indexly diagnostic",
            "mobile phone indexly diagnostic",
            "2026-05-08T00:00:00",
            "hash-mobile",
        ),
    )
    conn.commit()
    conn.close()


def test_doctor_inspects_explicit_local_index_db(tmp_path):
    db_path = tmp_path / "index.db"
    seed_search_db(db_path)

    report = doctor._inspect_search_db(str(db_path))

    assert report["exists"] is True
    assert report["readiness"]["file_index_rows"] == 1
    assert report["readiness"]["vocab_rows"] > 0
    assert report["readiness"]["sample_match_rows"] >= 1


def test_run_doctor_json_uses_explicit_relative_db(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    seed_search_db(tmp_path / "index.db")
    (tmp_path / "log").mkdir()
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(doctor, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(doctor, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(doctor, "LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setattr(doctor, "ANALYSIS_DB_FILE", str(tmp_path / "indexly.db"))

    exit_code = doctor.run_doctor(json_output=True, db_path="index.db")
    output = capsys.readouterr().out
    report = json.loads(output)

    assert exit_code == 0
    assert report["search_database"]["path"] == str(tmp_path / "index.db")
    assert report["search_database"]["readiness"]["file_index_rows"] == 1
    assert report["search_database"]["integrity"]["integrity_check"] == "skipped"


def test_run_doctor_full_integrity_checks_explicit_db(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    seed_search_db(tmp_path / "index.db")
    (tmp_path / "log").mkdir()
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(doctor, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(doctor, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(doctor, "LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setattr(doctor, "ANALYSIS_DB_FILE", str(tmp_path / "indexly.db"))

    exit_code = doctor.run_doctor(
        json_output=True,
        db_path="index.db",
        full_integrity=True,
    )
    output = capsys.readouterr().out
    report = json.loads(output)

    assert exit_code == 0
    assert report["search_database"]["integrity"]["quick_check"] == "ok"
    assert report["search_database"]["integrity"]["integrity_check"] == "ok"


def test_doctor_clear_cache_is_explicit(tmp_path, monkeypatch):
    db_path = tmp_path / "fts_index.db"
    seed_search_db(db_path)
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text('{"stale": {"results": []}}', encoding="utf-8")

    monkeypatch.setattr(doctor, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(doctor, "ANALYSIS_DB_FILE", str(tmp_path / "indexly.db"))

    exit_code = doctor.run_doctor(
        json_output=True,
        db_path=str(db_path),
        clear_cache=True,
    )

    assert exit_code == 1
    assert json.loads(cache_file.read_text(encoding="utf-8")) == {}


def test_apply_migrations_skips_fts_rebuild_without_explicit_flag(tmp_path):
    db_path = tmp_path / "old_fts.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE VIRTUAL TABLE file_index USING fts5(
            path,
            content
        )
        """
    )
    conn.execute(
        "INSERT INTO file_index(path, content) VALUES (?, ?)",
        ("C:/data/mobile.txt", "mobile"),
    )
    conn.commit()

    apply_migrations(conn, auto_fix=True)

    cols = [row[1] for row in conn.execute("PRAGMA table_info(file_index)")]
    count = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    conn.close()

    assert cols == ["path", "content"]
    assert count == 1
