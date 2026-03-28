class Indexly < Formula
  include Language::Python::Virtualenv

  desc "Local semantic file indexing and search tool"
  homepage "https://github.com/kimsgent/project-indexly"
  url "https://github.com/kimsgent/project-indexly/archive/refs/tags/v1.2.4.tar.gz"
  sha256 "75e4178b5bcdf85b9442776cb218d20b7affde0031362cfcaab93e01712d3e1e"
  license "MIT"

  depends_on "python@3.11"
  depends_on "tesseract"

  def install
    python = Formula["python@3.11"].opt_bin/"python3.11"
    system python, "-m", "pip", "install",
                   "--prefix=#{libexec}",
                   "--no-cache-dir",
                   "-r", "requirements.txt", "."
    bin.install_symlink libexec/"bin/indexly"
  end

  test do
    system bin/"indexly", "--version"
    system bin/"indexly", "--help"
  end
end
