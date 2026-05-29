# Docker Test Harness

This folder documents the local Docker path for running Indexly tests in disposable Linux containers.

## Purpose

Use this when you want a clean Linux environment that is separate from the Windows checkout, WSL profile, and local `.venv-codex`.

The default image follows the GitHub Actions Linux test shape:

- Python 3.13 by default
- dependencies from `requirements-ci.txt`
- editable install of the local checkout
- pytest with the same fast-fail style as CI lite
- selected external tools used by Indexly health checks and file workflows: Tesseract, ExifTool, SQLite, and zstd

## Commands

From the repository root:

```bash
docker compose -f compose.test.yml build test-py313
docker compose -f compose.test.yml run --rm test-py313
```

Run the Python 3.12 comparison container:

```bash
docker compose -f compose.test.yml run --rm test-py312
```

Open an interactive shell in the test image:

```bash
docker compose -f compose.test.yml run --rm shell
```

Inside the shell, useful smoke checks are:

```bash
python -m pytest -q --maxfail=3 --disable-warnings
indexly --version
indexly doctor
```

## WSL Notes

The preferred place to run these commands is the WSL checkout under:

```text
~/dev/projects/project-indexly
```

Running Docker against a repository inside the WSL filesystem avoids the slower file sharing and permission edge cases that can happen when bind-mounting a Windows path into a Linux container.

## Risks And Limits

The container validates Linux packaging and test behavior. It does not replace native macOS checks for Homebrew formula behavior, macOS paths, or bottle-specific issues.
