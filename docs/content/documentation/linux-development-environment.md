---
title: "Linux Development Environment Setup"
linkTitle: "Linux Setup"
slug: "linux-development-environment-setup"
icon: "mdi:linux"
weight: 12
date: "2026-04-23"
lastmod: "2026-04-23"
draft: false
summary: "Current-state Linux setup notes for Indexly contributors based on the existing dotfiles repository. Documents what is available today and what is still incomplete."
description: "Reality-based Linux contributor environment guide for Indexly. Covers the current status of the dotfiles repo on Linux, the supported manual setup path, Homebrew-based package parity, and limitations you should account for."
keywords:
  - indexly linux development environment
  - indexly contributor setup linux
  - dotfiles linux status
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

This page documents the current Linux state of the maintained contributor environment.

{{< alert title="Current Status" color="warning" >}}
The `dotfiles` repository does **not** currently provide a supported automated Linux bootstrap.

The top-level `bootstrap` script detects Linux, then exits with `Linux bootstrap is not implemented yet.`

Use this page as an honest guide to the current manual path, not as a claim of full Linux parity with Windows.
{{< /alert >}}

## What Exists Today

The current `dotfiles` repository still provides useful Linux-relevant assets:

- `.zshrc`
- `nvim/init.lua`
- `.config/starship/starship.toml`
- `tmux/.tmux.conf`
- `tools/bootstrap_project.sh`
- `Brewfile`

What does **not** exist today:

- a supported Linux automation path in `./bootstrap`
- a Linux equivalent of `dotfiles-windows/bootstrap.ps1`
- a finalized Linux contributor workflow with the same level of integration as Windows

## Recommended Linux Approach Today

For Linux contributors, the current reliable path is:

1. install the core shell and CLI tooling manually
2. optionally use the existing dotfiles files as configuration references
3. set up `project-indexly` manually using Python virtual environments

This keeps the workflow honest and aligned with the codebase as it exists now.

## Package And Tooling Reference

The current `Brewfile` in `dotfiles` is the clearest package parity reference. It includes:

- `git`
- `neovim`
- `tmux`
- `fzf`
- `zoxide`
- `ripgrep`
- `bat`
- `eza`
- `fd`
- `pyenv`
- `nvm`
- `direnv`
- `starship`
- `zsh-autosuggestions`
- `zsh-syntax-highlighting`
- `powershell`

If you already use [Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux), you can use the `Brewfile` as a package reference.

If you use a distro-native package manager instead, install the closest equivalents from your distro repositories.

## Manual Linux Bootstrap Pattern

### 1. Install Core Tooling

Example with Homebrew on Linux:

```bash
brew install git neovim tmux fzf zoxide ripgrep bat eza fd pyenv nvm direnv starship zsh-autosuggestions zsh-syntax-highlighting
```

This is not yet wrapped in a supported automation script for Linux.

### 2. Apply Dotfiles Manually If You Want Parity

The Linux-compatible parts of the repo can be wired manually with symlinks such as:

```bash
ln -sf /path/to/dotfiles/.zshrc ~/.zshrc
mkdir -p ~/.config/starship ~/.config/nvim
ln -sf /path/to/dotfiles/.config/starship/starship.toml ~/.config/starship/starship.toml
ln -sf /path/to/dotfiles/nvim/init.lua ~/.config/nvim/init.lua
ln -sf /path/to/dotfiles/tmux/.tmux.conf ~/.tmux.conf
```

Do this only if you actively want the shared shell and editor conventions. It is not currently presented as a finalized Linux bootstrap contract.

### 3. Use Indexly's Manual Developer Setup

Once your shell and toolchain are ready:

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
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

## What Is Linux-Safe To Rely On Today

Reasonable assumptions based on the current repos:

- Indexly itself supports Linux as a runtime platform.
- The documented install path via Homebrew or `pip` remains valid. See [Install Indexly](indexly-installation.md).
- The `dotfiles` repo provides useful config and package references.
- The project bootstrap helper `tools/bootstrap_project.sh` is shell-based and Linux-friendly in style.

What you should **not** rely on yet:

- `./bootstrap` as a supported Linux setup command
- a fully automated Linux workstation bootstrap
- Linux behavior matching Windows package manager automation one-to-one

## Linux Gaps To Keep In Mind

### No Supported Automated Bootstrap

The top-level `bootstrap` script explicitly aborts on Linux today. That is the clearest indicator that Linux remains a partial workflow.

### `bootstrap.sh` Is macOS-Oriented

The current `bootstrap.sh` assumes a macOS-style Homebrew layout and macOS shell setup flow. It is not positioned as a Linux script even though some individual commands may look portable.

### Repo-Specific Windows Automation Does Not Carry Over

`project-indexly/setup.ps1` is Windows-specific. On Linux, use the manual developer setup path from [Indexly Developer Guide](developer.md) instead.

## When To Use This Page vs Other Setup Docs

- Use this page when your question is: "What is the current Linux state of the maintained contributor environment?"
- Use [Windows Development Environment Setup](windows-terminal-setup.md) when you want the primary, maintained contributor workflow.
- Use [Install Indexly](indexly-installation.md) when you only need to install or run Indexly, not replicate the contributor workstation.
- Use [Indexly Developer Guide](developer.md) when you are already inside the repo and need packaging, testing, and architecture guidance.
