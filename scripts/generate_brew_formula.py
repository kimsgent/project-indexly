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
    "openblas",      # ← ADDED: Automated OpenBLAS
    "pkgconf",       # ← ADDED: pkg-config for OpenBLAS
]

# Vendored Python deps (runtime) - wheels preferred for heavy deps
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

def pypi_wheel(pkg: str, python_tag: str = "cp311") -> tuple[str, str]:
    """Match ACTUAL PyPI wheel tags for Ubuntu 24.04"""
    with urllib.request.urlopen(PYPI_JSON.format(pkg)) as r:
        data = json.load(r)

    # 1. manylinux_2_17_x86_64, manylinux2014_x86_64 (Ubuntu 24.04 perfect)
    for f in data["urls"]:
        if (f["packagetype"] == "wheel" and 
            python_tag in f["filename"] and 
            any(tag in f["filename"] for tag in ["manylinux_2_17_x86_64", "manylinux2014_x86_64", "manylinux1_x86_64"])):
            print(f"✔ Using manylinux wheel: {f['filename']}")
            return f["url"], f["digests"]["sha256"]
    
    # 2. musllinux (Alpine, but works)
    for f in data["urls"]:
        if (f["packagetype"] == "wheel" and python_tag in f["filename"] and "musllinux" in f["filename"]):
            print(f"✔ Using musllinux wheel: {f['filename']}")
            return f["url"], f["digests"]["sha256"]
    
    print(f"⚠️  {pkg}: no compatible wheel, using sdist")
    return pypi_sdist(pkg)

def pypi_sdist(pkg: str) -> tuple[str, str]:
    with urllib.request.urlopen(PYPI_JSON.format(pkg)) as r:
        data = json.load(r)

    for f in data["urls"]:
        if f["packagetype"] == "sdist":
            return f["url"], f["digests"]["sha256"]
    
    raise RuntimeError(f"No sdist found for {pkg}")

def get_package_url(pkg: str) -> tuple[str, str]:
    """Wheel preference for heavy deps, sdist fallback"""
    wheel_priority = {"numpy", "scipy", "pandas", "matplotlib"}
    if pkg.lower() in wheel_priority:
        return pypi_wheel(pkg)
    return pypi_sdist(pkg)

# -------------------------
# Formula generation
# -------------------------

def main():
    print("Generating Homebrew formula…")

    sha256 = sha256_of_url(TARBALL_URL)

    resource_blocks = []
    for pkg in PYTHON_RESOURCES:
        url, digest = get_package_url(pkg)
        resource_name = pkg.replace("_", "-")
        resource_blocks.append(
            f"""
    resource "{resource_name}" do
        url "{url}"
        sha256 "{digest}"
    end
    """
        )

    formula = f"""class {FORMULA_CLASS} < Formula
  include Language::Python::Virtualenv

  desc "Local semantic file indexing and search tool"
  homepage "{HOMEPAGE}"
  url "{TARBALL_URL}"
  sha256 "{sha256}"
  license "{LICENSE}"

"""

    for dep in HOMEBREW_DEPS:
        formula += f'  depends_on "{dep}"\n'

    formula += "".join(resource_blocks)

    formula += """
  def install
    # OpenBLAS setup FIRST (fixes SciPy/numpy Linuxbrew builds)
    openblas = Formula["openblas"]
    ENV.prepend_path "PKG_CONFIG_PATH", "#{openblas.opt_lib}/pkgconfig"
    ENV.prepend "LDFLAGS", "-L#{openblas.opt_lib}/lib"
    ENV.prepend "CPPFLAGS", "-I#{openblas.opt_lib}/include"
    ENV["BLAS"] = "openblas"
    ENV["LAPACK"] = "openblas"

    # Verify OpenBLAS detection
    system "pkg-config", "--exists", "openblas" || (raise "OpenBLAS pkg-config failed!")

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
    print("✔ Wheel preference + OpenBLAS automation complete")
    print("✔ Ready for production Linuxbrew/macOS installs")

if __name__ == "__main__":
    main()
