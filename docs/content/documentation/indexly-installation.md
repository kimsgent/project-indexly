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
lastmod: "2026-07-23"
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

{{% alert title="Contributor Note" color="info" %}}
This page covers product installation.

If you are preparing a contributor workstation rather than just installing the CLI, use:

- [Windows Development Environment Setup](windows-terminal-setup.md)
- [Linux Development Environment Setup](linux-development-environment.md)
- [Indexly Developer Guide](developer.md)
{{% /alert %}}

## 1. Install on macOS/Linux with Homebrew (Recommended)

```bash
brew tap kimsgent/indexly
brew install indexly
```

Verify:

```bash
command -v indexly
indexly --version
indexly --help
```

If you also have a pip installation, `command -v indexly` identifies which
executable the shell will run. Confirm it is the Homebrew executable before
managing Homebrew extras.

If a shell shim or another installation makes that result unclear, call the
brewed executable directly:

```bash
"$(brew --prefix indexly)/bin/indexly" extras status
"$(brew --prefix indexly)/bin/indexly" extras install documents
```

Homebrew installs the lightweight Indexly core. List and install optional
groups on demand:

```bash
indexly extras list
indexly extras install documents
indexly extras status
```

Available groups are `documents`, `analysis`, `visualization`, `pdf_export`,
and `backup`. Remove a group with:

```bash
indexly extras uninstall documents
```

Homebrew extras are stored in a user-owned overlay scoped to the installed
Indexly version, Python ABI, and platform architecture. The overlay is outside
the Homebrew Cellar and does not require `sudo`, `pip --user`, or a
`PYTHONPATH` wrapper. Do not use generic `pip` to add dependencies to brewed
Indexly.

Selected groups share one managed environment. Indexly resolves their combined
requirements together so two groups cannot silently load different copies of a
shared dependency. Adding or removing a group rebuilds that environment
atomically and may download packages; a failed rebuild leaves the previous
working environment in place.

If status reports an invalid managed environment, reset only the current
runtime's managed packs and reinstall the groups you need:

```bash
indexly extras reset
indexly extras install documents
```

If `brew` is already installed on Linux but not available in the current shell, initialize Homebrew first:

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

## 4. Optional Feature Packs for pip and virtual environments

The managed `indexly extras install <group>` command also works for pip
installations. If you prefer to manage optional packages directly in pip, run
the following with the same Python environment that contains Indexly:

```bash
python -m pip install "indexly[documents]"
python -m pip install "indexly[analysis]"
python -m pip install "indexly[visualization]"
python -m pip install "indexly[pdf_export]"
python -m pip install "indexly[backup]"
```

Install all optional groups:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export,backup]"
```

On Windows installations made with the `py` launcher, use that same launcher
instead:

```powershell
py -m pip install "indexly[documents]"
```

## 5. PDF Extraction and OCR

The `documents` group installs the Python dependencies used for rich document
formats, ordinary PDF extraction, and OCR integration.

OCR has one additional external requirement: the Tesseract executable. On
macOS or Linuxbrew, install it separately:

```bash
brew install tesseract
```

On Windows or non-Homebrew Linux, install Tesseract with the platform package
manager and ensure the `tesseract` executable is on `PATH`.

## 6. First Run

```bash
indexly index /path/to/folder
indexly search "invoice"
indexly regex "[A-Z]{3}-\\d{4}"
```

## 7. Upgrade and Uninstall

Upgrade:

```bash
# pip
python -m pip install --upgrade indexly

# brew
brew upgrade indexly
indexly extras status
```

A Homebrew upgrade can change the Indexly version, Python ABI, or platform used
to scope the extras overlay. If status reports a needed group as
`not-installed` or `invalid` for the current runtime, install it again:

```bash
indexly extras install documents
```

Older overlays are never loaded, but Indexly retains them so an older runtime
can still use them. They can be large, and `brew uninstall indexly` does not
remove them. To reclaim space:

1. Run `indexly extras status --json`.
2. Review entries under `stale`; each `path` names one exact old
   `environment` directory.
3. After confirming that runtime is no longer needed, remove only that
   displayed `environment` directory with your file manager or operating-system
   tools.

Do not delete the whole `INDEXLY_HOME` directory: it also contains search
indexes, profiles, cache data, and logs. `indexly extras reset` intentionally
removes only the current runtime's managed environment, not stale environments.

Uninstall:

```bash
# pip
python -m pip uninstall indexly

# brew
brew uninstall indexly
```

To remove one Homebrew-managed optional group without uninstalling Indexly:

```bash
indexly extras uninstall documents
```

## 8. Developer Setup (All Platforms)

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
python -m pip install -e ".[documents,analysis,visualization,pdf_export,backup]"
python -m pip install pytest pytest-cov flake8 black isort mypy build twine
```

Verify:

```bash
indexly --help
```

On Windows, contributors can also use the repo-native bootstrap script:

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1
```

## 9. Continuous Rename Watch Service

First install and validate Indexly normally. For an unattended Rename Watch
deployment, use a dedicated, versioned virtual environment so upgrades and
rollbacks do not modify the executable beneath a running service.

See [Operate Rename Watch as a Service](rename-watch-service-operation.md) for
the supported WinSW, systemd, and launchd templates, least-privilege accounts,
health and readiness probes, log retention, upgrades, and rollback.

## 10. Troubleshooting

- `indexly: command not found`
  - Restart terminal.
  - Confirm install succeeded (`pip show indexly` or `brew list indexly`).
- Missing feature message (for example analysis/documents)
  - Homebrew: run `indexly extras status`, then
    `indexly extras install <group>`.
  - pip/virtual environment: install the matching pip extra from section 4.
- Unsure which Indexly installation is active
  - Run `command -v indexly` on macOS/Linux.
  - Manage Homebrew extras only through the brewed executable.
- OCR unavailable after installing `documents`
  - Install Tesseract separately and confirm `tesseract` is on `PATH`.
- Homebrew on Linux not detected
  - Run `eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"` and retry.
- Need a quick environment check
  - Run `indexly doctor`.

Indexly is now ready to use.

See also [Windows Development Environment Setup](windows-terminal-setup.md), [Linux Development Environment Setup](linux-development-environment.md), and [Indexly Developer Guide](developer.md).
