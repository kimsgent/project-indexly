# Codex Automation Trigger Helper for PowerShell
# Usage: . tracking/system-test-risk-coverage/codex-automation/scripts/trigger-automation.ps1
# Then: Run-TrackingAnalysis

Set-StrictMode -Version 2.0

$script:TrackingAutomationScriptRoot = if ($PSScriptRoot) {
    $PSScriptRoot
} elseif ($PSCommandPath) {
    Split-Path -Parent $PSCommandPath
} else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Test-WindowsEnvironment {
    return [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
}

function Get-TrackingAutomationPaths {
    $repoRoot = Resolve-Path -LiteralPath (Join-Path $script:TrackingAutomationScriptRoot "..\..\..\..")
    $triggerScript = Join-Path $script:TrackingAutomationScriptRoot "trigger.py"
    $defaultPythonExe = Join-Path $repoRoot.Path ".venv-codex\Scripts\python.exe"
    $localTestsDir = Join-Path $repoRoot.Path "tracking\system-test-risk-coverage\local-tests"

    return [pscustomobject]@{
        RepoRoot = $repoRoot.Path
        TriggerScript = $triggerScript
        DefaultPythonExe = $defaultPythonExe
        LocalTestsDir = $localTestsDir
    }
}

function Run-TrackingAnalysis {
    param(
        [ValidateSet("", "known_bug", "general_analysis")]
        [string]$Mode = "",
        [string]$FaultDescription = "",
        [string]$AnalysisFocus = "",
        [string]$PythonExe = ""
    )

    if (-not (Test-WindowsEnvironment)) {
        Write-Host "Error: trigger-automation.ps1 is supported only on Windows." -ForegroundColor Red
        return
    }

    $paths = Get-TrackingAutomationPaths
    if (-not $PythonExe) {
        $PythonExe = $paths.DefaultPythonExe
    }

    Write-Host "`n" -ForegroundColor Cyan
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  Indexly Tracking Analysis Trigger                             ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

    # If mode not provided, prompt user
    if (-not $Mode) {
        Write-Host "`nSelect analysis mode:" -ForegroundColor Yellow
        Write-Host "  1) known_bug      - Analyze a known bug/defect" -ForegroundColor Gray
        Write-Host "  2) general_analysis - General module/workflow analysis" -ForegroundColor Gray
        $choice = Read-Host "`nEnter choice (1 or 2)"

        if ($choice -eq "1") {
            $Mode = "known_bug"
        } elseif ($choice -eq "2") {
            $Mode = "general_analysis"
        } else {
            Write-Host "Invalid choice. Exiting." -ForegroundColor Red
            return
        }
    }

    # Get mode-specific input
    if ($Mode -eq "known_bug") {
        if (-not $FaultDescription) {
            Write-Host "`nProvide fault description:" -ForegroundColor Yellow
            Write-Host "  (Include: symptom, expected vs actual, scope, repro context)" -ForegroundColor Gray
            $FaultDescription = Read-Host "Fault description"
        }

        if (-not $FaultDescription) {
            Write-Host "Error: Fault description required. Exiting." -ForegroundColor Red
            return
        }

        $payload = "mode=known_bug`nfault_description=$FaultDescription"
    } elseif ($Mode -eq "general_analysis") {
        if (-not $AnalysisFocus) {
            Write-Host "`nProvide analysis focus area:" -ForegroundColor Yellow
            Write-Host "  (Example: CSV parsing module, database connection pool, error handling)" -ForegroundColor Gray
            $AnalysisFocus = Read-Host "Analysis focus"
        }

        if (-not $AnalysisFocus) {
            Write-Host "Error: Analysis focus required. Exiting." -ForegroundColor Red
            return
        }

        $payload = "mode=general_analysis`nanalysis_focus=$AnalysisFocus"
    } else {
        Write-Host "Error: Invalid mode '$Mode'. Expected known_bug or general_analysis." -ForegroundColor Red
        return
    }

    Write-Host "`n" -ForegroundColor Cyan
    Write-Host "Configuration:" -ForegroundColor Yellow
    Write-Host "  Mode:    $Mode"
    Write-Host "  Payload: $(($payload -replace "`n", " | "))" -ForegroundColor Gray
    Write-Host ""

    $confirm = Read-Host "Continue? (y/n)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        return
    }

    # Delegate artifact creation to trigger.py. This wrapper only collects Windows inputs.
    Write-Host "`n🚀 Running automation..." -ForegroundColor Cyan
    Write-Host ""

    try {
        if (-not (Test-Path -LiteralPath $PythonExe)) {
            Write-Host "Error: Python executable not found at $PythonExe" -ForegroundColor Red
            Write-Host "Ensure .venv-codex is available and dependencies are installed." -ForegroundColor Yellow
            return
        }

        if (-not (Test-Path -LiteralPath $paths.TriggerScript)) {
            Write-Host "Error: trigger.py not found at $($paths.TriggerScript)" -ForegroundColor Red
            return
        }

        if ($Mode -eq "known_bug") {
            & $PythonExe $paths.TriggerScript --mode known_bug --fault-description $FaultDescription
        } else {
            & $PythonExe $paths.TriggerScript --mode general_analysis --analysis-focus $AnalysisFocus
        }

        if ($LASTEXITCODE -ne 0) {
            Write-Host "`nAutomation failed with exit code $LASTEXITCODE." -ForegroundColor Red
            return
        }

        Write-Host "`n✅ Automation completed!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Output files created in:" -ForegroundColor Cyan
        Write-Host "  $($paths.LocalTestsDir)\YYYYMMDD_<focus>\" -ForegroundColor Gray
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
    }
}

function Show-TrackingStatus {
    if (-not (Test-WindowsEnvironment)) {
        Write-Host "Error: trigger-automation.ps1 is supported only on Windows." -ForegroundColor Red
        return
    }

    Write-Host "`nRecent tracking runs:" -ForegroundColor Cyan
    $paths = Get-TrackingAutomationPaths
    $testDir = $paths.LocalTestsDir
    if (Test-Path $testDir) {
        Get-ChildItem -Path $testDir -Directory | Sort-Object -Property LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object {
            Write-Host "  📁 $($_.Name)" -ForegroundColor Gray
            if (Test-Path (Join-Path $_.FullName "run_summary.json")) {
                $summary = Get-Content (Join-Path $_.FullName "run_summary.json") | ConvertFrom-Json
                Write-Host "     Mode: $($summary.mode), Focus: $($summary.focus)" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "  No runs yet." -ForegroundColor Gray
    }
}

Write-Host "`n✓ Loaded: Run-TrackingAnalysis" -ForegroundColor Green
Write-Host "✓ Available: Show-TrackingStatus" -ForegroundColor Green
Write-Host "`nUsage:" -ForegroundColor Yellow
Write-Host "  Run-TrackingAnalysis                    # Interactive mode" -ForegroundColor Gray
Write-Host "  Run-TrackingAnalysis -Mode known_bug -FaultDescription 'description'" -ForegroundColor Gray
Write-Host "  Run-TrackingAnalysis -Mode general_analysis -AnalysisFocus 'focus area'" -ForegroundColor Gray
Write-Host "  Run-TrackingAnalysis -PythonExe 'D:\project-indexly\.venv-codex\Scripts\python.exe'" -ForegroundColor Gray
Write-Host "  Show-TrackingStatus                     # List recent runs" -ForegroundColor Gray
Write-Host ""
