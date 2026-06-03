# QUICK START: Indexly Tracking Analysis Automation

## ✅ Setup Complete!
Tasks have been added to your Codex sidebar.

This setup is for the Windows development environment only. It assumes PowerShell, `.venv-codex\Scripts\python.exe`, and VS Code task paths using Windows separators.

---

## 🎯 How to Trigger

### Option A: Via Codex Sidebar Tasks (Easiest)
1. Open **Codex** sidebar in VS Code
2. Look for **Tasks** section
3. Click one of these:
   - **🔍 Tracking: Known Bug Analysis**
   - **🔍 Tracking: General Analysis**
4. Enter the prompted fault description or analysis focus
5. Review the generated `codex_analysis_prompt.md` in the run folder

The task creates a draft tracking scaffold only. The generated worksheet files are not analysis results until Codex or a human completes them according to `tracking/system-test-risk-coverage/README.md`.

### Option B: Via "Do anything" Chat (Full Control)
1. Open **Codex** sidebar
2. Click the **"Do anything"** input box at the bottom
3. Paste a prompt with your specific inputs (see templates below)
4. Let Codex execute it

### Option C: Via PowerShell
```powershell
# Interactive prompt
. tracking/system-test-risk-coverage/codex-automation/scripts/trigger-automation.ps1
Run-TrackingAnalysis

# Or direct
Run-TrackingAnalysis -Mode known_bug -FaultDescription "Your description"

# Preferred direct Python form
.\.venv-codex\Scripts\python.exe tracking/system-test-risk-coverage/codex-automation/scripts/trigger.py --mode known_bug --fault-description "Your description"
```

---

## 📋 Input Templates for "Do anything" Chat

### Known Bug Mode
```
mode=known_bug
fault_description=App crashes when parsing large CSV with mixed types; expected graceful error, got fatal exception
```

### General Analysis Mode
```
mode=general_analysis
analysis_focus=CSV parsing module null value handling
```

---

## ✅ Success Indicators
- Output shows `Run folder: ...`
- `run_summary.json` created
- `codex_analysis_prompt.md` created for Codex follow-up analysis
- Draft worksheet files in dated folder
- Dashboard metrics regenerated

## 🔁 Analysis Handoff
After the task runs:

1. Open or reference `codex_analysis_prompt.md`.
2. Ask Codex to follow `tracking/system-test-risk-coverage/README.md`.
3. Treat `system-test-case-summary-worksheet.md` and `.json` as draft scaffolding.
4. Complete the worksheet only after code inspection, risk assessment, remediation or validation planning, test evidence, and residual risks are recorded.

## 📂 Output Location
```
tracking/system-test-risk-coverage/local-tests/YYYYMMDD_<focus>/
```

---

## 🔗 Full Documentation
See [CODEX_SETUP.md](CODEX_SETUP.md) for detailed setup, troubleshooting, and options.

