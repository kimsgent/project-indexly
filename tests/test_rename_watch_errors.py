import io
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexly.rename_watch.config import (
    RenameWatchConfigError,
    initialize_settings,
)
from indexly.rename_watch.counter_operator import reset_counters
from indexly.rename_watch.error_contract import (
    ERROR_SCHEMA,
    RenameWatchUsageError,
    classify_error,
    run_with_error_contract,
)
from indexly.rename_watch.status_cli import run_status_command


class _TTY:
    def isatty(self):
        return True


def _config(tmp_path, *, job_id="alpha"):
    path = tmp_path / "rename-watch.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "id": job_id,
                        "watch_path": "incoming",
                        "destination_subfolder": "done",
                        "pattern": "{date}-{title}-{counter}",
                        "date_format": "%Y%m%d",
                        "counter_format": "03d",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _subprocess_environment(tmp_path):
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": os.fspath(tmp_path / "home-must-not-exist"),
            "INDEXLY_HOME": os.fspath(tmp_path / "runtime-must-not-exist"),
            "PYTHONIOENCODING": "ascii",
            "PYTHONPATH": os.fspath(Path(__file__).parents[1] / "src"),
        }
    )
    return environment


def _assert_json_error(result, exit_code, category):
    assert result.returncode == exit_code
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1
    assert "\x1b" not in result.stderr
    assert all(ord(character) < 128 for character in result.stderr)
    document = json.loads(result.stderr)
    assert set(document) == {"schema", "version", "exit_code", "error"}
    assert document["schema"] == ERROR_SCHEMA
    assert document["version"] == 1
    assert document["exit_code"] == exit_code
    assert document["error"]["category"] == category
    assert set(document["error"]) == {"category", "message"}


@pytest.mark.parametrize(
    ("error", "exit_code", "category"),
    [
        (RuntimeError("internal"), 1, "internal"),
        (RenameWatchUsageError("usage"), 2, "usage"),
        (RenameWatchConfigError("safety"), 3, "config_or_safety"),
        (KeyboardInterrupt(), 130, "interrupted"),
    ],
)
def test_error_classification_is_strictly_typed(error, exit_code, category):
    classified = classify_error(error)
    assert (classified.exit_code, classified.category) == (exit_code, category)


@pytest.mark.parametrize(
    "arguments",
    [
        ["rename-watch", "--status", "--json-errors"],
        ["rename-watch", "--config", "c.json", "--unknown", "--json-errors"],
        [
            "rename-watch",
            "--config",
            "c.json",
            "--status",
            "--inspect-counters",
            "--json-errors",
        ],
    ],
)
def test_argparse_failures_are_one_usage_document(arguments, capsys):
    exit_code = run_status_command(arguments, 0)
    captured = capsys.readouterr()
    result = SimpleNamespace(
        returncode=exit_code, stdout=captured.out, stderr=captured.err
    )
    _assert_json_error(result, 2, "usage")


@pytest.mark.parametrize(
    "arguments",
    [
        ["--reset-counters", "--all-counters"],
        ["--reset-counters", "--job", "alpha"],
        ["--reset-counters", "--job", "alpha", "--all-counters", "--json"],
        ["--status", "--job", "alpha"],
        ["--dry-run"],
    ],
)
def test_semantic_option_failures_are_usage(tmp_path, arguments, capsys):
    config = _config(tmp_path)
    argv = ["rename-watch", "--config", os.fspath(config), *arguments, "--json-errors"]
    exit_code = run_status_command(argv, 0)
    captured = capsys.readouterr()
    result = SimpleNamespace(returncode=exit_code, stdout=captured.out, stderr=captured.err)
    _assert_json_error(result, 2, "usage")


def test_json_errors_reset_requires_yes_before_prompt(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    import indexly.rename_watch.counter_operator as operator

    monkeypatch.setattr(
        operator,
        "_confirm",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("confirmation was reached")
        ),
    )
    exit_code = run_status_command(
        [
            "rename-watch",
            "--config",
            os.fspath(config),
            "--reset-counters",
            "--job",
            "alpha",
            "--all-counters",
            "--json-errors",
        ],
        0,
    )
    captured = capsys.readouterr()
    _assert_json_error(
        SimpleNamespace(returncode=exit_code, stdout=captured.out, stderr=captured.err),
        2,
        "usage",
    )


def test_config_failure_and_human_failure_are_ascii_safe(tmp_path, capsys):
    bad_path = tmp_path / "caf\u00e9\n\x1b-invalid.json"
    exit_code = run_status_command(
        [
            "rename-watch",
            "--config",
            os.fspath(bad_path),
            "--status",
            "--json",
            "--json-errors",
        ],
        0,
    )
    captured = capsys.readouterr()
    _assert_json_error(
        SimpleNamespace(returncode=exit_code, stdout=captured.out, stderr=captured.err),
        3,
        "config_or_safety",
    )

    exit_code = run_status_command(
        ["rename-watch", "--config", os.fspath(bad_path), "--status"], 0
    )
    captured = capsys.readouterr()
    assert exit_code == 3 and captured.out == ""
    assert captured.err.count("\n") == 1
    assert "caf\\u00e9\\n\\u001b-invalid.json" in captured.err
    assert "\x1b" not in captured.err
    assert all(ord(character) < 128 for character in captured.err)


