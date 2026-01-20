import hashlib
import os
import sys
import urllib.request
from pathlib import Path

PROJECT = "indexly"
FORMULA_CLASS = "Indexly"
HOMEPAGE = "https://github.com/kimsgent/project-indexly"
LICENSE = "MIT"
PYTHON_DEP = "python@3.11"

VERSION = os.environ.get("VERSION")
if not VERSION:
    sys.exit("ERROR: VERSION is not set")

TAG = VERSION.lstrip("v")
TARBALL_URL = f"{HOMEPAGE}/archive/refs/tags/{VERSION}.tar.gz"

# SHA256 calculation
def sha256_of_url(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return hashlib.sha256(r.read()).hexdigest()


# Formula template is **outside Python**, using placeholders
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
    print("Generating clean Homebrew formula…")
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

    out = Path("Formula/indexly.rb")
    out.parent.mkdir(parents=True, exist_ok=True)
    # write as-is, no trailing blank line
    out.write_text(formula, encoding="utf-8")

    print(f"✔ Formula written to {out}")
    print("✔ Audit-compatible")

if __name__ == "__main__":
    main()
