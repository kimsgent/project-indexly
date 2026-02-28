class Indexly < Formula
  include Language::Python::Virtualenv

  desc "Local semantic file indexing and search tool"
  homepage "https://github.com/kimsgent/project-indexly"
  url "https://github.com/kimsgent/project-indexly/archive/refs/tags/v1.2.3.tar.gz"
  sha256 "e8bf853735d28a3a0707b4a68f2781ea248854caabc38397def7881dd3f0281c"
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
