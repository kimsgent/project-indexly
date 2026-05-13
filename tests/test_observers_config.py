import logging

import indexly.observers.field_observer as field_observer_module
from indexly.observers.config import validate_config
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
