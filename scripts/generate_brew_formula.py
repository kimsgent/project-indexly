#!/usr/bin/env python3
"""Generate an audit-friendly Homebrew formula for Indexly.

The generated formula is compatible with `virtualenv_install_with_resources` and
vendors only runtime dependencies from Indexly's core dependency set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


FORMULA_CLASS = "Indexly"
PROJECT_SLUG = "indexly"
HOMEPAGE = "https://github.com/kimsgent/project-indexly"
FORMULA_DESC = "Local file indexing and search CLI with FTS5 and regex support"
DEFAULT_LICENSE = "MIT"
DEFAULT_PYTHON_DEP = "python@3.13"
PYPI_RELEASE_JSON = "https://pypi.org/pypi/{package}/{version}/json"
GITHUB_TARBALL_URL = (
    "https://github.com/kimsgent/project-indexly/archive/refs/tags/{tag}.tar.gz"
)
SKIP_RESOURCES = {"pip", "setuptools", "wheel", "pkg-resources"}


@dataclass(frozen=True)
class SourceArtifact:
    url: str
    sha256: str
    install_target: str


@dataclass(frozen=True)
class Resource:
    name: str
    url: str
    sha256: str


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def ruby_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Homebrew formula.")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Local source tar.gz. Required for --dry-run; optional for release mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate formula against local source artifact (file:// URL).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="Formula/indexly.rb",
        help="Output path for the generated formula.",
    )
    parser.add_argument(
        "--pyproject",
        type=str,
        default="pyproject.toml",
        help="Path to pyproject.toml.",
    )
    parser.add_argument(
        "--python-dep",
        type=str,
        default=DEFAULT_PYTHON_DEP,
        help="Homebrew Python dependency (e.g. python@3.13).",
    )
    parser.add_argument(
        "--resolver-python",
        type=str,
        default=sys.executable,
        help="Python executable used to resolve runtime dependencies in a temp venv.",
    )
    return parser.parse_args()


def read_pyproject_metadata(pyproject_path: Path) -> dict[str, str]:
    if not pyproject_path.exists():
        raise SystemExit(f"ERROR: {pyproject_path} not found")

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})

    name = str(project.get("name", PROJECT_SLUG))
    version = project.get("version")
    if not version:
        raise SystemExit("ERROR: pyproject.toml is missing [project].version")

    description = str(
        project.get("description", "Local semantic file indexing and search tool")
    )

    license_value = project.get("license", DEFAULT_LICENSE)
    if isinstance(license_value, dict):
        license_name = str(license_value.get("text", DEFAULT_LICENSE))
    else:
        license_name = str(license_value)

    return {
        "name": name,
        "version": str(version),
        "description": description,
        "license": license_name or DEFAULT_LICENSE,
    }


def get_version_tag(project_version: str) -> str:
    raw = os.environ.get("VERSION")
    if not raw:
        return f"v{project_version}"
    return raw if raw.startswith("v") else f"v{raw}"


def resolve_local_source(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"ERROR: source artifact not found: {path}")
    return path


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_url(url: str) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=90) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url} -> HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{url} -> {exc.reason}") from exc


def pypi_name_candidates(package: str) -> list[str]:
    normalized = normalize_name(package)
    underscore = normalized.replace("-", "_")
    candidates: list[str] = []
    for value in (package, normalized, underscore):
        if value not in candidates:
            candidates.append(value)
    return candidates


def pypi_release_files(package: str, version: str) -> tuple[str, list[dict]]:
    last_error: Exception | None = None

    for candidate in pypi_name_candidates(package):
        encoded_name = urllib.parse.quote(candidate, safe="")
        encoded_version = urllib.parse.quote(version, safe="")
        metadata_url = PYPI_RELEASE_JSON.format(
            package=encoded_name, version=encoded_version
        )
        try:
            payload = fetch_json(metadata_url)
            files = payload.get("urls") or []
            if files:
                official_name = payload.get("info", {}).get("name", candidate)
                return str(official_name), files
        except RuntimeError as exc:
            last_error = exc

    detail = f" ({last_error})" if last_error else ""
    raise RuntimeError(f"Unable to query PyPI release for {package}=={version}{detail}")


def select_release_artifact(
    package: str, version: str, prefer_sdist: bool = True
) -> tuple[str, str, str]:
    official_name, files = pypi_release_files(package, version)

    if prefer_sdist:
        for file_info in files:
            if file_info.get("packagetype") == "sdist":
                return (
                    str(file_info["url"]),
                    str(file_info["digests"]["sha256"]),
                    official_name,
                )

    for file_info in files:
        if (
            file_info.get("packagetype") == "bdist_wheel"
            and "py3-none-any.whl" in str(file_info.get("filename", ""))
        ):
            return (
                str(file_info["url"]),
                str(file_info["digests"]["sha256"]),
                official_name,
            )

    for file_info in files:
        if file_info.get("packagetype") == "bdist_wheel":
            return (
                str(file_info["url"]),
                str(file_info["digests"]["sha256"]),
                official_name,
            )

    raise RuntimeError(f"No downloadable artifact found for {package}=={version}")


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or "no output"
        raise RuntimeError(
            f"Command failed ({' '.join(command)}): {details}"
        ) from exc


def resolve_runtime_packages(
    install_target: str, resolver_python: str, project_name: str
) -> list[tuple[str, str]]:
    skip_names = {normalize_name(project_name)}
    skip_names.update(normalize_name(item) for item in SKIP_RESOURCES)

    with tempfile.TemporaryDirectory(prefix="indexly-brew-resolve-") as temp_dir:
        venv_path = Path(temp_dir) / "venv"
        run_command([resolver_python, "-m", "venv", str(venv_path)])

        venv_python = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

        run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
        run_command(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-compile",
                install_target,
            ]
        )

        pip_list = run_command(
            [str(venv_python), "-m", "pip", "list", "--format", "json"]
        )
        rows = json.loads(pip_list.stdout)

    package_map: dict[str, tuple[str, str]] = {}
    for row in rows:
        name = str(row.get("name", "")).strip()
        version = str(row.get("version", "")).strip()
        normalized = normalize_name(name)
        if not name or not version or normalized in skip_names:
            continue
        package_map[normalized] = (name, version)

    return [package_map[key] for key in sorted(package_map)]


def resolve_formula_source(
    project_name: str,
    version: str,
    version_tag: str,
    source_path: Path | None,
    dry_run: bool,
) -> SourceArtifact:
    if dry_run or "-test" in version_tag:
        if not source_path:
            raise SystemExit("ERROR: --source is required for --dry-run or -test versions")
        return SourceArtifact(
            url=f"file://{source_path}",
            sha256=sha256_of_file(source_path),
            install_target=str(source_path),
        )

    try:
        pypi_url, pypi_sha, _ = select_release_artifact(
            project_name, version, prefer_sdist=True
        )
        install_target = str(source_path) if source_path else pypi_url
        print(f"Using PyPI source for formula URL: {pypi_url}")
        return SourceArtifact(url=pypi_url, sha256=pypi_sha, install_target=install_target)
    except RuntimeError as exc:
        print(f"WARNING: {exc}")
        print("WARNING: Falling back to GitHub release tarball.")

    github_url = GITHUB_TARBALL_URL.format(tag=version_tag)
    install_target = str(source_path) if source_path else github_url
    return SourceArtifact(
        url=github_url,
        sha256=sha256_of_url(github_url),
        install_target=install_target,
    )


def resolve_resource_blocks(packages: list[tuple[str, str]]) -> list[Resource]:
    resources: dict[str, Resource] = {}
    for package_name, version in packages:
        url, digest, official_name = select_release_artifact(package_name, version)
        resource_name = normalize_name(official_name)
        resources[resource_name] = Resource(
            name=resource_name,
            url=url,
            sha256=digest,
        )
    return [resources[key] for key in sorted(resources)]


def render_formula(
    *,
    homepage: str,
    source: SourceArtifact,
    license_name: str,
    python_dep: str,
    resources: list[Resource],
) -> str:
    dependencies = {python_dep}
    if any(resource.name == "pyyaml" for resource in resources):
        dependencies.add("libyaml")

    lines = [
        f"class {FORMULA_CLASS} < Formula",
        "  include Language::Python::Virtualenv",
        "",
        f'  desc "{ruby_escape(FORMULA_DESC)}"',
        f'  homepage "{ruby_escape(homepage)}"',
        f'  url "{source.url}"',
        f'  sha256 "{source.sha256}"',
        f'  license "{ruby_escape(license_name)}"',
        "",
    ]

    for dependency in sorted(dependencies):
        lines.append(f'  depends_on "{dependency}"')

    lines.extend(
        [
        "",
        ]
    )

    for resource in resources:
        lines.extend(
            [
                f'  resource "{resource.name}" do',
                f'    url "{resource.url}"',
                f'    sha256 "{resource.sha256}"',
                "  end",
                "",
            ]
        )

    lines.extend(
        [
            "  def install",
            "    virtualenv_install_with_resources",
            "  end",
            "",
            "  test do",
            '    assert_match version.to_s, shell_output("#{bin}/indexly --version").strip',
            '    assert_match "usage", shell_output("#{bin}/indexly --help").downcase',
            "  end",
            "end",
            "",
        ]
    )
    return "\n".join(lines)


def write_formula(out_path: Path, formula: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = formula.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    out_path.write_text(normalized, encoding="utf-8", newline="\n")


def main() -> None:
    args = parse_args()
    metadata = read_pyproject_metadata(Path(args.pyproject))
    version_tag = get_version_tag(metadata["version"])
    version = version_tag[1:] if version_tag.startswith("v") else version_tag
    source_path = resolve_local_source(args.source)

    print("Generating Homebrew formula with vendored Python resources...")
    source_artifact = resolve_formula_source(
        project_name=metadata["name"],
        version=version,
        version_tag=version_tag,
        source_path=source_path,
        dry_run=args.dry_run,
    )

    print("Resolving runtime dependency graph in an isolated environment...")
    runtime_packages = resolve_runtime_packages(
        install_target=source_artifact.install_target,
        resolver_python=args.resolver_python,
        project_name=metadata["name"],
    )
    print(f"Resolved {len(runtime_packages)} runtime dependencies.")

    print("Resolving pinned resource URLs and checksums from PyPI...")
    resources = resolve_resource_blocks(runtime_packages)
    print(f"Prepared {len(resources)} Homebrew resource blocks.")

    formula = render_formula(
        homepage=HOMEPAGE,
        source=source_artifact,
        license_name=metadata["license"],
        python_dep=args.python_dep,
        resources=resources,
    )

    out_path = Path(args.out)
    write_formula(out_path, formula)
    print(f"✔ Formula written to {out_path}")
    print("✔ Formula uses virtualenv_install_with_resources")


if __name__ == "__main__":
    main()
