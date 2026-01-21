# scripts/preflight.sh
#!/usr/bin/env bash
set -euo pipefail

python -m build
twine check dist/*

python scripts/generate_brew_formula.py \
  --source dist/*.tar.gz \
  --dry-run \
  --out Formula/indexly.rb

brew audit --strict indexly || true
