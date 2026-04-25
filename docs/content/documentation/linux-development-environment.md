---
title: "Linux Development Environment Setup"
linkTitle: "Linux Setup"
slug: "linux-development-environment-setup"
icon: "mdi:linux"
weight: 12
date: "2026-04-23"
lastmod: "2026-04-25"
draft: false
summary: "Set up the maintained Indexly contributor environment on Ubuntu/Linux using dotfiles-linux, Bash, Homebrew for Linux, Neovim, Starship, and Project-Indexly docs helpers."
description: "Production-ready Linux contributor environment guide for Indexly. Covers the standalone dotfiles-linux bootstrap flow, full dotfiles repo mode, local profile sync with update-lp, Homebrew/Linuxbrew tooling, Project-Indexly docs commands, verification, rollback, and known Ubuntu support notes."
keywords:
  - indexly linux development environment
  - indexly contributor setup linux
  - dotfiles-linux bootstrap
  - ubuntu developer setup
  - homebrew linux indexly
  - linuxbrew developer setup
type: docs
toc: true
categories:
  - Development
  - Environment Setup
tags:
  - linux
  - setup
  - dotfiles
  - developer
---

This guide documents the maintained Linux contributor workflow for Indexly.

Use it when your goal is: "I want an Ubuntu/Linux workstation that can develop Project-Indexly, build the Hugo/Docsy docs, and use the same shell/editor conventions as the maintained dotfiles workflow."

{{< alert title="Current Status" color="success" >}}
Linux setup is now implemented through `dotfiles-linux` in the `dotfiles` repository.

The top-level `dotfiles/bootstrap` dispatcher detects Linux and routes to `dotfiles-linux/bootstrap.sh`. The Linux bundle can also be copied to `~/dotfiles-linux` and run without the full dotfiles repo present.
{{< /alert >}}

## Supported Setup Modes

There are two supported ways to run the Linux bootstrap.

| Mode | Best for | Command shape |
| --- | --- | --- |
| Standalone bundle | New machines, machines without the full dotfiles repo, or your normal Linux runtime flow | `cd ~/dotfiles-linux && ./bootstrap.sh` |
| Full repo mode | Maintaining the dotfiles repo itself or testing shared repo changes | `cd ~/dev/configs/dotfiles && ./bootstrap` |

The standard/default Linux workflow is the standalone bundle:

```bash
cp -a ~/dev/configs/dotfiles/dotfiles-linux ~/dotfiles-linux
cd ~/dotfiles-linux
./bootstrap.sh
```

If a new machine does not have the full dotfiles repo, copy or download the `dotfiles-linux` directory to `~/dotfiles-linux` first, then run the same bootstrap command.

## What The Linux Bootstrap Sets Up

The Linux suite is Bash-first and keeps Homebrew for Linux as the shared package layer.

It manages:

- `~/.bashrc`
- `~/.gitconfig`
- `~/.tmux.conf`
- `~/.config/nvim`
- `~/.config/starship/starship.toml`
- `~/dev/tools/indexly-docs`
- `~/bin/dev`
- `~/bin/dev-new`

It backs up existing non-symlink targets before replacing them. Backup files use names such as:

```text
~/.bashrc.backup.20260424-213000
```

## Fresh Ubuntu Flow

