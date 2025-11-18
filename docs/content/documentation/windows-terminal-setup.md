---
title: "Customizing Windows Terminal"
slug: "customizing-windows-terminal"
icon: "mdi:microsoft-windows"
weight: 4
date: 2025-10-12
summary: "Set up Windows Terminal like a pro — featuring Chocolatey, Scoop, Oh My Posh, Neovim, fzf, and PowerShell enhancements."
description: "Learn how to fully customize Windows Terminal for productivity and aesthetics. This step-by-step guide covers installing Chocolatey, Scoop, Oh My Posh, Neovim, PowerShell modules, fzf, and fonts to build a powerful Linux-like development environment on Windows. Created collaboratively with ChatGPT."
keywords: [
  "Windows Terminal customization",
  "PowerShell productivity setup",
  "Oh My Posh configuration",
  "Chocolatey install guide",
  "Scoop package manager tutorial",
  "Neovim on Windows setup",
  "fzf PowerShell integration",
  "Windows developer environment",
  "Chris Titus PowerShell setup",
  "modern terminal tools"
]
cta: "Transform your terminal experience"
canonicalURL: "/en/documentation/customizing-windows-terminal/"
type: docs
categories:
    - Platform Setup 
    - Usage
tags:
    - windows
    - setup
    - configuration
    - usage
    - productivity
---

_A collaborative guide with ChatGPT_

---

## Prerequisites

Ensure you have the latest PowerShell and script execution rights:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
````

---

## Step 1: Install Package Managers

### Chocolatey

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; `
[System.Net.ServicePointManager]::SecurityProtocol = `
[System.Net.ServicePointManager]::SecurityProtocol -bor 3072; `
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

📖 [Official Chocolatey Guide](https://docs.chocolatey.org/en-us/choco/setup/)

### Scoop

```powershell
irm get.scoop.sh | iex
scoop bucket add extras
```

📖 [Scoop Website](https://scoop.sh)


---

## Step 2: Upgrade & Install Power Tools

### Oh My Posh

```powershell
winget upgrade JanDeDobbeleer.OhMyPosh -s winget
```

📖 [Oh My Posh GitHub](https://github.com/JanDeDobbeleer/oh-my-posh)

### Windows Updates via PowerShell

```powershell
Install-Module PSWindowsUpdate
Add-WUServiceManager -MicrosoftUpdate
Get-WindowsUpdate
Install-WindowsUpdate -MicrosoftUpdate -AcceptAll -AutoReboot | Out-File "C:\($env.computername-$(Get-Date -f yyyy-MM-dd))-MSUpdates.log" -Force
```

---

## Step 3: Configure Neovim

```powershell
choco install -y neovim git ripgrep wget fd unzip gzip mingw make
git clone https://github.com/nvim-lua/kickstart.nvim.git $env:USERPROFILE\AppData\Local\nvim\
pip3 install --user --upgrade pynvim
```

📖 [Kickstart.nvim GitHub](https://github.com/nvim-lua/kickstart.nvim)

---

## Step 4: Add Shell Enhancers

### fzf (Fuzzy Finder)

```powershell
choco install fzf
Install-Module -Name PSFzf
```

📖 [fzf GitHub](https://github.com/junegunn/fzf)

### PowerShell Editor Services

```powershell
Install-Module PSReadLine -Force
Import-Module PSReadLine
Install-Module InvokeBuild -Scope CurrentUser
Install-Module platyPS -Scope CurrentUser
Install-Module -Name PowerShellEditorServices -Repository PSGallery
```

### Excel Support

```powershell
Install-Module -Name ImportExcel -Scope CurrentUser -Force
pip install openpyxl
```

📖 [ImportExcel GitHub](https://github.com/dfinke/ImportExcel)


---

## Step 5: Beautify Terminal

```powershell
scoop bucket add nerd-fonts
scoop install Hack-NF
scoop install eza bat fd fastfetch
```


---

## Bonus: Titus PowerShell Setup

```powershell
irm "https://github.com/ChrisTitusTech/powershell-profile/raw/main/setup.ps1" | iex
```

📖 [Chris Titus GitHub](https://github.com/ChrisTitusTech)

---

## Optional: jq & ripgrep-all

```powershell
choco install jq
choco install ripgrep-all
```

📖 [ripgrep-all GitHub](https://github.com/phiresky/ripgrep-all)

---

## Sources & Credits

* [Chocolatey](https://chocolatey.org/)
* [Scoop](https://scoop.sh)
* [Oh My Posh](https://ohmyposh.dev/)
* [Chris Titus Tech](https://github.com/ChrisTitusTech)
* [ripgrep-all](https://github.com/phiresky/ripgrep-all)
* [fzf](https://github.com/junegunn/fzf)
* [Kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim)
* [ImportExcel](https://github.com/dfinke/ImportExcel)
* Brett Terpstra — inspiration from [Ripple (GitHub gist)](https://gist.github.com/ttscoff/efe9c1284745c4df956457a5707e7450) and his [homepage article](https://brettterpstra.com/2025/06/30/ripple-an-indeterminate-progress-indicator/)  
* Michael Bazzel — inspiration drawn from his OSINT books on extraction techniques

> ✨ Created collaboratively with **ChatGPT** based on N. K. Franklin-Gent’s prompt.
