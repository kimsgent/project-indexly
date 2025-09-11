#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import subprocess

def release_exists(version: str) -> bool:
    """Check if release already exists on GitHub."""
    result = subprocess.run(
        ["gh", "release", "view", version],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0

def main():
    if len(sys.argv) < 2:
        print("Usage: prepare_release_notes.py <version>")
        sys.exit(1)

    version = sys.argv[1]  # e.g., v1.0.0
    release_file = Path(f"docs/content/releases/{version}.md")
    notes_file = Path("RELEASE_NOTES.md")

    # Skip if release already exists
    if release_exists(version):
        print(f"⚠️ Release {version} already exists on GitHub, skipping NOTES generation")
        return

    if release_file.exists():
        print(f"✅ Using {release_file} for notes")
        lines = release_file.read_text(encoding="utf-8").splitlines()
        # Strip Hugo front matter (--- blocks)
        in_frontmatter = False
        filtered = []
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if not in_frontmatter:
                filtered.append(line)
        notes_file.write_text("\n".join(filtered), encoding="utf-8")
    else:
        print("⚠️ Release file not found, fallback to changelog.json")
        data_file = Path("docs/data/changelog.json")
        data = json.loads(data_file.read_text(encoding="utf-8"))

        for v in data.get("versions", []):
            if "v" + v["version"] == version:
                content = [f"## Release {version} ({v['date']})", "### Changes"]
                content += [f"- {c}" for c in v["changes"]]
                notes_file.write_text("\n".join(content), encoding="utf-8")
                break
        else:
            notes_file.write_text(
                f"No release notes found for {version}", encoding="utf-8"
            )

if __name__ == "__main__":
    main()
