import json
import sqlite3
from pathlib import Path

import pytest

from indexly import doctor
from indexly.db_update import apply_migrations
from indexly.db_utils import connect_db
from indexly.extras_manager import ExtraStatus
from indexly.perf import PerformanceStatus


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


@pytest.mark.parametrize(
    ("create_sql", "expected_state", "expected_warning"),
    [
        (
            """
            CREATE VIRTUAL TABLE file_index USING fts5(
                path, content, clean_content, modified, hash, tag,
                tokenize='porter', prefix='2 3'
            )
            """,
            "drift",
            "fts_schema_drift",
        ),
        (
            """
            CREATE TABLE file_index(
                path, content, clean_content, modified, hash, tag
            )
            """,
            "uninspectable",
            "fts_schema_uninspectable",
        ),
    ],
)
def test_doctor_uses_semantic_fts_definition_inspection(
    tmp_path,
    create_sql,
    expected_state,
    expected_warning,
):
    db_path = tmp_path / "semantic-drift.db"
    conn = sqlite3.connect(db_path)
    conn.execute(create_sql)
    conn.commit()
    conn.close()

    report = doctor._inspect_search_db(str(db_path))

    assert report["schema"]["fts5"]["state"] == expected_state
    assert expected_warning in report["warnings"]
    recommendations = doctor._recommendations(
        {
            "search_database": report,
            "analysis_database": {},
            "dependencies": {"extras_overlay": {}},
            "cache": {},
            "local_index_db": {},
            "performance": {},
            "errors": [],
        }
    )
    assert any(
        "FTS5" in recommendation or "file_index" in recommendation
        for recommendation in recommendations
    )


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
    assert report["dependencies"]["extras_overlay"]["status"] == "ok"
    assert report["dependencies"]["extras_overlay"]["stale"] == []
    assert report["performance"]["grade"] is None
    assert report["performance"]["evidence"] == "record_unavailable"


def test_doctor_consumes_only_conservative_performance_status(
    tmp_path, monkeypatch, capsys
):
    seed_search_db(tmp_path / "index.db")
    (tmp_path / "log").mkdir()
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    calls = []

    monkeypatch.setattr(doctor, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(doctor, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(doctor, "LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setattr(doctor, "ANALYSIS_DB_FILE", str(tmp_path / "indexly.db"))
    monkeypatch.setattr(
        doctor,
        "read_conservative_status",
        lambda state_dir: (
            calls.append(state_dir)
            or PerformanceStatus(
                "Elevated",
                "current",
                "Current local evidence indicates sustained FTS-read pressure.",
            )
        ),
    )

    exit_code = doctor.run_doctor(
        json_output=True,
        db_path=str(tmp_path / "index.db"),
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [tmp_path / "perf"]
    assert report["performance"] == {
        "grade": "Elevated",
        "evidence": "current",
        "reason": "Current local evidence indicates sustained FTS-read pressure.",
    }
    assert any("indexly perf --show" in item for item in report["recommendations"])


def test_extras_overlay_report_is_read_only_when_no_packs_exist(tmp_path):
    report = doctor._extras_overlay_report(tmp_path)

    assert report["status"] == "ok"
    assert report["stale"] == []
    assert all(group["state"] == "not-installed" for group in report["groups"].values())
    assert not (tmp_path / "extras").exists()


def test_extras_overlay_report_warns_about_stale_runtime(tmp_path):
    stale = (
        tmp_path / "extras" / "0.0.1" / "cpython-300" / "test-platform" / "environment"
    )
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text(
        json.dumps({"selected_groups": ["documents"]}),
        encoding="utf-8",
    )

    report = doctor._extras_overlay_report(tmp_path)

    assert report["status"] == "warning"
    assert report["stale"] == [
        {
            "path": str(stale),
            "indexly_version": "0.0.1",
            "python_abi": "cpython-300",
            "platform_tag": "test-platform",
            "groups": ["documents"],
            "reason": "indexly-version",
        }
    ]


def test_extras_overlay_report_detects_installed_pack_with_missing_imports(
    tmp_path, monkeypatch
):
    status = ExtraStatus(
        group="documents",
        state="installed",
        path=Path(tmp_path) / "documents",
        manifest={"schema": 1},
    )
    monkeypatch.setattr(
        "indexly.extras_manager.list_extras",
        lambda **kwargs: (status,),
    )
    monkeypatch.setattr(
        "indexly.extras_manager.list_stale_overlays",
        lambda **kwargs: (),
    )

    report = doctor._extras_overlay_report(
        tmp_path,
        optional_report={
            "documents": {
                "status": "missing_optional",
                "missing": ["fitz"],
            }
        },
    )

    assert report["status"] == "warning"
    assert report["incomplete_groups"] == ["documents"]


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


def test_run_doctor_profile_db_respects_full_integrity(
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
        profile_db=True,
        db_path="index.db",
        full_integrity=True,
    )
    output = capsys.readouterr().out
    report = json.loads(output)

    assert exit_code == 0
    assert report["integrity"]["quick_check"] == "ok"
    assert report["integrity"]["integrity_check"] == "ok"


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


def test_doctor_missing_db_recommendation_is_actionable(tmp_path, monkeypatch, capsys):
    missing_db = tmp_path / "missing.db"
    (tmp_path / "log").mkdir()
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(doctor, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(doctor, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(doctor, "LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setattr(doctor, "ANALYSIS_DB_FILE", str(tmp_path / "indexly.db"))

    exit_code = doctor.run_doctor(json_output=True, db_path=str(missing_db))
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "No immediate action required." not in report["recommendations"]
    assert any(
        "Search database not found." in rec for rec in report["recommendations"]
    )


def test_render_search_db_report_marks_missing_readiness_values(monkeypatch):
    captured: dict[str, object] = {}

    def fake_render_table(title, rows):
        captured["title"] = title
        captured["rows"] = rows

    monkeypatch.setattr(doctor, "_render_table", fake_render_table)

    doctor._render_search_db_report(
        {
            "path": "/tmp/missing.db",
            "exists": False,
            "is_indexly": False,
            "readiness": {},
            "integrity": {},
        }
    )

    rows = captured["rows"]
    status_by_check = {name: status for name, _value, status in rows}
    assert status_by_check["Documents"] == "error"
    assert status_by_check["Vocabulary terms"] == "error"
    assert status_by_check["Sample MATCH rows"] == "error"


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
