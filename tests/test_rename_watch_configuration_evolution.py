import json
import os
from importlib import resources
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from indexly.rename_watch.config import RenameWatchConfigError, load_settings
from indexly.rename_watch.config_migration import REPORT_SCHEMA, migrate_config
from indexly.rename_watch.status_cli import run_status_command


def _document(watch_path="incoming"):
    return {
        "version": 1,
        "jobs": [
            {
                "id": "inbox",
                "watch_path": watch_path,
                "destination_subfolder": "processed",
            }
        ],
    }


def _write_config(path: Path, document=None):
    path.write_text(json.dumps(document or _document()), encoding="utf-8")
    return path


def _schema_bytes():
    return (
        resources.files("indexly.rename_watch")
        .joinpath("schemas/rename-watch-config-v1.schema.json")
        .read_bytes()
    )


def test_published_schema_is_valid_packaged_and_identical_to_hugo_asset():
    packaged = _schema_bytes()
    published = (
        Path(__file__).parents[1]
        / "docs/static/schemas/rename-watch-config-v1.schema.json"
    ).read_bytes()
    assert packaged == published
    schema = json.loads(packaged)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == (
        "https://projectindexly.com/schemas/rename-watch-config-v1.schema.json"
    )


def test_schema_accepts_minimal_v1_and_rejects_bool_version_and_unknown_keys():
    validator = Draft202012Validator(json.loads(_schema_bytes()))
    assert list(validator.iter_errors(_document())) == []
    invalid_version = _document()
    invalid_version["version"] = True
    assert list(validator.iter_errors(invalid_version))
    unknown = _document()
    unknown["new_v2_key"] = True
    assert list(validator.iter_errors(unknown))


def test_runtime_rejects_bool_version_to_match_schema(tmp_path):
    document = _document()
    document["version"] = True
    with pytest.raises(RenameWatchConfigError, match="version must be 1"):
        load_settings(os.fspath(_write_config(tmp_path / "config.json", document)))


def test_path_expansion_is_scoped_and_undefined_variables_fail_closed(
    tmp_path, monkeypatch
):
    watch_root = tmp_path / "expanded-watch"
    home = tmp_path / "service-home"
    monkeypatch.setenv("RW_WATCH_ROOT", os.fspath(watch_root))
    monkeypatch.setenv("HOME", os.fspath(home))
    monkeypatch.setenv("USERPROFILE", os.fspath(home))
    document = _document("${RW_WATCH_ROOT}")
    document["jobs"][0]["destination_subfolder"] = "${DESTINATION_LITERAL}"
    config = _write_config(tmp_path / "config.json", document)
    settings = load_settings(os.fspath(config))
    assert settings.jobs[0].watch_path == watch_root.resolve()
    assert settings.jobs[0].destination_path.name == "${DESTINATION_LITERAL}"

    home_config = _write_config(tmp_path / "home.json", _document("~/incoming"))
    assert load_settings(os.fspath(home_config)).jobs[0].watch_path == (
        home / "incoming"
    ).resolve()

    missing = _write_config(tmp_path / "missing.json", _document("${RW_MISSING}"))
    monkeypatch.delenv("RW_MISSING", raising=False)
    with pytest.raises(RenameWatchConfigError, match="undefined environment"):
        load_settings(os.fspath(missing))


def test_migration_is_deterministic_preserves_literals_and_has_no_runtime_side_effects(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.json"
    output = tmp_path / "migrated.json"
    second = tmp_path / "migrated-again.json"
    runtime = tmp_path / "runtime-must-not-exist"
    watch = tmp_path / "watch-must-not-exist"
    monkeypatch.setenv("RW_WATCH", os.fspath(watch))
    monkeypatch.setenv("INDEXLY_HOME", os.fspath(runtime))
    document = _document("${RW_WATCH}")
    original = json.dumps(document, separators=(",", ":")).encode("utf-8")
    source.write_bytes(original)

    assert migrate_config(os.fspath(source), output=os.fspath(output)) == 0
    assert source.read_bytes() == original
    migrated = json.loads(output.read_text(encoding="utf-8"))
    assert migrated == document
    assert migrated["jobs"][0]["watch_path"] == "${RW_WATCH}"
    assert "service" not in migrated
    assert not runtime.exists()
    assert not watch.exists()

    assert migrate_config(os.fspath(output), output=os.fspath(second)) == 0
    assert output.read_bytes() == second.read_bytes()


def test_migration_refuses_same_existing_and_unsupported_version(tmp_path):
    source = _write_config(tmp_path / "source.json")
    with pytest.raises(RenameWatchConfigError, match="must differ"):
        migrate_config(os.fspath(source), output=os.fspath(source))

    existing = _write_config(tmp_path / "existing.json")
    with pytest.raises(RenameWatchConfigError, match="already exists"):
        migrate_config(os.fspath(source), output=os.fspath(existing))

    version_two = _document()
    version_two["version"] = 2
    unsupported = _write_config(tmp_path / "version-two.json", version_two)
    with pytest.raises(RenameWatchConfigError, match="cannot be migrated"):
        migrate_config(os.fspath(unsupported), output=os.fspath(tmp_path / "v2-out.json"))


def test_migration_cli_json_contract_and_missing_output_usage(tmp_path, capsys):
    source = _write_config(tmp_path / "source.json")
    output = tmp_path / "migrated.json"
    assert run_status_command(
        [
            "rename-watch",
            "--config",
            os.fspath(source),
            "--migrate-config",
            "--output",
            os.fspath(output),
            "--json",
        ],
        0,
    ) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "schema": REPORT_SCHEMA,
        "version": 1,
        "source_version": 1,
        "target_version": 1,
        "output": os.fspath(output.resolve()),
    }

    assert run_status_command(
        [
            "rename-watch",
            "--config",
            os.fspath(source),
            "--migrate-config",
            "--json-errors",
        ],
        0,
    ) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["category"] == "usage"


def test_help_exposes_migration_but_no_live_reload(capsys):
    with pytest.raises(SystemExit) as exit_info:
        run_status_command(["rename-watch", "--help"], 0)
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--migrate-config" in help_text
    assert "--reload" not in help_text