On a clean Ubuntu machine, install the minimum bootstrap prerequisites first:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates
```

Then get the Linux bundle onto the machine and run it:

```bash
cd ~
# Copy dotfiles-linux here by git checkout, archive, scp, rsync, or your preferred transfer method.
cd ~/dotfiles-linux
./bootstrap.sh
```

After bootstrap, restart the terminal or run:

```bash
source ~/.bashrc
```

Then inspect the available helper commands:

```bash
show-help
```

## Full Dotfiles Repo Flow

If the full dotfiles repo is present:

```bash
mkdir -p ~/dev/configs
cd ~/dev/configs
git clone git@github.com:kimsgent/dotfiles.git
cd dotfiles
./bootstrap
```

This mode is useful when you are editing shared dotfiles files such as the Neovim config, Starship config, or project helper scripts.

## How Symlink Priority Works

The symlink script is designed for both workflows.

The active local profile normally points at the standalone bundle:

```text
~/.bashrc -> ~/dotfiles-linux/.bashrc
~/.config/starship/starship.toml -> ~/dotfiles-linux/config/starship/starship.toml
~/.config/nvim -> ~/dotfiles-linux/config/nvim
```

That keeps day-to-day shells stable even while the source repo is being edited.

When run from `~/dotfiles-linux`, the symlink script prefers bundled files inside:

```text
~/dotfiles-linux/config/
~/dotfiles-linux/tools/
```

When run from the full dotfiles repo, it can prefer shared repo files such as:

```text
~/dev/configs/dotfiles/nvim
~/dev/configs/dotfiles/.config/starship/starship.toml
~/dev/configs/dotfiles/git/.gitconfig
```

To force shared repo mode from a standalone location, set `DOTFILES_ROOT` explicitly:

```bash
DOTFILES_ROOT=~/dev/configs/dotfiles ~/dotfiles-linux/bootstrap.sh
```

For normal Linux use, keep the live profile linked to `~/dotfiles-linux` and use `update-lp` when repo changes need to be copied into that local bundle.

## Installed Tooling

The bootstrap installs apt prerequisites, Homebrew for Linux when needed, and Homebrew packages from `dotfiles-linux/Brewfile`.

Core CLI/global tooling includes:

- `git`
- `gh`
- `neovim`
- `tmux`
- `fzf`
- `zoxide`
- `ripgrep`
- `bat`
- `eza`
- `fd`
- `direnv`
- `starship`
- `jq`
- `shellcheck`
- `shfmt`
- `pyenv`
- `nvm`
- `rbenv`
- `ruby-build`

Project-Indexly docs tooling includes:

- Hugo Extended
- Go
- Node LTS through `nvm`
- npm
- local PostCSS/Pagefind dependencies from `docs/package.json`
- Pandoc/ImageMagick-related utilities for docs and asset workflows

## Project-Indexly Docs Helper

After bootstrap, use `idxdocs` from any shell where the managed `.bashrc` is loaded:

```bash
idxdocs verify
idxdocs serve
idxdocs build-local
idxdocs build-prod
idxdocs smoke
idxdocs update-modules
idxdocs brew-test
```

The commands do the following:

| Command | Purpose |
| --- | --- |
| `idxdocs verify` | Checks Hugo Extended, Go, Node, npm, local PostCSS, and local Pagefind |
| `idxdocs serve` | Runs the local Hugo docs server through `npm run dev` |
| `idxdocs build-local` | Runs the existing docs build script |
| `idxdocs build-prod` | Runs a production-style Hugo build plus local Pagefind |
| `idxdocs smoke` | Confirms `docs/public` and Pagefind output exist after a build |
| `idxdocs update-modules` | Runs Hugo module update, tidy, and vendor flow |
| `idxdocs brew-test` | Tests `brew tap kimsgent/indexly`, installs/reinstalls `indexly`, and runs `indexly --version` |

Direct path equivalent:

```bash
~/dev/tools/indexly-docs verify
```

## Project-Indexly Repo Setup

Once the workstation is ready:

```bash
mkdir -p ~/dev/projects
cd ~/dev/projects
git clone git@github.com:kimsgent/project-indexly.git
cd project-indexly
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[documents,analysis,visualization,pdf_export]"
python -m pip install pytest pytest-cov flake8 black isort mypy build twine hatch
```

Verify:

```bash
indexly --help
indexly show-help
indexly doctor
pytest -q
```

## Updating The Linux Environment

There are three update paths, and they intentionally do different jobs.

### Sync Repo Changes Into The Local Profile

On a development machine, the full repo is the source of truth and `~/dotfiles-linux` is the live local profile bundle. After changing files in:

```text
~/dev/configs/dotfiles/dotfiles-linux
```

run:

```bash
update-lp
```

`update-lp` copies the repo bundle into `~/dotfiles-linux`, then relinks managed files from the local bundle. This is the command to use after editing the repo version of Bash, Starship, Neovim, Git, tmux, or helper scripts.

Dry run:

```bash
update-lp --dry-run
```

On a non-development machine where `~/dev/configs/dotfiles` is absent, `update-lp` exits with a friendly "nothing changed" message.

### Relink The Already-Synced Local Bundle

Use this when the local bundle is already correct and you only need to recreate symlinks:

```bash
update-profile
```

This relinks from `~/dotfiles-linux`. It does not copy from the source repo.

### Update Packages And Tooling

Use the managed package update helper:

```bash
update-system
```

Dry run:

```bash
update-system --dry-run
```

### Reload Current Shells

Existing terminal sessions do not automatically reload a changed `.bashrc`. After `update-lp` or `update-profile`, run:

```bash
reload-profile
```

New terminal windows pick up the updated profile automatically.

## Useful Shell Commands

The Linux profile exposes a small discoverable command surface:

```bash
show-help
```

Common helpers include:

- `idxdocs` for Project-Indexly documentation tasks
- `update-lp` to sync repo `dotfiles-linux` changes into the live `~/dotfiles-linux` bundle
- `update-profile` to relink managed files from the already-synced local bundle
- `gstatus` / `gst` for Git status
- `gbranch` / `gbr` for Git branches without opening a pager
- `gcheckout` / `gco` for branch checkout
- `gpull` / `gpl` for fast-forward pulls
- `reload-profile` to reload `~/.bashrc`
- `bootstrap-linux` to call the Linux bootstrap directly

The profile intentionally leaves `gs` available for Ghostscript on Linux.

## Ubuntu Support Notes

Validated environment:

- Ubuntu 24.04.4 LTS
- Bash
- GNOME on Wayland
- Homebrew for Linux

Expected support:

- Ubuntu 22.04 or newer
- closely related Debian-based systems with `apt-get`, Bash, sudo, and network access to GitHub, Homebrew, and npm registries

Wayland note: the shell setup does not force Wayland-only environment variables. It should also work from SSH, TTY, and X11 sessions.

## Known Limits

- GUI app installation is documented in the dotfiles README but is not forced by bootstrap.
- SSH config is not bundled into standalone `dotfiles-linux`; this avoids copying machine-specific credentials or host policy.
- `update-lp` is mainly for development machines with `~/dev/configs/dotfiles`; standalone machines can keep using `update-profile` and `update-system`.
- Netlify still runs its configured production command. `idxdocs build-prod` uses local Pagefind for repeatable local validation.
- `project-indexly/setup.ps1` remains Windows-specific. Linux contributors should use the Bash/bootstrap and Python virtual environment flow above.

## Rollback

For any replaced file, find the timestamped backup next to it:

```bash
ls -la ~ | grep backup
```

Restore example:

```bash
rm ~/.bashrc
mv ~/.bashrc.backup.YYYYMMDD-HHMMSS ~/.bashrc
```

For symlinked config directories, remove the symlink and restore the backup directory if one was created:

```bash
rm ~/.config/nvim
mv ~/.config/nvim.backup.YYYYMMDD-HHMMSS ~/.config/nvim
```

## Related Pages

- [Windows Development Environment Setup](windows-terminal-setup.md)
- [Install Indexly](indexly-installation.md)
- [Indexly Developer Guide](developer.md)
