<#
Indexly Environment Bootstrap + Update Script (Windows)

This script automates:
1. Installing/upgrading system dependencies via winget (from winget.yaml)
2. Creating/activating Python virtual environment (.venv)
3. Upgrading pip, setuptools, wheel
4. Installing/upgrading Python dependencies (requirements.txt + requirements-dev.txt)

⚡ Usage:
  # Full bootstrap (apps + Python deps)
  .\setup.ps1

  # Update only (skip bootstrap steps, just upgrade apps + deps)
  .\setup.ps1 -UpdateOnly

  # Fresh install (force recreate venv + reinstall all)
  .\setup.ps1 -FreshInstall

  # Purge (delete .venv without reinstalling)
  .\setup.ps1 -Purge

  # Check mode (verify environment only, no installs/changes)
  .\setup.ps1 -CheckOnly

Notes:
- Requires Windows 10/11 with winget installed
- Run in PowerShell (not CMD)
- If venv already exists, it will be reused unless -FreshInstall is given
- The script auto-detects requirements.txt and requirements-dev.txt in the same folder as setup.ps1
#>

param(
    [switch]$UpdateOnly,
    [switch]$FreshInstall,
    [switch]$CheckOnly,
    [switch]$Purge
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$requirements = Join-Path $scriptDir "requirements.txt"
$requirementsDev = Join-Path $scriptDir "requirements-dev.txt"
$wingetYaml = Join-Path $scriptDir "winget.yaml"

# --- Step 0: Purge mode ---
if ($Purge) {
    if (Test-Path ".venv") {
        Write-Host "🗑 Removing existing virtual environment..."
        Remove-Item ".venv" -Recurse -Force
        Write-Host "✅ .venv purged."
    } else {
        Write-Host "ℹ️ No .venv found to purge."
    }
    exit 0
}

# --- Step 1: Check mode ---
if ($CheckOnly) {
    Write-Host "🔍 Running environment check only (no installs)..."

    # Check winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "✅ winget is installed."
    } else {
        Write-Host "❌ winget not found. Please install App Installer from Microsoft Store."
    }

    # Check Python
    $pythonOk = $false
    try {
        $pyVersionStr = python --version 2>&1
        Write-Host "✅ Python found: $pyVersionStr"

        # Extract version numbers
        if ($pyVersionStr -match "Python (\d+)\.(\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]

            if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
                Write-Host "⚠️ Warning: Python 3.11+ is required."
            } else {
                Write-Host "✅ Python version is sufficient."
                $pythonOk = $true
            }
        }
    } catch {
        Write-Host "❌ Python not found in PATH."
    }

    # Check files
    if (Test-Path $requirements) { Write-Host "✅ requirements.txt found." } else { Write-Host "❌ requirements.txt missing." }
    if (Test-Path $requirementsDev) { Write-Host "✅ requirements-dev.txt found." } else { Write-Host "❌ requirements-dev.txt missing." }
    if (Test-Path $wingetYaml) { Write-Host "✅ winget.yaml found." } else { Write-Host "❌ winget.yaml missing." }

    # Check venv
    if (Test-Path ".venv") {
        Write-Host "✅ Virtual environment exists."

        $pip = ".\.venv\Scripts\pip.exe"
        if (Test-Path $pip) {
            Write-Host "📦 Installed packages in venv:"

            if ($pythonOk) {
                & $pip list

                # Check against requirements.txt
                if (Test-Path $requirements) {
                    Write-Host "`n🔎 Checking requirements.txt consistency..."
                    & $pip install -r $requirements --dry-run
                }
                if (Test-Path $requirementsDev) {
                    Write-Host "`n🔎 Checking requirements-dev.txt consistency..."
                    & $pip install -r $requirementsDev --dry-run
                }
            } else {
                Write-Host "⚠️ Skipping pip checks due to Python version < 3.11"
            }
        } else {
            Write-Host "⚠️ pip not found in .venv"
        }
    } else {
        Write-Host "ℹ️ Virtual environment not found."
    }

    exit 0
}

# --- Ensure winget is installed ---
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️ Winget is not installed. Installing App Installer from Microsoft Store..."
    Start-Process "ms-windows-store://pdp/?productid=9NBLGGH4NNS1"
    exit 1
}

# --- Step 2: System dependencies ---
if (-not $UpdateOnly) {
    Write-Host "📦 Installing/updating system dependencies via winget.yaml..."
    winget configure -f "$wingetYaml"
} else {
    Write-Host "⏭ Skipping system dependency bootstrap (UpdateOnly mode)"
}

# --- Step 3: Python virtual environment ---
# Check Python version before creating venv
try {
    $pyVersionStr = python --version 2>&1
    $major = 0; $minor = 0
    if ($pyVersionStr -match "Python (\d+)\.(\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
    }
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Host "❌ Python 3.11+ is required to create virtual environment. Aborting setup."
        exit 1
    }
} catch {
    Write-Host "❌ Python not found in PATH. Aborting setup."
    exit 1
}

if ($FreshInstall -and (Test-Path ".venv")) {
    Write-Host "🗑 Removing existing virtual environment..."
    Remove-Item ".venv" -Recurse -Force
}

if (-not (Test-Path ".venv")) {
    Write-Host "🐍 Creating new virtual environment..."
    python -m venv .venv
} else {
    Write-Host "♻️ Reusing existing virtual environment..."
}

# Activate venv
Write-Host "🔑 Activating virtual environment..."
& ".\.venv\Scripts\Activate.ps1"

# --- Step 4: Upgrade pip/setuptools/wheel ---
Write-Host "⬆️ Upgrading pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel

# --- Step 5: Install Python dependencies ---
if (Test-Path $requirements) {
    Write-Host "📥 Installing runtime dependencies from requirements.txt..."
    pip install -r $requirements
}

if (Test-Path $requirementsDev) {
    Write-Host "📥 Installing dev dependencies from requirements-dev.txt..."
    pip install -r $requirementsDev
}

Write-Host "✅ Setup complete!"
