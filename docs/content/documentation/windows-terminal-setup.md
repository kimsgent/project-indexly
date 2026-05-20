---
title: "Windows Development Environment Setup"
linkTitle: "Windows Setup"
slug: "windows-development-environment-setup"
icon: "mdi:microsoft-windows"
weight: 11
date: "2026-04-23"
lastmod: "2026-04-23"
draft: false
summary: "Set up the maintained Indexly contributor environment on Windows using dotfiles-windows, PowerShell 7, Scoop, winget, and the repo-native setup.ps1 workflow."
description: "Production-ready Windows setup guide for Indexly contributors. Covers PowerShell 7, Windows Terminal, Scoop, winget, dotfiles-windows bootstrap, project-indexly setup.ps1, verification, and troubleshooting."
keywords:
  - indexly windows development environment
  - indexly contributor setup windows
  - dotfiles-windows bootstrap
  - powershell 7 indexly
  - scoop winget developer setup
  - indexly setup.ps1
  - windows terminal indexly
aliases:
  - "/en/documentation/customizing-windows-terminal/"
  - "/en/documentation/windows-terminal-setup/"
type: docs
toc: true
categories:
  - Development
  - Environment Setup
tags:
  - windows
  - setup
  - powershell
  - dotfiles
  - developer
---

This guide documents the current maintained Windows contributor workflow for Indexly.

It replaces the old Windows Terminal customization page and aligns with the actual implementation in:

- `dotfiles-windows` for shell, terminal, package manager, and editor setup
- `project-indexly/setup.ps1` for repo-specific dependencies and virtual environment setup

{{% alert title="Scope" color="primary" %}}
Use this page when your goal is: "I want a Windows workstation that matches the maintained Indexly development flow."

If you only want to install Indexly as a user, start with [Install Indexly](indexly-installation.md) instead.
{{% /alert %}}

## What This Setup Covers

| Layer | Source of truth | Purpose |
| --- | --- | --- |
| Shell and workstation bootstrap | `dotfiles-windows/bootstrap.ps1` | Installs PowerShell 7, Windows Terminal support tools, Scoop packages, fonts, modules, and profile wiring |
| Day-to-day shell workflow | `dotfiles-windows/profile.ps1` and `modules/functions.ps1` | Loads prompt, helper commands, updater commands, and project setup helpers |
| Repo-specific onboarding | `project-indexly/setup.ps1` | Installs repo system packages from `winget.yaml`, creates `.venv`, and installs Python dependencies |
| Product installation docs | [Install Indexly](indexly-installation.md) | End-user install and verification guidance |

## Recommended Windows Flow

### 1. Start With Official Base Components

Recommended before you bootstrap:

