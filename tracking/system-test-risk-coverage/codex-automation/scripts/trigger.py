#!/usr/bin/env python3
"""Indexly tracking analysis trigger.

Validates fault-analysis inputs, initializes local tracking artifacts, and
regenerates dashboard metrics.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TRACKING_KEYS = ("mode", "fault_description", "analysis_focus")
SCRIPT_DIR = Path(__file__).resolve().parent
AUTOMATION_ROOT = SCRIPT_DIR.parent
TRACKING_ROOT = AUTOMATION_ROOT.parent
REPO_ROOT = TRACKING_ROOT.parent.parent


def parse_input_payload(payload_str):
    """Parse a key=value payload into a dict.

    Supports both newline-delimited payloads and compact one-line payloads, for
    example:

    mode=known_bug fault_description=Crash when indexing large CSV files
    """
    params = {}
    if not payload_str or not payload_str.strip():
        return params

    key_pattern = "|".join(re.escape(key) for key in TRACKING_KEYS)
    matches = list(re.finditer(rf"(?<!\S)({key_pattern})=", payload_str))
    for index, match in enumerate(matches):
        key = match.group(1)
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(payload_str)
        params[key] = payload_str[value_start:value_end].strip()
    return params


def parse_args(argv):
    """Parse modern CLI options while keeping the legacy payload argument."""
    parser = argparse.ArgumentParser(
        description="Initialize an Indexly tracking analysis run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  trigger.py --mode known_bug --fault-description \"Crash on CSV import\"\n"
            "  trigger.py --mode general_analysis --analysis-focus \"CSV null handling\"\n"
            "  trigger.py \"mode=known_bug fault_description=Crash on CSV import\""
        ),
    )
    parser.add_argument("payload", nargs="*", help="Legacy key=value payload.")
    parser.add_argument("--mode", choices=("known_bug", "general_analysis"))
    parser.add_argument("--fault-description", dest="fault_description")
    parser.add_argument("--analysis-focus", dest="analysis_focus")
    parser.add_argument(
        "--venv-path",
        default=None,
        help="Virtual environment used for dashboard regeneration.",
    )
    return parser.parse_args(argv)


def validate_inputs(params):
    """Validate required inputs based on mode."""
    mode = params.get('mode', '').strip()

    if not mode:
        print("ERROR: mode is required (mode=known_bug or mode=general_analysis)")
        return False

    if mode == 'known_bug':
        fault_description = params.get('fault_description', '').strip()
        if not fault_description:
            print("ERROR: fault_description is required for known_bug mode")
            print("  Use: --fault-description <clear symptom, expected vs actual, scope>")
            return False
    elif mode == 'general_analysis':
        analysis_focus = params.get('analysis_focus', '').strip()
        if not analysis_focus:
            print("ERROR: analysis_focus is required for general_analysis mode")
            print("  Use: --analysis-focus <module/workflow/design-principle focus>")
            return False
    else:
        print(f"ERROR: Invalid mode '{mode}'. Must be 'known_bug' or 'general_analysis'")
        return False

    return True


def safe_slug(value, max_length=48):
    """Return a short filesystem-safe slug for run folder names."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return (slug or "analysis")[:max_length]


def get_today_run_folder(base_path, focus_name):
    """Get or create today's dated run folder."""
    today = datetime.now().strftime('%Y%m%d')
    focus_safe = safe_slug(focus_name)
    dated_folder = base_path / f"{today}_{focus_safe}"
    dated_folder.mkdir(parents=True, exist_ok=True)
    return dated_folder


def initialize_run_artifacts(run_folder, params):
    """Initialize run artifacts from templates."""
    templates_path = TRACKING_ROOT / 'templates'

    worksheets = [
        'system-test-case-summary-worksheet-template.md',
        'system-test-case-summary-worksheet-template.json'
    ]

    for template in worksheets:
        template_path = templates_path / template
        if template_path.exists():
            out_name = template.replace('-template', '')
            out_path = run_folder / out_name
            if not out_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(content)


