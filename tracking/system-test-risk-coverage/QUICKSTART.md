# QUICK START: Indexly Tracking Analysis Automation

## ✅ Setup Complete!
Tasks have been added to your Codex sidebar.

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

### Option B: Via "Do anything" Chat (Full Control)
1. Open **Codex** sidebar
2. Click the **"Do anything"** input box at the bottom
3. Paste a prompt with your specific inputs (see templates below)
4. Let Codex execute it

### Option C: Via PowerShell
```powershell
# Interactive prompt
. tracking/system-test-risk-coverage/trigger-automation.ps1
Run-TrackingAnalysis

# Or direct
Run-TrackingAnalysis -Mode known_bug -FaultDescription "Your description"

# Preferred direct Python form
.\.venv-codex\Scripts\python.exe tracking/system-test-risk-coverage/trigger.py --mode known_bug --fault-description "Your description"
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
- Worksheet files in dated folder
- Dashboard metrics regenerated

## 📂 Output Location
```
tracking/system-test-risk-coverage/local-tests/YYYYMMDD_<focus>/
```

---

## 🔗 Full Documentation
See [CODEX_SETUP.md](CODEX_SETUP.md) for detailed setup, troubleshooting, and options.

