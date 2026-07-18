#!/usr/bin/env python3
"""Validate release metadata and documentation highlights before publication."""

import argparse
import json
from pathlib import Path
import re

import yaml
from release_versions import is_prerelease

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_FILE = ROOT / "docs" / "data" / "changelog.json"
RELEASES_DIR = ROOT / "docs" / "content" / "releases"
DOCUMENTATION_INDEX = ROOT / "docs" / "content" / "documentation" / "_index.en.md"
MAX_DOCUMENTATION_RELEASE_HIGHLIGHTS = 4


def front_matter(filepath):
    lines = filepath.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Release metadata is missing YAML front matter: {filepath}")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"Release metadata has unclosed YAML front matter: {filepath}") from exc
    try:
        metadata = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Release metadata is not valid YAML: {filepath}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"Release metadata must be a mapping: {filepath}")
    return metadata


def id_set(mapping, field, filepath):
    value = mapping.get(field)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"Release metadata requires non-empty {field}: {filepath}")
    return set(value)


def release_page(version):
    for directory in (RELEASES_DIR, RELEASES_DIR / "Archive"):
        candidate = directory / f"v{version}.md"
        if candidate.exists():
            return candidate
    raise ValueError(f"Release v{version} needs a reviewed release page with risk metadata before publishing.")


def validate_metadata(version, changelog):
    entry = next((item for item in changelog if item.get("version") == version), None)
    if entry is None:
        raise ValueError(f"Release v{version} is missing from {CHANGELOG_FILE}")
    filepath = release_page(version)
    metadata = front_matter(filepath)
    required_values = {
        "release_id": f"IDXREL-{version}",
        "version": version,
        "released_at": entry.get("date"),
    }
    for field, expected in required_values.items():
        if str(metadata.get(field)) != str(expected):
            raise ValueError(f"Release metadata {field} does not match v{version}: {filepath}")
    if metadata.get("mapping_confidence") not in {"high", "medium", "low"}:
        raise ValueError(f"Release metadata needs mapping_confidence: {filepath}")
    if not isinstance(metadata.get("source_commit_range"), str) or ".." not in metadata["source_commit_range"]:
        raise ValueError(f"Release metadata needs source_commit_range from the previous release: {filepath}")

    release_areas = id_set(metadata, "area_ids", filepath)
    release_risks = id_set(metadata, "risk_ids", filepath)
    changes = metadata.get("change_ids")
    if not isinstance(changes, list) or not changes:
        raise ValueError(f"Release metadata requires non-empty change_ids: {filepath}")
    change_areas, change_risks = set(), set()
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError(f"Each change entry must be a mapping: {filepath}")
        if not isinstance(change.get("id"), str) or not change["id"].startswith(f"IDXREL-{version}-CHG-"):
            raise ValueError(f"Change IDs must use the release ID prefix: {filepath}")
        if not isinstance(change.get("type"), str) or not change["type"].strip():
            raise ValueError(f"Each change needs a type: {filepath}")
        if not isinstance(change.get("summary"), str) or not change["summary"].strip():
            raise ValueError(f"Each change needs a summary: {filepath}")
        change_areas.update(id_set(change, "area_ids", filepath))
        change_risks.update(id_set(change, "risk_ids", filepath))
    if release_areas != change_areas:
        raise ValueError(f"Release area_ids must match mapped change areas: {filepath}")
    if release_risks != change_risks:
        raise ValueError(f"Release risk_ids must match mapped change risks: {filepath}")


def validate_documentation_highlights(changelog):
    expected = [item["version"] for item in changelog if not is_prerelease(item["version"])][:MAX_DOCUMENTATION_RELEASE_HIGHLIGHTS]
    content = DOCUMENTATION_INDEX.read_text(encoding="utf-8")
    section = re.search(r"^## What Is New\s*$([\s\S]*?)(?=^## |\Z)", content, re.MULTILINE)
    if section is None:
        raise ValueError(f"Missing 'What Is New' section: {DOCUMENTATION_INDEX}")
    actual = []
    for item in re.findall(r"^\s*<li>(.*?)</li>\s*$", section.group(1), re.MULTILINE):
        match = re.search(r"`v([0-9][^`]*)`", item)
        if match is None:
            raise ValueError(f"Each documentation highlight needs one release version: {DOCUMENTATION_INDEX}")
        actual.append(match.group(1))
    if actual != expected:
        raise ValueError(f"Documentation highlights must list exactly the latest {MAX_DOCUMENTATION_RELEASE_HIGHLIGHTS} stable releases in order: expected {expected}, found {actual}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-version", required=True, help="Release tag, for example v2.1.4")
    args = parser.parse_args(argv)
    changelog = json.loads(CHANGELOG_FILE.read_text(encoding="utf-8")).get("versions", [])
    changelog = sorted(changelog, key=lambda item: item["date"], reverse=True)
    validate_documentation_highlights(changelog)
    validate_metadata(args.release_version.lstrip("v"), changelog)
    print(f"Validated release metadata and documentation highlights for {args.release_version}")


if __name__ == "__main__":
    main()
