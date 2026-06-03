# Codex Automation Setup: Indexly Tracking Analysis Trigger

## Overview
This guide sets up a manual-trigger automation in Codex (VS Code sidebar) to run tracking analysis on Windows.

This automation is Windows-only. It assumes PowerShell, VS Code tasks, and the repository-local `.venv-codex\Scripts\python.exe`.

---

## ✅ Setup Status: COMPLETE

The automation is ready to use! You can trigger it two ways:

### Method 1: Via Tasks Sidebar (Recommended)
Tasks have been added to `.vscode/tasks.json`. They now appear in your Codex **Tasks** list and prompt for the mode-specific input before running.

### Method 2: Via "Do anything" Chat (Interactive)
Use the chat input at the bottom of the Codex panel for full control over inputs.

---

## How to Use

### Recommended Wiring

Use VS Code tasks for deterministic setup work: collect the fault/focus input, create a dated tracking folder, initialize worksheets, regenerate metrics, and write `codex_analysis_prompt.md`.

Use Codex chat for the reasoning step: paste or reference the generated `codex_analysis_prompt.md` and ask Codex to update the worksheet, inspect code, and propose fixes. A VS Code task can prompt for input and run commands, but it does not automatically start an agentic Codex analysis session with those parameters.

### Method 1️⃣: Click Tasks in Sidebar

1. Open **Codex** sidebar
2. Look for new tasks:
   - **🔍 Tracking: Known Bug Analysis**
   - **🔍 Tracking: General Analysis**
3. Click a task to run it

The known-bug task prompts for a fault description. The general-analysis task prompts for an analysis focus.

### Method 2️⃣: "Do anything" Chat (Full Control)

1. Open **Codex** sidebar
2. Click the **"Do anything"** input box at the bottom
3. Paste one of these prompts:

#### Known Bug Analysis
```
Run the Indexly tracking analysis for a known bug:
- Mode: known_bug
- Fault Description: App crashes on startup when indexing large CSV files with mixed data types. Expected: graceful error handling, Actual: fatal exception

Use: .\.venv-codex\Scripts\python.exe tracking/system-test-risk-coverage/codex-automation/scripts/trigger.py --mode known_bug --fault-description "App crashes on startup when indexing large CSV files with mixed data types"
```

#### General Analysis
```
Run the Indexly tracking analysis for general module review:
- Mode: general_analysis
- Analysis Focus: CSV parsing module error handling paths

Use: .\.venv-codex\Scripts\python.exe tracking/system-test-risk-coverage/codex-automation/scripts/trigger.py --mode general_analysis --analysis-focus "CSV parsing module error handling"
```

---

## Input Templates for "Do anything" Chat

### Template A: Known Bug Mode
Replace the bracketed placeholders:

```
mode=known_bug
fault_description=[Symptom + expected vs actual + scope + repro steps]
```

**Example:**
```
mode=known_bug
fault_description=TypeError when parsing CSV with null values; expected graceful skip, got unhandled exception in row 42
```

### Template B: General Analysis Mode
Replace the bracketed placeholders:

```
mode=general_analysis
analysis_focus=[Module name / workflow / design area]
```

**Example:**
```
mode=general_analysis
analysis_focus=CSV module null handling and validation edge cases
```

---

## What Happens During Execution

The automation will:

1. ✅ **Validate inputs** (mode, required params)
2. ✅ **Create/append to dated run folder** in `tracking/system-test-risk-coverage/local-tests/`
3. ✅ **Initialize artifacts** from templates:
   - `system-test-case-summary-worksheet.md`
   - `system-test-case-summary-worksheet.json`
4. ✅ **Create `codex_analysis_prompt.md`** from the supplied fault/focus
5. ✅ **Regenerate dashboard metrics** via `regenerate_dashboard_metrics.py`
6. ✅ **Return summary** with file locations and next steps

### Output Files Created

```
tracking/system-test-risk-coverage/local-tests/
└── YYYYMMDD_<focus_name>/
    ├── run_summary.json                        (execution summary)
    ├── codex_analysis_prompt.md                (Codex follow-up prompt)
    ├── system-test-case-summary-worksheet.md   (analysis worksheet)
    └── system-test-case-summary-worksheet.json (analysis data)
```

---

## Troubleshooting

### Tasks Don't Appear in Sidebar
- Reload VS Code (`Ctrl+Shift+P` → `Developer: Reload Window`)
- Check that `.vscode/tasks.json` was updated

### "Mode is required" Error
- Make sure your input includes `mode=known_bug` or `mode=general_analysis`

### "fault_description is required" Error
- You're using `known_bug` mode but didn't provide fault description
- Format: `fault_description=<clear symptom and scope>`

### "analysis_focus is required" Error
- You're using `general_analysis` mode but didn't provide focus
- Format: `analysis_focus=<module or workflow name>`

### Python Not Found
- Ensure `.venv-codex` exists and dependencies are installed
- In terminal: `& d:\project-indexly\.venv-codex\Scripts\Activate.ps1`

### Dashboard Regeneration Failed
- Check that `regenerate_dashboard_metrics.py` exists
- Run manually: `.\.venv-codex\Scripts\python.exe tracking/system-test-risk-coverage/scripts/regenerate_dashboard_metrics.py`

---

## Portable Use (No Codex/Sidebar)

If you need to run this outside Codex, use the Python script directly in terminal:

```powershell
cd D:\project-indexly
.\.venv-codex\Scripts\python.exe tracking/system-test-risk-coverage/codex-automation/scripts/trigger.py --mode known_bug --fault-description "Test crash on startup"
```

Or use the PowerShell helper:

```powershell
. tracking/system-test-risk-coverage/codex-automation/scripts/trigger-automation.ps1
Run-TrackingAnalysis  # Interactive prompt
```

---

## Files Created

- **`.vscode/tasks.json`** – Updated with two new tracking tasks
- **`tracking/system-test-risk-coverage/codex-automation/scripts/trigger.py`** – Main automation script
- **`tracking/system-test-risk-coverage/codex-automation/scripts/trigger-automation.ps1`** – PowerShell helper (for terminal use)
- **`tracking/system-test-risk-coverage/codex-automation/docs/CODEX_SETUP.md`** – This file
- **`tracking/system-test-risk-coverage/codex-automation/docs/QUICKSTART.md`** – Quick reference