@pytest.mark.parametrize("kind", ["directory", "invalid_utf8"])
def test_config_read_environment_failures_are_config_or_safety(tmp_path, kind, capsys):
    config = tmp_path / "broken.json"
    if kind == "directory":
        config.mkdir()
    else:
        config.write_bytes(b"\xff\xfe")
    exit_code = run_status_command(
        [
            "rename-watch",
            "--config",
            os.fspath(config),
            "--status",
            "--json-errors",
        ],
        0,
    )
    captured = capsys.readouterr()
    _assert_json_error(
        SimpleNamespace(returncode=exit_code, stdout=captured.out, stderr=captured.err),
        3,
        "config_or_safety",
    )


def test_initialize_write_oserror_is_config_error(tmp_path, monkeypatch):
    config = tmp_path / "new.json"
    real_open = Path.open

    def fail_target_open(path, *args, **kwargs):
        if path == config:
            raise PermissionError("write refused")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_target_open)
    with pytest.raises(RenameWatchConfigError, match="could not be created"):
        initialize_settings(os.fspath(config))


def test_internal_and_interrupt_render_without_traceback_or_duplicate_output():
    for error, expected_code, category in (
        (RuntimeError("caf\u00e9\n\x1b"), 1, "internal"),
        (KeyboardInterrupt(), 130, "interrupted"),
    ):
        stream = io.StringIO()

        def fail(value=error):
            raise value

        assert run_with_error_contract(fail, json_errors=True, stream=stream) == expected_code
        value = stream.getvalue()
        assert value.count("\n") == 1 and "Traceback" not in value and "\x1b" not in value
        document = json.loads(value)
        assert document["error"]["category"] == category


def test_full_application_route_uses_same_contract_and_skips_update(tmp_path, monkeypatch, capsys):
    import indexly.indexly as application
    import indexly.update_utils as update_utils

    args = SimpleNamespace(
        command="rename-watch",
        json_errors=True,
        no_update_check=False,
        show_license=False,
        version=False,
        check_updates=False,
        status=False,
        inspect_counters=False,
        reset_counters=False,
        profile=None,
        func=lambda value: (_ for _ in ()).throw(RuntimeError("injected internal")),
    )

    class Parser:
        def parse_known_args(self):
            return args, []

        def parse_args(self):
            return args

    monkeypatch.setattr(application, "build_parser", lambda: Parser())
    monkeypatch.setattr(
        update_utils,
        "check_for_updates",
        lambda: (_ for _ in ()).throw(AssertionError("update check ran")),
    )
    with pytest.raises(SystemExit) as raised:
        application.main()
    captured = capsys.readouterr()
    _assert_json_error(
        SimpleNamespace(
            returncode=raised.value.code, stdout=captured.out, stderr=captured.err
        ),
        1,
        "internal",
    )


@pytest.mark.parametrize("primary_kind", ["config", "internal", "interrupted"])
@pytest.mark.parametrize("cleanup_kind", ["internal", "interrupted"])
def test_reset_primary_failure_beats_release_failure(
    tmp_path, monkeypatch, primary_kind, cleanup_kind
):
    config = _config(tmp_path)
    import indexly.rename_watch.counter_operator as operator

    cleanup_error = (
        RuntimeError("cleanup failed")
        if cleanup_kind == "internal"
        else KeyboardInterrupt()
    )

    class FailingReleaseLock:
        def __init__(self, path):
            self.path = path

        def acquire(self):
            return None

        def release(self):
            raise cleanup_error

    monkeypatch.setattr(operator, "WatchRootLock", FailingReleaseLock)

    if primary_kind == "config":
        def input_func(prompt):
            return "wrong confirmation"

        expected = RenameWatchConfigError
    elif primary_kind == "internal":
        def input_func(prompt):
            raise RuntimeError("primary internal")

        expected = RuntimeError
    else:
        def input_func(prompt):
            raise KeyboardInterrupt

        expected = KeyboardInterrupt

    with pytest.raises(expected):
        reset_counters(
            os.fspath(config),
            job_id="alpha",
            all_counters=True,
            input_func=input_func,
            stdin=_TTY(),
            base_dir=tmp_path / "runtime",
        )


@pytest.mark.parametrize("cleanup_error", [RuntimeError("cleanup"), KeyboardInterrupt()])
def test_reset_raises_release_failure_without_primary(tmp_path, monkeypatch, cleanup_error):
    config = _config(tmp_path)
    import indexly.rename_watch.counter_operator as operator

    class FailingReleaseLock:
        def __init__(self, path):
            self.path = path

        def acquire(self):
            return None

        def release(self):
            raise cleanup_error

    monkeypatch.setattr(operator, "WatchRootLock", FailingReleaseLock)
    with pytest.raises(type(cleanup_error)):
        reset_counters(
            os.fspath(config),
            job_id="alpha",
            all_counters=True,
            yes=True,
            base_dir=tmp_path / "runtime",
        )


