import json
import os
from pathlib import Path

version = os.environ["VERSION"]
notes_file = Path(os.environ["NOTES_FILE"])
data_file = Path("docs/data/changelog.json")
release_file = Path(f"docs/content/releases/{version}.md")

if release_file.exists():
    # Strip Hugo front matter (between --- lines)
    inside = False
    lines = []
    for line in release_file.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    notes_file.write_text("\n".join(lines), encoding="utf-8")
else:
    data = json.loads(data_file.read_text(encoding="utf-8"))
    for v in data["versions"]:
        if "v" + v["version"] == version:
            content = [f"## Release {version} ({v['date']})", "### Changes"]
            content += [f"- {c}" for c in v["changes"]]
            notes_file.write_text("\n".join(content), encoding="utf-8")
            break
    else:
        notes_file.write_text(f"No release notes found for {version}", encoding="utf-8")
