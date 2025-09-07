# 🔧 Development Workflow for Hatch-Built Python Packages

This guide explains how to continue development after downloading a package built with `hatch build`.
You have two options: work **without installing** or work **with installation** but still access the raw source.

---

## 📂 1. Work Without Installing the Package

This is the simplest way if you just want to hack on the raw source.

```bash
# 1. Clone or download the package source
git clone https://github.com/your/repo.git
cd repo

# 2. Move into the source folder (where pyproject.toml exists)
cd repo

# 3. Set PYTHONPATH so Python knows where to find your package
# (on Windows PowerShell)
$env:PYTHONPATH = "$(Get-Location)/src"
# (on Linux/Mac)
export PYTHONPATH=$(pwd)/src

# 4. Run your package directly without installing
python -m your_package_name <args>
```

✅ You now:

* Have **full access** to raw files
* Can edit `.py` files directly
* Can test changes immediately with `python -m`

No rebuild or install is required until you’re satisfied.

---

## 📦 2. Work With Installed Package (Editable / Dev Mode)

If you want to install but still keep working on the raw files:

```bash
# 1. Clone or download the package source
git clone https://github.com/kimsgent/repo.git
cd repo

# 2. Install in editable (dev) mode
pip install -e .

# 3. Confirm installation
pip show your-package-name
```

✅ With `pip install -e .`:

* Python links the installed package back to your source folder (`src/`).
* Any edits you make in the raw source are **immediately reflected** without reinstalling.
* You can still run `python -m your_package_name` or call the CLI.

---

## 🔁 3. Rebuild & Reinstall Once Ready

When your changes are stable and tested:

```bash
# 1. Build with hatch
hatch build

# 2. Install the fresh build
pip install dist/your_package_name-<version>-py3-none-any.whl --force-reinstall
```

---

## 📝 Summary

* **No install path** → set `PYTHONPATH=src` and run with `python -m`.
* **Editable install path** → `pip install -e .` links your raw files to Python.
* **Final release** → `hatch build` + `pip install dist/*.whl`.
