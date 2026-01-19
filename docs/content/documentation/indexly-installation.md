---
title: "Install Indexly – Setup, Configuration & First Run"
description: "Learn how to install Indexly on Windows, macOS, and Linux using pip or Homebrew. Step-by-step setup, verification, and troubleshooting for your first successful run."
keywords:
  - install indexly
  - indexly installation
  - indexly setup
  - python file indexing tool
  - local search cli
  - indexly homebrew
  - indexly pip
weight: 10
type: docs
toc: true
aliases:
  - /installation/
  - /getting-started/installation/
---

---

>Indexly requires **Python ≥ 3.11**. Installation differs slightly depending on your platform and whether you are a **user** or a **developer**.


## **1. Installation via pip (Recommended for Windows & cross-platform users)**

### **Windows (User Install)**

```other
python -m pip install --upgrade pip
pip install indexly
```

Verify:

```other
indexly --version
```

If the command is not found, ensure Python’s Scripts directory is on `PATH`.

----

### **macOS / Linux (User Install)**

```bash
python3.11 -m pip install --upgrade pip
python3.11 -m pip install indexly
```

Verify:

```bash
indexly --version
```

> 💡 If you see import or runtime errors, prefer the Homebrew method below on macOS/Linux.

----

## **2. Installation via Homebrew (Recommended for macOS & Linux)**

Indexly provides an official Homebrew tap.

### **Install**

```bash
brew tap kimsgent/indexly
brew install indexly
```

Verify:

```bash
indexly --version
```

----

### **Shell setup (IMPORTANT)**

On some systems, Homebrew Python and Indexly’s runtime paths must be explicitly configured.

#### **Bash**

```bash
echo 'export PATH="$(brew --prefix)/opt/python@3.11/bin:$PATH"' >> ~/.bashrc
echo 'export PYTHONPATH="$(brew --prefix)/Cellar/indexly/$(indexly --version)/libexec:$PYTHONPATH"' >> ~/.bashrc

echo '
indexly() {
  PYTHONPATH="$(brew --prefix)/Cellar/indexly/$(indexly --version)/libexec/lib/python3.11/site-packages:$PYTHONPATH" \
  "$(brew --prefix)/opt/python@3.11/bin/python3.11" \
  "$(brew --prefix)/Cellar/indexly/$(indexly --version)/libexec/bin/indexly" "$@"
}
' >> ~/.bashrc
```

#### **Zsh**

```bash
echo 'export PATH="$(brew --prefix)/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
echo 'export PYTHONPATH="$(brew --prefix)/Cellar/indexly/$(indexly --version)/libexec:$PYTHONPATH"' >> ~/.zshrc

echo '
indexly() {
  PYTHONPATH="$(brew --prefix)/Cellar/indexly/$(indexly --version)/libexec/lib/python3.11/site-packages:$PYTHONPATH" \
  "$(brew --prefix)/opt/python@3.11/bin/python3.11" \
  "$(brew --prefix)/Cellar/indexly/$(indexly --version)/libexec/bin/indexly" "$@"
}
' >> ~/.zshrc
```

Reload your shell:

```bash
source ~/.bashrc   # or ~/.zshrc
```

----

## **3. [Developer](developer.md) Installation (All Platforms)**

Recommended for contributors and advanced users.

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
pip install -e .
```

Verify:

```bash
indexly --help
```

----

## **4. Troubleshooting**

- Ensure **Python 3.11** is used at runtime
- Prefer **Homebrew** on macOS/Linux for stable CLI behavior
- If `indexly` runs but fails at import time, re-check `PYTHONPATH`

----

Indexly is now ready to use. 🚀

**See also [Customizing Windows Terminal](windows-terminal-setup.md)**

