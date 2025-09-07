import json
from pathlib import Path

# Paths
BASE_DIR = Path("/home/kims/project-indexly/docs")
DATA_FILE = BASE_DIR / "data" / "changelog.json"
RELEASES_DIR = BASE_DIR / "content" / "releases"
INDEX_FILE = RELEASES_DIR / "_index.en.md"
API_FILE = BASE_DIR / "static" / "releases.json"  # Serve as static API

# Ensure releases dir exists
RELEASES_DIR.mkdir(parents=True, exist_ok=True)

def generate_release_page(version, date, changes):
    """Generate content for a single release page if not already existing"""
    filename = f"v{version}.md"
    filepath = RELEASES_DIR / filename
    if not filepath.exists():
        content = [
            "---",
            f'title: "Release v{version}"',
            "type: docs",
            "toc: true",
            "weight: 15",
            "---\n",
            f"## Release v{version} ({date})\n",
            "### Changes"
        ]
        for change in changes:
            content.append(f"- {change}")
        filepath.write_text("\n".join(content), encoding="utf-8")
    # Return Hugo URL path
    return f"/releases/v{version}/"

def build_summary(changes, max_items=2):
    """Build a short summary string from changes"""
    return " | ".join(changes[:max_items])

def main():
    # Load changelog
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    project = data.get("project", "Project")
    versions = data.get("versions", [])

    # Sort versions by date (newest first)
    versions_sorted = sorted(versions, key=lambda v: v["date"], reverse=True)

    # Generate master index
    index_content = [
        "---",
        f'title: "Release Notes - {project}"',
        "type: docs",
        "toc: true",
        "weight: 10",
        "---\n",
        f"# Release Notes for {project}\n"
    ]

    # Add newest release in full
    latest = versions_sorted[0]
    index_content.append(f"## Latest Release: v{latest['version']} ({latest['date']})\n")
    index_content.append("### Changes")
    for change in latest["changes"]:
        index_content.append(f"- {change}")
    index_content.append("\n---\n")

    # Generate per-version pages + archive section
    index_content.append("## Archive\n")
    archive_list = []
    for v in versions_sorted[1:]:
        url_path = generate_release_page(v["version"], v["date"], v["changes"])
        index_content.append(f"- [Release v{v['version']}]({url_path}) ({v['date']})")
        archive_list.append({
            "version": v["version"],
            "date": v["date"],
            "link": f"/en{url_path}",
            "summary": build_summary(v["changes"])
        })

    # Write master index
    INDEX_FILE.write_text("\n".join(index_content), encoding="utf-8")

    # Build API structure
    api_data = {
        "project": project,
        "latest": latest,
        "archive": archive_list
    }

    # Write static JSON API
    API_FILE.write_text(json.dumps(api_data, indent=2), encoding="utf-8")
    print(f"Generated releases.json API at {API_FILE}")

if __name__ == "__main__":
    main()