@pytest.mark.parametrize(
    "primary_error",
    [RenameWatchConfigError("primary config"), RuntimeError("primary internal"), KeyboardInterrupt()],
)
@pytest.mark.parametrize("cleanup_error", [RuntimeError("cleanup"), KeyboardInterrupt()])
def test_service_primary_failure_beats_cleanup_failure(
    monkeypatch, primary_error, cleanup_error
):
    from indexly.rename_watch.service import RenameWatchService

    service = RenameWatchService([])
    monkeypatch.setattr(
        service,
        "_prepare_watch_paths",
        lambda: (_ for _ in ()).throw(primary_error),
    )
    monkeypatch.setattr(
        service,
        "_stop_and_release",
        lambda: (_ for _ in ()).throw(cleanup_error),
    )
    with pytest.raises(type(primary_error)) as raised:
        service.run_forever()
    assert raised.value is primary_error


@pytest.mark.parametrize("cleanup_error", [RuntimeError("cleanup"), KeyboardInterrupt()])
def test_service_raises_cleanup_failure_without_primary(monkeypatch, cleanup_error):
    from indexly.rename_watch.service import RenameWatchService

    service = RenameWatchService([])
    service.stop_event.set()
    monkeypatch.setattr(service, "_prepare_watch_paths", lambda: None)
    monkeypatch.setattr(service, "_acquire_root_locks", lambda: None)
    monkeypatch.setattr(service, "_recover_pending_moves", lambda: None)
    monkeypatch.setattr(service, "_start_observers", lambda: None)
    monkeypatch.setattr(
        service,
        "_stop_and_release",
        lambda: (_ for _ in ()).throw(cleanup_error),
    )
    with pytest.raises(type(cleanup_error)) as raised:
        service.run_forever()
    assert raised.value is cleanup_error


def test_reset_eof_is_config_or_safety(tmp_path):
    config = _config(tmp_path)

    def end_of_input(prompt):
        raise EOFError

    stream = io.StringIO()
    exit_code = run_with_error_contract(
        lambda: reset_counters(
            os.fspath(config),
            job_id="alpha",
            all_counters=True,
            input_func=end_of_input,
            stdin=_TTY(),
            base_dir=tmp_path / "runtime",
        ),
        json_errors=True,
        stream=stream,
    )
    assert exit_code == 3
    assert json.loads(stream.getvalue())["error"]["category"] == "config_or_safety"


@pytest.mark.parametrize(
    "prefix",
    [
        [sys.executable, "-m", "indexly"],
        [sys.executable, "-m", "indexly.indexly"],
        [
            os.fspath(
                Path(sysconfig.get_path("scripts"))
                / ("indexly.exe" if os.name == "nt" else "indexly")
            )
        ],
    ],
)
def test_entrypoints_share_json_error_contract_without_side_effects(tmp_path, prefix):
    environment = _subprocess_environment(tmp_path)
    result = subprocess.run(
        [*prefix, "rename-watch", "--status", "--json-errors"],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    _assert_json_error(result, 2, "usage")
    assert not (tmp_path / "home-must-not-exist").exists()
    assert not (tmp_path / "runtime-must-not-exist").exists()


@pytest.mark.parametrize("module", ["indexly", "indexly.indexly"])
def test_success_json_and_json_errors_keeps_success_channel_contract(tmp_path, module):
    config = _config(tmp_path, job_id="caf\u00e9")
    environment = _subprocess_environment(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            "rename-watch",
            "--config",
            os.fspath(config),
            "--inspect-counters",
            "--json",
            "--json-errors",
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout)["schema"] == "indexly.rename-watch.counters"
    assert not (tmp_path / "home-must-not-exist").exists()
    assert not (tmp_path / "runtime-must-not-exist").exists()


def test_json_errors_alone_keeps_human_success_output(tmp_path):
    config = _config(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "indexly",
            "rename-watch",
            "--config",
            os.fspath(config),
            "--status",
            "--json-errors",
        ],
        cwd=Path(__file__).parents[1],
        env=_subprocess_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert result.stdout.startswith("Rename-watch status\n")
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("extra", [[], ["--json-errors"]])
def test_plain_help_exits_zero_and_lists_shared_options(tmp_path, extra):
    result = subprocess.run(
        [sys.executable, "-m", "indexly", "rename-watch", *extra, "--help"],
        cwd=Path(__file__).parents[1],
        env=_subprocess_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert "--json-errors" in result.stdout
    assert "--reset-counters" in result.stdout


def test_top_level_no_update_check_keeps_json_error_contract(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "indexly",
            "--no-update-check",
            "rename-watch",
            "--status",
            "--json-errors",
        ],
        cwd=Path(__file__).parents[1],
        env=_subprocess_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    _assert_json_error(result, 2, "usage")
