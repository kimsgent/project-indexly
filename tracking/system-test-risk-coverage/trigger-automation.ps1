# Codex Automation Trigger Helper for PowerShell
# Usage: . ./trigger-automation.ps1
# Then: Run-TrackingAnalysis

function Run-TrackingAnalysis {
    param(
        [string]$Mode = "",
        [string]$FaultDescription = "",
        [string]$AnalysisFocus = ""
    )
    
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
    } else {
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
    
    # Run the trigger script
    Write-Host "`n🚀 Running automation..." -ForegroundColor Cyan
    Write-Host ""
    
    try {
        $pythonExe = ".\.venv-codex\Scripts\python.exe"
        if (-not (Test-Path $pythonExe)) {
            Write-Host "Error: Python executable not found at $pythonExe" -ForegroundColor Red
            Write-Host "Ensure .venv-codex is available and dependencies are installed." -ForegroundColor Yellow
            return
        }

        if ($Mode -eq "known_bug") {
            & $pythonExe "tracking/system-test-risk-coverage/trigger.py" --mode known_bug --fault-description $FaultDescription
        } else {
            & $pythonExe "tracking/system-test-risk-coverage/trigger.py" --mode general_analysis --analysis-focus $AnalysisFocus
        }
        
        Write-Host "`n✅ Automation completed!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Output files created in:" -ForegroundColor Cyan
        Write-Host "  tracking/system-test-risk-coverage/local-tests/YYYYMMDD_<focus>/" -ForegroundColor Gray
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
    }
}

function Show-TrackingStatus {
    Write-Host "`nRecent tracking runs:" -ForegroundColor Cyan
    $testDir = "tracking/system-test-risk-coverage/local-tests"
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
Write-Host "  Show-TrackingStatus                     # List recent runs" -ForegroundColor Gray
Write-Host ""
