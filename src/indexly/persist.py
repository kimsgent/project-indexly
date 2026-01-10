import json
from pathlib import Path
from typing import Any, Dict

def save_json(summary: Dict[str, Any], db_path: str, dest_dir: str | None = None) -> Path:
    p = Path(dest_dir or Path.home() / ".indexly" / "analysis")
    p.mkdir(parents=True, exist_ok=True)
    fname = Path(db_path).stem + ".analysis.json"
    out = p / fname
    with out.open("w", encoding="utf-8") as f:
        json.dump(summary, f, default=str, indent=2)
    return out
