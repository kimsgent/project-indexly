"""Pure planning and filesystem moves owned by rename-watch."""
from __future__ import annotations
import json, os, re, tempfile, threading, unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple
from indexly.config import BASE_DIR
from .config import RenameWatchJob

def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-") or "file"

def render_name(source: Path, pattern: str, date_format: str, counter_format: str, counter: int) -> str:
    date = datetime.fromtimestamp(source.stat().st_mtime).strftime(date_format)
    values = {"date": date, "title": _slug(source.stem), "counter": format(counter, counter_format), "prefix": ""}
    name = pattern
    for key, value in values.items(): name = name.replace("{" + key + "}", value)
    return re.sub(r"-+", "-", name).strip("- ") + source.suffix

class CounterState:
    def __init__(self, job_id: str, state_root: Path = None):
        self.path = (state_root or Path(BASE_DIR) / "rename-watch") / (job_id + ".json")
        self.lock = threading.Lock()
    def _load(self) -> Dict[str, int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(k): int(v) for k, v in data.items() if isinstance(v, int) and v >= 0}
        except (OSError, ValueError, TypeError): return {}
    def _save(self, data: Dict[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle: json.dump(data, handle, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    def next(self, date_key: str) -> Tuple[Dict[str, int], int]:
        data = self._load(); return data, data.get(date_key, 0)

class PlanMoveLog:
    def __init__(self, job: RenameWatchJob, state_root: Path = None):
        self.job, self.state = job, CounterState(job.job_id, state_root)
    def plan_and_move(self, source: Path) -> Path:
        source = source.resolve()
        with self.state.lock:
            date_key = datetime.fromtimestamp(source.stat().st_mtime).strftime(self.job.date_format)
            data, counter = self.state.next(date_key)
            self.job.destination_path.mkdir(parents=True, exist_ok=True)
            while True:
                target = self.job.destination_path / render_name(source, self.job.pattern, self.job.date_format, self.job.counter_format, counter)
                if not target.exists(): break
                counter += 1
            source.replace(target)
            data[date_key] = counter + 1
            self.state._save(data)
            return target
