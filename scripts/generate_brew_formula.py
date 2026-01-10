# scripts/generate_brew_formula.py
import hashlib
import os
import subprocess
from pathlib import Path
import textwrap

PROJECT = "indexly"
HOMEPAGE = "https://github.com/kimsgent/project-indexly"
LICENSE = "MIT"
PYTHON_DEP = "python@3.11"

VERSION = os.environ.get("VERSION")
if not VERSION:
    raise SystemExit("VERSION env var not set")

TAG = VERSION.lstrip("v")
TARBALL_URL = f"{HOMEPAGE}/archive/refs/tags/v{TAG}.tar.gz"

FORMULA_TEMPLATE = """\
class Indexly < Formula
  include Language::Python::Virtualenv

  desc "Local semantic file indexing and search tool"
  homepage "{homepage}"
  url "{url}"
  sha256 "{sha256}"
  license "{license}"

  depends_on "{python_dep}"

  def install
    virtualenv_install_with_resources
  end

  test do
    system "#{{bin}}/indexly", "--help"
  end
end
"""

def sha256_of_url(url: str) -> str:
    proc = subprocess.run(
        ["curl", "-L", url],
        stdout=subprocess.PIPE,
        check=True,
    )
    return hashlib.sha256(proc.stdout).hexdigest()

def main():
    sha256 = sha256_of_url(TARBALL_URL)

    formula = FORMULA_TEMPLATE.format(
        homepage=HOMEPAGE,
        url=TARBALL_URL,
        sha256=sha256,
        license=LICENSE,
        python_dep=PYTHON_DEP,
    )

    out = Path("Formula/indexly.rb")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(textwrap.dedent(formula), encoding="utf-8")

    print(f"Generated Homebrew formula at {out}")

if __name__ == "__main__":
    main()
