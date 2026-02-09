#!/usr/bin/env python3
import hashlib
import os
import sys
import urllib.request
from pathlib import Path
import argparse

PROJECT = "indexly"
FORMULA_CLASS = "Indexly"
HOMEPAGE = "https://github.com/kimsgent/project-indexly"
LICENSE = "MIT"
PYTHON_DEP = "python@3.11"

# CLI arguments
parser = argparse.ArgumentParser(description="Generate Homebrew formula")
parser.add_argument(
    "--source", type=str, default=None,
    help="Path to local tar.gz source (for dry-run or test tags)"
)
parser.add_argument(
    "--dry-run", action="store_true",
    help="Dry-run mode, do not require GitHub tag"
)
parser.add_argument(
    "--out", type=str, default="Formula/indexly.rb",
    help="Output path for formula"
)
args = parser.parse_args()

# VERSION from environment
VERSION = os.environ.get("VERSION")
if not VERSION:
    sys.exit("ERROR: VERSION is not set")

IS_RELEASE = VERSION.startswith("v") and "-test" not in VERSION
TAG = VERSION.lstrip("v")

# Determine tarball URL or local file
if args.dry_run or "-test" in VERSION:
    if args.source:
        dist_file = Path(args.source).expanduser()
        if not dist_file.exists():
            sys.exit(f"ERROR: Source file {dist_file} not found for dry-run/test")
        TARBALL_URL = f"file://{dist_file.resolve()}"
        def sha256_of_url(url: str) -> str:
            # Local file SHA
            with dist_file.open("rb") as f:
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        print(f"WARNING: Non-release VERSION detected ({VERSION}); using local tarball {dist_file}")
    else:
        sys.exit("ERROR: --source must be provided for dry-run/test mode")
else:
    TARBALL_URL = f"{HOMEPAGE}/archive/refs/tags/{VERSION}.tar.gz"
    def sha256_of_url(url: str) -> str:
        with urllib.request.urlopen(url) as r:
            return hashlib.sha256(r.read()).hexdigest()

# Formula template
FORMULA_TEMPLATE = """\
class {formula_class} < Formula
  desc "Local semantic file indexing and search tool"
  homepage "{homepage}"
  url "{url}"
  sha256 "{sha256}"
  license "{license}"

  depends_on "{python_dep}"
  depends_on "tesseract"

  def install
    python = Formula["{python_dep}"].opt_bin/"python3.11"
    system python, "-m", "pip", "install",
                   "--prefix=#{{libexec}}",
                   "--no-cache-dir",
                   "-r", "requirements.txt", "."
    bin.install_symlink libexec/"bin/{project}"
  end
  test do
    system bin/"{project}", "--version"
    system bin/"{project}", "--help"
  end
end"""

def main():
    print("Generating Homebrew formula…")
    sha256 = sha256_of_url(TARBALL_URL)

    formula = FORMULA_TEMPLATE.format(
        formula_class=FORMULA_CLASS,
        homepage=HOMEPAGE,
        url=TARBALL_URL,
        sha256=sha256,
        license=LICENSE,
        python_dep=PYTHON_DEP,
        project=PROJECT,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(formula, encoding="utf-8")

    print(f"✔ Formula written to {out}")
    print("✔ Audit-compatible")

if __name__ == "__main__":
    main()
