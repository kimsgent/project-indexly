import logging
from pathlib import Path

import indexly.observers.config as config_module
import indexly.observers.field_observer as field_observer_module
from indexly.observers.config import get_config_path, validate_config
from indexly.observers.field_observer import FieldObserver


def test_validate_config_missing_watch():
    is_valid, errors = validate_config({})

    assert not is_valid
    assert any("watch" in error for error in errors)


def test_validate_config_missing_pattern_and_key():
    config = {
        "watch": [
            {
                "path": "/tmp",
                "profile": "health",
                "fields": {
                    "name": {"type": "regex"},
                    "version": {"type": "toml"},
                },
            }
        ]
    }

    is_valid, errors = validate_config(config)

    assert not is_valid
    assert any("pattern" in error for error in errors)
    assert any("key" in error for error in errors)


def test_field_observer_skips_malformed_rules(monkeypatch, tmp_path, caplog):
    source = tmp_path / "record.txt"
    source.write_text("Name: Jane Doe\nVersion: 1.2.3\n", encoding="utf-8")

    monkeypatch.setattr(
        field_observer_module,
        "find_watch_entry",
        lambda _: {
            "path": str(tmp_path),
            "profile": "health",
            "fields": {
                "name": {"type": "regex"},
                "version": {"type": "regex", "pattern": r"Version:\s*(.*)"},
            },
        },
    )

    with caplog.at_level(logging.WARNING):
        extracted = FieldObserver().extract(source, {})

    assert extracted == {"version": "1.2.3"}
    assert "missing 'pattern'" in caplog.text


def test_get_config_path_falls_back_when_home_is_not_writable(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    temp_root = tmp_path / "tmp"

    monkeypatch.setattr(config_module.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(config_module, "_directory_is_writable", lambda _: False)
    monkeypatch.setattr(config_module.tempfile, "gettempdir", lambda: str(temp_root))

    assert get_config_path() == Path(temp_root) / "indexly" / config_module.CONFIG_FILENAME
