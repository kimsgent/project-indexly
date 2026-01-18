import hashlib
import os
import subprocess
import sys
from pathlib import Path
import textwrap
import json
import urllib.request

PROJECT = "indexly"
FORMULA_CLASS = "Indexly"
HOMEPAGE = "https://github.com/kimsgent/project-indexly"
LICENSE = "MIT"
PYTHON_DEP = "python@3.11"

VERSION = os.environ.get("VERSION")
if not VERSION or not VERSION.startswith("v"):
    sys.exit("ERROR: VERSION must be a tag like v1.1.2")

TAG = VERSION.lstrip("v")
TARBALL_URL = f"{HOMEPAGE}/archive/refs/tags/v{TAG}.tar.gz"

# -------------------------
# Dependency policy
# -------------------------

# Heavy native stack → Homebrew-managed
HOMEBREW_DEPS = [
    "python@3.11",
    "tesseract",
]

# Vendored Python deps (runtime)
PYTHON_RESOURCES = [
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
    "nltk",
    "pymupdf",
    "pytesseract",
    "Pillow",
    "python-docx",
    "openpyxl",
    "rapidfuzz",
    "fpdf2",
    "reportlab",
    "beautifulsoup4",
    "extract_msg",
    "eml-parser",
    "PyPDF2",
    "watchdog",
    "colorama",
    "python-pptx",
    "ebooklib",
    "odfpy",
    "rich",
    "PyYAML",
    "xmltodict",
    "requests",
    "plotext",
    "plotly",
]

PYPI_JSON = "https://pypi.org/pypi/{}/json"


# -------------------------
# Helpers
# -------------------------


def sha256_of_url(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return hashlib.sha256(r.read()).hexdigest()


def pypi_sdist(pkg: str) -> tuple[str, str]:
    with urllib.request.urlopen(PYPI_JSON.format(pkg)) as r:
        data = json.load(r)

    for f in data["urls"]:
        if f["packagetype"] == "sdist":
            return f["url"], f["digests"]["sha256"]

    raise RuntimeError(f"No sdist found for {pkg}")


# -------------------------
# Formula generation
# -------------------------


def main():
    print("Generating Homebrew formula…")

    sha256 = sha256_of_url(TARBALL_URL)

    resource_blocks = []
    for pkg in PYTHON_RESOURCES:
        url, digest = pypi_sdist(pkg)
        resource_name = pkg.replace("_", "-")  # <-- FIX applied
        resource_blocks.append(
            f"""
    resource "{resource_name}" do
        url "{url}"
        sha256 "{digest}"
    end
    """
        )

    formula = f"""
class {FORMULA_CLASS} < Formula
  include Language::Python::Virtualenv

  desc "Local semantic file indexing and search tool"
  homepage "{HOMEPAGE}"
  url "{TARBALL_URL}"
  sha256 "{sha256}"
  license "{LICENSE}"

  depends_on "{PYTHON_DEP}"
"""

    for dep in HOMEBREW_DEPS:
        formula += f'  depends_on "{dep}"\n'

    formula += "".join(resource_blocks)

    formula += """
  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"indexly", "--version"
    system bin/"indexly", "--help"
  end
end
"""

    out = Path("Formula/indexly.rb")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(textwrap.dedent(formula).strip() + "\n", encoding="utf-8")

    print(f"✔ Formula written to {out}")
    print("✔ Dependency vendoring complete")


if __name__ == "__main__":
    main()
