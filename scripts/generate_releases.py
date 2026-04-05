import json
import os
from pathlib import Path
import re

# Paths
BASE_DIR = Path(__file__).parent.parent / "docs"
DATA_FILE = BASE_DIR / "data" / "changelog.json"
RELEASES_DIR = BASE_DIR / "content" / "releases"
ARCHIVE_DIR = RELEASES_DIR / "Archive"
INDEX_FILE = RELEASES_DIR / "_index.en.md"
ARCHIVE_INDEX_FILE = ARCHIVE_DIR / "_index.en.md"
API_FILE = BASE_DIR / "static" / "releases.json"


def _read_keep_old() -> int:
    raw = os.environ.get("RELEASES_KEEP_OLD", "5").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


MAX_OLD_RELEASES = _read_keep_old()

# Ensure releases dir exists
RELEASES_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def is_prerelease(version: str) -> bool:
    """Return True if version string looks like a prerelease (alpha, beta, rc, test)."""
    return bool(re.search(r"(alpha|beta|rc|test|-test)", version, re.IGNORECASE))


def _release_filename(version: str) -> str:
    return f"v{version}.md"


def _release_path(version: str, archived: bool = False) -> Path:
    base = ARCHIVE_DIR if archived else RELEASES_DIR
    return base / _release_filename(version)


def _release_url(version: str, archived: bool = False) -> str:
    if archived:
        return f"/releases/Archive/v{version}/"
    return f"/releases/v{version}/"


def write_release_page(filepath: Path, version: str, date: str, changes: list[str]):
    """Generate content for a single release page if not already existing."""
    if not filepath.exists():
        content = [
            "---",
            f'title: "Release v{version}"',
            "type: docs",
            "toc: true",
            "weight: 15",
            "---\n",
            f"## Release v{version} ({date})\n",
            "### Changes",
        ]
        for change in changes:
            content.append(f"- {change}")
        if is_prerelease(version):
            content.append("\n**⚠️ Pre-release / test version**")
        filepath.write_text("\n".join(content), encoding="utf-8")


def build_summary(changes, max_items=2):
    """Build a short summary string from changes"""
    return " | ".join(changes[:max_items])


def main():
    # Load changelog
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    project = data.get("project", "Project")
    versions = data.get("versions", [])

    for v in versions:
        if not v.get("date"):
            raise ValueError(
                f"❌ Missing date in changelog for version {v.get('version')}. "
                "Please update docs/data/changelog.json with a valid date."
            )

    # Sort by date (newest first)
    versions_sorted = sorted(versions, key=lambda v: v["date"], reverse=True)

    # Pick latest stable release (ignore prereleases for "latest")
    latest_stable = next(
        (v for v in versions_sorted if not is_prerelease(v["version"])), None
    )
    latest = latest_stable or (versions_sorted[0] if versions_sorted else None)

    # Retention policy:
    # - Keep latest in active releases
    # - Keep only N additional old releases active
    # - Move older release pages into docs/content/releases/Archive
    versions_without_latest = [
        v for v in versions_sorted if not latest or v["version"] != latest["version"]
    ]
    recent_old_versions = versions_without_latest[:MAX_OLD_RELEASES]
    archived_versions = versions_without_latest[MAX_OLD_RELEASES:]

    active_versions = {v["version"] for v in recent_old_versions}
    if latest:
        active_versions.add(latest["version"])

    # Ensure release pages exist and are in the correct folder
    for v in versions_sorted:
        version = v["version"]
        active_path = _release_path(version, archived=False)
        archive_path = _release_path(version, archived=True)

        if version in active_versions:
            if archive_path.exists() and not active_path.exists():
                archive_path.rename(active_path)
            write_release_page(active_path, version, v["date"], v["changes"])
            if archive_path.exists() and active_path.exists():
                archive_path.unlink()
        else:
            if active_path.exists() and not archive_path.exists():
                active_path.rename(archive_path)
            write_release_page(archive_path, version, v["date"], v["changes"])

    # Generate master index
    index_content = [
        "---",
        f'title: "Release Notes - {project}"',
        "type: docs",
        "toc: true",
        "weight: 10",
        "---\n",
        f"# Release Notes for {project}\n",
        (
            f"_Retention policy: latest release + {MAX_OLD_RELEASES} previous releases "
            "are shown here. Older releases are moved to Archive._\n"
        ),
    ]

    # Add latest release in full
    if latest:
        index_content.append(
            f"## Latest Release: v{latest['version']} ({latest['date']})\n"
        )
        index_content.append("### Changes")
        for change in latest["changes"]:
            index_content.append(f"- {change}")
        index_content.append("\n---\n")

    # Show only recent old releases in the public list
    index_content.append("## Recent Previous Releases\n")
    recent_list = []
    if not recent_old_versions:
        index_content.append("- No previous releases available.")
    else:
        for v in recent_old_versions:
            url_path = _release_url(v["version"], archived=False)
            index_content.append(
                f"- [Release v{v['version']}]({url_path}) ({v['date']})"
            )
            recent_list.append(
                {
                    "version": v["version"],
                    "date": v["date"],
                    "link": f"/en{url_path}",
                    "summary": build_summary(v["changes"]),
                    "prerelease": is_prerelease(v["version"]),
                }
            )

    if archived_versions:
        index_content.append("\n---\n")
        index_content.append("## Older Releases\n")
        index_content.append(
            f"- {len(archived_versions)} older releases moved to "
            "[Archive](/releases/Archive/)."
        )

    # Build Archive index page (all archived releases)
    archive_index_content = [
        "---",
        f'title: "Release Archive - {project}"',
        "type: docs",
        "toc: true",
        "weight: 25",
        "---\n",
        f"# Release Archive for {project}\n",
        (
            f"These are older releases archived automatically. "
            f"The main release page keeps only the latest + {MAX_OLD_RELEASES} older releases.\n"
        ),
    ]

    if not archived_versions:
        archive_index_content.append("No archived releases yet.")
    else:
        for v in archived_versions:
            url_path = _release_url(v["version"], archived=True)
            archive_index_content.append(
                f"- [Release v{v['version']}]({url_path}) ({v['date']})"
            )

    # Write master index
    INDEX_FILE.write_text("\n".join(index_content), encoding="utf-8")
    ARCHIVE_INDEX_FILE.write_text("\n".join(archive_index_content), encoding="utf-8")

    # Build API (cleaned: only recent old releases + archive metadata)
    api_data = {
        "project": project,
        "latest": {
            "version": latest["version"],
            "date": latest["date"],
            "link": f"/en{_release_url(latest['version'], archived=False)}",
            "summary": build_summary(latest["changes"]),
            "prerelease": is_prerelease(latest["version"]),
        }
        if latest
        else {},
        "recent": recent_list,
        # Backward-compat key retained, now cleaned to the same capped list.
        "archive": recent_list,
        "archived": {
            "count": len(archived_versions),
            "link": "/en/releases/Archive/",
        },
        "retention": {
            "max_old_releases": MAX_OLD_RELEASES,
            "active_releases_count": (1 if latest else 0) + len(recent_list),
        },
    }
    API_FILE.write_text(json.dumps(api_data, indent=2), encoding="utf-8")
    print(f"Generated releases index at {INDEX_FILE}")
    print(f"Generated release archive index at {ARCHIVE_INDEX_FILE}")
    print(
        f"Retention applied: latest + {MAX_OLD_RELEASES} old releases active, "
        f"{len(archived_versions)} archived."
    )
    print(f"Generated releases.json API at {API_FILE}")


if __name__ == "__main__":
    main()