def write_analysis_prompt(run_folder, params):
    """Write a Codex-ready analysis prompt from the provided inputs."""
    mode = params["mode"]
    if mode == "known_bug":
        prompt = (
            "# Codex Analysis Prompt\n\n"
            "Analyze this known Indexly defect using the tracking worksheet in this folder.\n\n"
            f"Fault description: {params['fault_description']}\n\n"
            "Focus on likely fault boundaries, impacted workflows, regression risk, and "
            "the smallest useful validation set. Update the worksheet and record any "
            "risks or open questions before proposing code changes.\n"
        )
    else:
        prompt = (
            "# Codex Analysis Prompt\n\n"
            "Analyze this Indexly area using the tracking worksheet in this folder.\n\n"
            f"Analysis focus: {params['analysis_focus']}\n\n"
            "Focus on observable behavior, missing system tests, risk coverage gaps, "
            "and the smallest useful validation set. Update the worksheet and record "
            "any risks or open questions before proposing code changes.\n"
        )

    prompt_path = run_folder / "codex_analysis_prompt.md"
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    return prompt_path


def regenerate_dashboard(venv_path):
    """Regenerate dashboard metrics."""
    script_path = TRACKING_ROOT / 'scripts' / 'regenerate_dashboard_metrics.py'
    if not script_path.exists():
        print(f"WARNING: Dashboard script not found at {script_path}")
        return True

    python_exe = venv_path / 'Scripts' / 'python.exe'
    if not python_exe.exists():
        print(f"ERROR: Python executable not found at {python_exe}")
        return False

    result = subprocess.run(
        [str(python_exe), str(script_path)],
        cwd=str(TRACKING_ROOT),
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("ERROR: Dashboard regeneration failed")
        print(result.stderr)
        return False

    print("Dashboard metrics regenerated successfully")
    return True


def main():
    """Main trigger routine."""
    args = parse_args(sys.argv[1:])
    payload = " ".join(args.payload)
    params = parse_input_payload(payload)

    for key in TRACKING_KEYS:
        value = getattr(args, key, None)
        if value:
            params[key] = value.strip()

    if not validate_inputs(params):
        sys.exit(1)

    mode = params.get('mode').strip()

    if mode == 'known_bug':
        focus_name = f"known_bug_{params.get('fault_description', 'unknown')[:20]}"
    else:
        focus_name = f"analysis_{params.get('analysis_focus', 'general')}"

    base_path = TRACKING_ROOT / 'local-tests'
    run_folder = get_today_run_folder(base_path, focus_name)

    print(f"Run folder: {run_folder}")

    initialize_run_artifacts(run_folder, params)
    print("Run artifacts initialized")

    prompt_file = write_analysis_prompt(run_folder, params)
    print(f"Codex analysis prompt: {prompt_file}")

    default_venv_path = REPO_ROOT / '.venv-codex'
    venv_path = Path(args.venv_path) if args.venv_path else default_venv_path
    if not regenerate_dashboard(venv_path):
        print("WARNING: Proceeding despite dashboard regeneration issues")

    summary = {
        'mode': mode,
        'focus': focus_name,
        'run_folder': str(run_folder),
        'analysis_prompt': str(prompt_file),
        'timestamp': datetime.now().isoformat(),
        'status': 'success'
    }

    if mode == 'known_bug':
        summary['fault_description'] = params.get('fault_description')
    else:
        summary['analysis_focus'] = params.get('analysis_focus')

    summary_file = run_folder / 'run_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print("\n" + "="*60)
    print("AUTOMATION SUMMARY")
    print("="*60)
    print(f"Mode:           {mode}")
    print(f"Focus:          {focus_name}")
    print(f"Run Folder:     {run_folder}")
    print(f"Summary File:   {summary_file}")
    print(f"Prompt File:    {prompt_file}")
    print("="*60)
    print("\nNext validation actions:")
    print("  1. Review codex_analysis_prompt.md in the run folder")
    print("  2. Use that prompt in Codex for analysis")
    print("  3. Update the worksheet artifacts with findings")

    sys.exit(0)


if __name__ == '__main__':
    main()
