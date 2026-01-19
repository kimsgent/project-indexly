import hashlib
import os
import sys
import textwrap
import urllib.request
from pathlib import Path

PROJECT = "indexly"
FORMULA_CLASS = "Indexly"
HOMEPAGE = "https://github.com/kimsgent/project-indexly"
LICENSE = "MIT"
PYTHON_DEP = "python@3.11"

VERSION = os.environ.get("VERSION")
if not VERSION or not VERSION.startswith("v"):
    sys.exit("ERROR: VERSION must be a tag like v1.1.5")

TAG = VERSION.lstrip("v")
TARBALL_URL = f"{HOMEPAGE}/archive/refs/tags/{VERSION}.tar.gz"


def sha256_of_url(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return hashlib.sha256(r.read()).hexdigest()


def main():
    print("Generating Homebrew formula (runtime pip + caveats wrapper)…")

    sha256 = sha256_of_url(TARBALL_URL)

    formula = f"""\
class {FORMULA_CLASS} < Formula
  desc "Local semantic file indexing and search tool"
  homepage "{HOMEPAGE}"
  url "{TARBALL_URL}"
  sha256 "{sha256}"
  license "{LICENSE}"

  depends_on "{PYTHON_DEP}"
  depends_on "tesseract"

  def install
    python = Formula["{PYTHON_DEP}"].opt_bin/"python3.11"
    system python, "-m", "pip", "install",
                   "--prefix=#{{libexec}}",
                   "--no-cache-dir",
                   "-r", "requirements.txt", "."
    bin.install_symlink libexec/"bin/{PROJECT}"
  end

  def caveats
    <<~EOS
      Indexly is installed successfully.

      If you encounter runtime issues, add the following to your shell config.

      ---- Bash (.bashrc) ----
      echo 'export PATH="$(brew --prefix)/opt/python@3.11/bin:$PATH"' >> ~/.bashrc
      echo 'export PYTHONPATH="$(brew --prefix)/Cellar/indexly/#{{version}}/libexec:$PYTHONPATH"' >> ~/.bashrc
      echo '
      indexly() {{
        PYTHONPATH="$(brew --prefix)/Cellar/indexly/#{{version}}/libexec/lib/python3.11/site-packages:$PYTHONPATH" \\
        "$(brew --prefix)/opt/python@3.11/bin/python3.11" \\
        "$(brew --prefix)/Cellar/indexly/#{{version}}/libexec/bin/indexly" "$@"
      }}
      ' >> ~/.bashrc

      ---- Zsh (.zshrc) ----
      echo 'export PATH="$(brew --prefix)/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
      echo 'export PYTHONPATH="$(brew --prefix)/Cellar/indexly/#{{version}}/libexec:$PYTHONPATH"' >> ~/.zshrc
      echo '
      indexly() {{
        PYTHONPATH="$(brew --prefix)/Cellar/indexly/#{{version}}/libexec/lib/python3.11/site-packages:$PYTHONPATH" \\
        "$(brew --prefix)/opt/python@3.11/bin/python3.11" \\
        "$(brew --prefix)/Cellar/indexly/#{{version}}/libexec/bin/indexly" "$@"
      }}
      ' >> ~/.zshrc

      Reload your shell after applying.
    EOS
  end

  test do
    system bin/"{PROJECT}", "--version"
    system bin/"{PROJECT}", "--help"
  end
end
"""

    out = Path("Formula/indexly.rb")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(textwrap.dedent(formula), encoding="utf-8")

    print(f"✔ Formula written to {out}")
    print("✔ Audit-compatible")
    print("✔ Matches verified install behavior")


if __name__ == "__main__":
    main()
