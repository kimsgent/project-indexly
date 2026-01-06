from pathlib import Path
from importlib.resources import files

# Path to the packaged .txt template
TEMPLATE_PATH = files("indexly.ignore_defaults") / "indexly_default.txt"

def get_default_template() -> str:
    """Return the contents of the default ignore template."""
    return TEMPLATE_PATH.read_text(encoding="utf-8")