- [PowerShell 7](https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows)
- [Windows Terminal](https://learn.microsoft.com/windows/terminal/install)
- [winget / App Installer](https://learn.microsoft.com/windows/package-manager/winget/)

You can run the bootstrap from Windows PowerShell, but the bootstrap now attempts to install PowerShell 7 first and then relaunch itself under `pwsh` when available.

### 2. Get The Dotfiles Repo

Clone the dotfiles repository:

```powershell
git clone https://github.com/kimsgent/dotfiles.git "$HOME\dotfiles"
Copy-Item -Recurse -Force "$HOME\dotfiles\dotfiles-windows" "$HOME\dotfiles-windows"
Set-Location "$HOME\dotfiles-windows"
```

If `git` is not installed yet, install it first with an official source such as `winget`:

```powershell
winget install --id Git.Git -e
```

### 3. Run The Maintained Windows Bootstrap

```powershell
.\bootstrap.ps1
```

The current bootstrap flow does all of the following:

1. Ensures PowerShell 7 is available.
2. Relaunches the bootstrap under `pwsh` when possible.
3. Installs base Windows packages with `winget`.
4. Installs Scoop if missing.
5. Ensures Scoop Git support before adding buckets.
6. Adds and refreshes the `extras` and `nerd-fonts` buckets when available.
7. Installs core CLI tools such as `neovim`, `ripgrep`, `fd`, `fzf`, `bat`, `eza`, `zoxide`, `jq`, and `delta`.
8. Installs Nerd Fonts when the `nerd-fonts` bucket is available.
9. Ensures Python and Node.js are available.
10. Installs maintained PowerShell modules such as `PSReadLine`, `PSFzf`, `Terminal-Icons`, `PSWindowsUpdate`, and `ImportExcel`.
11. Copies the maintained PowerShell profile and links Starship and Neovim config.

### 4. Restart The Shell And Verify

Close the current shell and open a new PowerShell 7 session.

Run these checks:

```powershell
pwsh --version
git --version
python --version
nvim --version
rg --version
fd --version
```

If the profile loaded correctly, you should also have helper commands such as:

```powershell
usp
update-powershell
setup-env
dev-mode
minimal-mode
```

## What The Windows Bootstrap Installs

### Managed By winget

The current bootstrap uses `winget` for Windows-native packages such as:

- `Microsoft.PowerShell`
- `Microsoft.WindowsTerminal`
- `JanDeDobbeleer.OhMyPosh`
- `Starship.Starship`
- `Microsoft.PowerToys`
- `OpenJS.NodeJS`
- Python when no working Python runtime is already present

### Managed By Scoop

The current bootstrap uses [Scoop](https://scoop.sh/) for CLI-focused tools and buckets. It currently installs or manages:

- `git`
- `neovim`
- `ripgrep`
- `fd`
- `fzf`
- `bat`
- `eza`
- `zoxide`
- `jq`
- `delta`
- `fastfetch`
- `mingw`

When the `nerd-fonts` bucket is available, it also installs:

- `Hack-NF`
- `Meslo-NF`

### Managed By PowerShell Gallery

The bootstrap also installs or updates PowerShell modules that improve the contributor shell experience:

- `PackageManagement`
- `PSReadLine`
- `PSFzf`
- `Terminal-Icons`
- `PSWindowsUpdate`
- `ImportExcel`

## Onboard The `project-indexly` Repository

After your workstation bootstrap is complete, move to the repo itself:

```powershell
Set-Location D:\project-indexly
```

The repo contains its own onboarding script:

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1
```

What `setup.ps1` does today:

- validates `winget`, Python, and repo files
- applies system packages from `winget.yaml`
- creates or reuses `.venv`
- upgrades `pip`, `setuptools`, and `wheel`
- installs `requirements.txt`
- installs `requirements-dev.txt`

Supported modes:

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1 -UpdateOnly
.\setup.ps1 -FreshInstall
.\setup.ps1 -Purge
```

If your dotfiles profile is already loaded, the same repo-native flow is also available through the helper command:

```powershell
setup-env indexly -check
setup-env indexly
```

## Recommended Validation For Contributors

After bootstrap and repo setup, verify the environment that actually matters for Indexly work:

```powershell
Set-Location D:\project-indexly
.venv\Scripts\Activate.ps1
python -m indexly --help
indexly --version
indexly show-help
indexly doctor
pytest -q
```

If you are working on optional features, install the matching extra groups described in [Install Indexly](indexly-installation.md) and [Indexly Developer Guide](developer.md).

## Optional Quality-Of-Life Commands

The maintained Windows profile adds several useful commands for contributors:

| Command | Purpose |
| --- | --- |
| `usp` | Run the logged package-manager update flow |
| `uspf` | Run the fuller update variant |
| `usd` | Preview updates without making changes |
| `upd` | View the latest structured update log |
| `update-powershell` | Update the PowerShell 7 runtime using `winget` first, then the official MSI fallback |
| `fdg` / `rgg` | Fuzzy file search and ripgrep-driven code search |
| `dev-mode` / `minimal-mode` | Switch Starship prompt mode |

## Troubleshooting

### Bootstrap Started In Windows PowerShell Instead Of PowerShell 7

This is expected on a clean machine.

The current bootstrap attempts to install PowerShell 7 first, then relaunches itself under `pwsh`. If it cannot, it continues with a warning and you can verify later with:

```powershell
pwsh --version
update-powershell
```

### Scoop Says Git Is Required For Buckets

The maintained bootstrap now installs or detects Scoop Git support before adding buckets.

If you still see bucket-related Git errors:

```powershell
git --version
scoop update
usp
```

If `git` is still missing in the current session, restart PowerShell and rerun the bootstrap.

### Scoop Cannot Find `Hack-NF` Or `Meslo-NF`

This usually means the `nerd-fonts` bucket is unavailable or stale, not that the fonts are universally unsupported.

Use this order:

```powershell
scoop bucket list
scoop update
usp
```

If the `nerd-fonts` bucket is still missing, rerun the bootstrap after Git and Scoop are healthy.

### Bootstrap Runs Without Administrator Rights

A non-elevated run is acceptable for most of the environment.

Current behavior:

- file symlinks may fall back to hard links or file copies
- Neovim directory linking may fall back to a junction
- some Windows Update or package operations may still require an elevated shell

Typical admin-sensitive areas:

- `PSWindowsUpdate` operations
- some `winget` installs or configuration changes
- symbolic links when Developer Mode is not enabled

### `setup.ps1` Fails During `winget configure`

`project-indexly/setup.ps1` applies `winget.yaml`, and some packages may prompt, fail, or require elevation depending on machine policy.

Start with:

```powershell
.\setup.ps1 -CheckOnly
```

Then rerun the full setup in an elevated shell if `winget` or package policy blocks the import.

### Script Execution Is Blocked

If PowerShell blocks local scripts, use a per-user policy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Related Pages

- [Linux Development Environment Setup](linux-development-environment.md)
- [Install Indexly](indexly-installation.md)
- [Indexly Developer Guide](developer.md)
