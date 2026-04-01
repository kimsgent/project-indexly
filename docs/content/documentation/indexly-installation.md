---
title: "Install Indexly – Setup, Configuration & First Run"
description: "Install Indexly on Windows, macOS, and Linux with clear steps for pip and Homebrew. Includes verification, optional feature packs, and troubleshooting."
keywords:
  - install indexly
  - indexly installation
  - indexly setup
  - python file indexing tool
  - local search cli
  - indexly homebrew
  - indexly pip
  - brew install indexly
  - windows install indexly
  - linux install indexly
weight: 10
type: docs
toc: true
aliases:
  - /installation/
  - /getting-started/installation/
---

Indexly runs on Windows, macOS, and Linux.

For most users:
- Use **Homebrew** on macOS/Linux
- Use **pip** on Windows

## 1. Install on macOS/Linux with Homebrew (Recommended)

```bash
brew tap kimsgent/indexly
brew install indexly
```

Verify:

```bash
indexly --version
indexly --help
```

No manual `PYTHONPATH` wrapper is required for current Homebrew releases.

If `brew` is not available yet on Linux, initialize Homebrew in your shell first:

```bash
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
```

## 2. Install on Windows with pip (Recommended)

```powershell
py -m pip install --upgrade pip
py -m pip install indexly
```

Verify:

```powershell
indexly --version
indexly --help
```

If the `indexly` command is not found immediately, restart the terminal and run again.

## 3. Cross-platform pip install (Alternative)

```bash
python -m pip install --upgrade pip
python -m pip install indexly
```

Verify:

```bash
indexly --version
```

## 4. Optional Feature Packs

Indexly ships with a lightweight core install. Add extras only when needed:

```bash
python -m pip install "indexly[documents]"
python -m pip install "indexly[analysis]"
python -m pip install "indexly[visualization]"
python -m pip install "indexly[pdf_export]"
```

Install all optional groups:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export]"
```

## 5. First Run

```bash
indexly index /path/to/folder
indexly search "invoice"
indexly regex "[A-Z]{3}-\\d{4}"
```

## 6. Upgrade and Uninstall

Upgrade:

```bash
# pip
python -m pip install --upgrade indexly

# brew
brew upgrade indexly
```

Uninstall:

```bash
# pip
python -m pip uninstall indexly

# brew
brew uninstall indexly
```

## 7. Developer Setup (All Platforms)

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly
python -m venv .venv
```

Activate:

- macOS/Linux: `source .venv/bin/activate`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`

Install editable package with optional extras:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[documents,analysis,visualization,pdf_export]"
python -m pip install pytest pytest-cov flake8 black isort mypy build twine
```

Verify:

```bash
indexly --help
```

## 8. Troubleshooting

- `indexly: command not found`
  - Restart terminal.
  - Confirm install succeeded (`pip show indexly` or `brew list indexly`).
- Missing feature message (for example analysis/documents)
  - Install the matching extra group from section 4.
- Homebrew on Linux not detected
  - Run `eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"` and retry.
- Need a quick environment check
  - Run `indexly doctor`.

Indexly is now ready to use.

See also [Customizing Windows Terminal](windows-terminal-setup.md).
