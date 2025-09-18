#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import subprocess
import shutil
import re

def release_exists(version: str) -> bool:
    """Check if release already exists on GitHub. Dry-run returns False if gh is missing."""
    if shutil.which("gh") is None:
        return False
    result = subprocess.run(
        ["gh", "release", "view", version],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0

def is_special_version(version: str) -> bool:
    """Return True if version is dry-run or pre-release."""
    return bool(re.search(r"-(test|alpha|beta|rc)", version, re.IGNORECASE))

def main():
    if len(sys.argv) < 2:
        print("Usage: prepare_release_notes.py <version>")
        sys.exit(1)

    version = sys.argv[1]  # e.g., v1.0.0 or v0.0.0-test
    release_file = Path(f"docs/content/releases/{version}.md")
    notes_file = Path("RELEASE_NOTES.md")

    # Skip if release already exists
    if release_exists(version):
        print(f"⚠️ Release {version} already exists on GitHub, skipping NOTES generation")
        return

    if release_file.exists():
        print(f"✅ Using {release_file} for notes")
        lines = release_file.read_text(encoding="utf-8").splitlines()
        # Strip Hugo front matter
        in_frontmatter = False
        filtered = []
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if not in_frontmatter:
                filtered.append(line)
        notes_file.write_text("\n".join(filtered), encoding="utf-8")
        return

    print("⚠️ Release file not found, fallback to changelog.json")
    data_file = Path("docs/data/changelog.json")
    data = json.loads(data_file.read_text(encoding="utf-8"))

    for v in data.get("versions", []):
        if "v" + v["version"] == version:
            content = [f"## Release {version} ({v['date']})", "### Changes"]
            content += [f"- {c}" for c in v["changes"]]
            notes_file.write_text("\n".join(content), encoding="utf-8")
            return

    # Fallback for dry-run or pre-release
    if is_special_version(version):
        dummy_content = [
            f"## Release {version} (dry-run)",
            "### Changes",
            "- This is a dry-run or pre-release",
            "- Workflow validated successfully",
            "- No real changes included"
        ]
        notes_file.write_text("\n".join(dummy_content), encoding="utf-8")
        print(f"ℹ️ Dummy release notes created for {version}")
    else:
        notes_file.write_text(
            f"No release notes found for {version}", encoding="utf-8"
        )
        print(f"⚠️ No release notes found for {version}")

if __name__ == "__main__":
    main()
