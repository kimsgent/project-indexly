"""
📄 log_utils.py

Purpose:
    Handles logging of indexing activities with timestamped filenames.

Key Features:
    - write_index_log(): Logs all indexed file paths with timestamps.

Usage:
    Called during indexing to keep a persistent record of what was indexed.
"""

# log_utils.py
# Multi-log upgrade for indexly log-clean feature
from __future__ import annotations
import csv
import hashlib
import json
import os
import re
import glob
import time
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple
from .config import (
    BASE_DIR,
    LOG_DIR as CONFIG_LOG_DIR,
    MAX_LOG_SIZE,
    BATCH_SIZE,
    FLUSH_INTERVAL,
    COMPRESS_THRESHOLD,
    LOG_RETENTION_DAYS,
    LOG_PARTITION,
)
from .path_utils import normalize_path

# -----------------------------------------
# indexly/log_utils.py – unified async logger
# -----------------------------------------
import zlib
import base64
import asyncio
import threading
from threading import Lock
import logging


# ---------------- CONFIG DEFAULTS ----------------
# Legacy .log files (can be converted manually if needed)
LEGACY_LOG_DIR = Path(CONFIG_LOG_DIR)  # anchored to BASE_DIR/log
LEGACY_LOG_DIR.mkdir(parents=True, exist_ok=True)

# NDJSON log files (used by LogManager)
NDJSON_LOG_DIR = Path(BASE_DIR) / "log"
NDJSON_LOG_DIR.mkdir(parents=True, exist_ok=True)



_log_lock = Lock()


# ---------------- PATH HELPERS ----------------
def _choose_today_ndjson_filename():
    today = date.today().isoformat()
    return NDJSON_LOG_DIR / f"indexly-{today}.ndjson"


# ---------------- UNIFIED LOG ENTRY ----------------

def _unified_log_entry(
    event_type: str,
    raw_path: str,
    *,
    content_changed: bool | None = None,
) -> dict:
    cleaned = normalize_path(raw_path)
    parts = cleaned.split("/")
    filename = parts[-1] if parts else ""
    extension = filename.split(".")[-1].lower() if "." in filename else ""

    year = month = customer = None

    # --- 1) Folder-based extraction
    if len(parts) >= 5:
        maybe_year = parts[-4]
        maybe_month = parts[-3]
        maybe_customer = parts[-2]

        if (
            maybe_year.isdigit()
            and len(maybe_year) == 4
            and maybe_month.isdigit()
        ):
            year = maybe_year
            month = maybe_month
            customer = maybe_customer

    # cleaned filename + cleaned path
    cleaned_filename = filename.replace(" ", "_")
    cleaned_path = (
        "/".join(parts[:-1] + [cleaned_filename])
        if parts
        else cleaned_filename
    )

    # --- 2) Filename-based fallback
    if year is None or month is None:
        import re
        m = re.search(r"(19|20)\d{2}[^\d]?\d{2}?", cleaned_filename)
        if m:
            token = m.group(0)
            digits = "".join(c for c in token if c.isdigit())
            if len(digits) >= 4:
                year = digits[:4]
                if len(digits) >= 6:
                    month = digits[4:6]

    # --- 3) Filesystem timestamp fallback
    p = Path(raw_path)
    if (year is None or month is None) and p.exists():
        ts = datetime.fromtimestamp(p.stat().st_mtime)
        year = year or ts.strftime("%Y")
        month = month or ts.strftime("%m")

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event": event_type,
        "path": cleaned_path,
        "filename": cleaned_filename,
        "extension": extension,
        "customer": customer,
        "year": year,
        "month": month,
    }

    # --- 4) Integrity signal (explicit, optional, non-semantic)
    if content_changed is not None:
        entry["content_changed"] = content_changed

    return entry


# ---------------- LOG MANAGER ----------------
class LogManager:
    """
    Async NDJSON logger with clean shutdown (no pending tasks,
    no event-loop-closed errors).
    """

    def __init__(
        self,
        log_dir: Path = NDJSON_LOG_DIR,
        max_bytes: int = MAX_LOG_SIZE,
        retention_days: int = LOG_RETENTION_DAYS,
        partition: str = LOG_PARTITION,
        async_mode: bool = True,
        compress_threshold: int = COMPRESS_THRESHOLD,
        batch_size: int = BATCH_SIZE,
        flush_interval: float = FLUSH_INTERVAL,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self.partition = partition if partition in ("daily", "hourly") else "daily"
        self.async_mode = async_mode
        self.compress_threshold = compress_threshold
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self._lock = threading.Lock()
        self._active_files = {}
        self._stopped = False

        # async components
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._worker_task = None
        self._thread = None
        self._stop_event = threading.Event()

        if self.async_mode:
            self._queue = asyncio.Queue()
            self._start_background_worker()
            
    def flush(self, timeout: float = 1.0):
        """Ensure all queued log entries are written without stopping the worker."""
        if not self.async_mode or not self._queue or not self._thread:
            return

        start = time.time()
        while not self._queue.empty() and (time.time() - start) < timeout:
            time.sleep(0.05)

    # ---------------- PATH HELPERS ----------------
    def _partition_base(self, now: datetime) -> str:
        return now.strftime("%Y-%m-%d_%H") if self.partition == "hourly" else now.strftime("%Y-%m-%d")

    def _build_subdir(self, entry: dict) -> Path:
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        return self.log_dir / year / month


    def _choose_log_path(self, entry: dict) -> str:
        base = self._partition_base(datetime.now())
        subdir = self._build_subdir(entry)
        return str(subdir / f"{base}_index_events.ndjson")

    def _rotate_if_needed(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            return file_path
        try:
            if os.path.getsize(file_path) < self.max_bytes:
                return file_path
        except OSError:
            return file_path

        base = Path(file_path)
        counter = 1
        while True:
            cand = base.with_name(f"{base.stem}_{counter}{base.suffix}")
            if not cand.exists():
                return str(cand)
            counter += 1

    def _apply_retention(self):
        cutoff = datetime.now().date() - timedelta(days=self.retention_days)

        for f in self.log_dir.rglob("*.ndjson"):
            try:
                # Filename format: YYYY-MM-DD_index_events.ndjson
                ts = f.stem.split("_")[0]  # → "2025-12-11"
                f_date = datetime.strptime(ts, "%Y-%m-%d").date()

                if f_date < cutoff:
                    f.unlink()
            except Exception:
                # ignore files with unexpected names
                continue

    # ---------------- COMPRESSION ----------------
    def _compress_if_needed(self, entry: dict) -> dict:
        e = entry.copy()
        for key in ("content", "snippet"):
            v = e.get(key)
            if isinstance(v, str) and len(v) >= self.compress_threshold:
                comp = zlib.compress(v.encode("utf-8"))
                e[f"{key}_compressed"] = base64.b64encode(comp).decode("ascii")
                e[f"{key}_compression"] = "zlib+base64"
                del e[key]
        return e

    # ---------------- SYNC WRITE ----------------
    def _write_sync(self, entry: dict):
        entry = self._compress_if_needed(entry)
        target = self._choose_log_path(entry)

        with self._lock:
            active = self._active_files.get(target) or target
            Path(active).parent.mkdir(parents=True, exist_ok=True)
            rotated = self._rotate_if_needed(active)
            active = rotated
            self._active_files[target] = active

            with open(active, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

            self._apply_retention()

    # ---------------- ASYNC WORKER ----------------
    def _start_background_worker(self):
        def runner(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=runner, args=(self._loop,), daemon=True)
        self._thread.start()

        self._worker_task = asyncio.run_coroutine_threadsafe(self._async_worker(), self._loop)

    async def _async_worker(self):
        batch = []
        last_flush = asyncio.get_running_loop().time()

        while not self._stop_event.is_set():
            try:
                entry = await asyncio.wait_for(self._queue.get(), timeout=self.flush_interval)
                batch.append(entry)
                self._queue.task_done()
            except asyncio.TimeoutError:
                pass

            now = asyncio.get_running_loop().time()
            if batch and (len(batch) >= self.batch_size or now - last_flush >= self.flush_interval):
                self._flush_batch(batch)
                batch.clear()
                last_flush = now

        # stop → flush remaining
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch):
        for e in batch:
            try:
                self._write_sync(e)
            except:
                pass

    # ---------------- PUBLIC API ----------------
    def log(self, entry: dict):
        if self.async_mode and self._queue:
            fut = asyncio.run_coroutine_threadsafe(self._queue.put(entry), self._loop)
            try:
                fut.result(timeout=1)
            except:
                self._write_sync(entry)
        else:
            self._write_sync(entry)

    async def alog(self, entry: dict):
        if self._queue:
            await self._queue.put(entry)
        else:
            self._write_sync(entry)

    # ---------------- CLEAN SHUTDOWN ----------------
    def stop(self, timeout: float = 2.0):
        if not self.async_mode:
            return

        self._stop_event.set()

        try:
            if self._queue:
                asyncio.run_coroutine_threadsafe(self._queue.join(), self._loop).result(timeout=timeout)
        except:
            pass

        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except:
            pass

        try:
            self._thread.join(timeout=timeout)
        except:
            pass


# ---------------- SINGLETON LOGGER ----------------
_default_logger = LogManager(async_mode=True)


# ---------------- TOP-LEVEL FUNCTIONS ----------------
def log_index_event_dict(entry: dict):
    _default_logger.log(entry)


def log_index_event(event_type: str, path: str):
    entry = _unified_log_entry(event_type, path)
    print(f"[{entry['timestamp']}] [{event_type}] {path}")
    _default_logger.log(entry)


def shutdown_logger(timeout: float = 2.0):
    global _default_logger
    if not _default_logger:
        return

    logger = _default_logger
    _default_logger = None

    try:
        # signal async worker to stop
        logger._stop_event.set()

        # wake the event loop so it notices the stop event
        if logger._loop and logger._loop.is_running():
            logger._loop.call_soon_threadsafe(lambda: None)

        # wait for worker thread to finish
        logger._thread.join(timeout=timeout)
    except Exception as e:
        logging.error(f"Logger shutdown error: {e}")




# -------------------------
# Basic cleaners / utils
# -------------------------
ISO_DATE_LOG_RE = re.compile(r"\d{4}-\d{2}-\d{2}_index\.log$")


def _is_index_log(path: str | Path) -> bool:
    return bool(ISO_DATE_LOG_RE.search(str(path)))


def _clean_path(p: str) -> str:
    p = p.replace("\\", "/")
    p = re.sub(r"(?<!:)//+", "/", p)
    return p


def _clean_filename(fn: str) -> str:
    fn = fn.strip()
    fn = re.sub(r"\s+", " ", fn)  # collapse whitespace
    fn = fn.replace(" ", "-")  # spaces -> dashes
    return fn


def _file_hash(path: str | Path, alg: str = "sha1") -> str:
    h = hashlib.new(alg)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -------------------------
# Log parsing
# -------------------------
TIMESTAMP_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
)  # ISO-like


def _parse_log_lines(path: str | Path) -> Tuple[List[Dict[str, Any]], dict]:
    """
    Return (entries, meta) for a single raw index log file.
    entries: list of metadata dicts (path/filename/ext/customer/year/month)
    meta: per-log metadata: date, count, earliest_ts, latest_ts, hash
    """
    p = Path(path)
    raw_lines: List[str] = []
    with p.open("r", encoding="utf-8", errors="ignore") as fh:
        raw_lines = [ln.rstrip("\n") for ln in fh if ln.strip()]

    earliest_ts = None
    latest_ts = None
    entries: List[Dict[str, Any]] = []

    for line in raw_lines:
        # try to extract timestamp from the start or anywhere in line
        m = TIMESTAMP_RE.search(line)
        if m:
            ts = m.group("ts")
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                dt = None
            if dt:
                if earliest_ts is None or dt < earliest_ts:
                    earliest_ts = dt
                if latest_ts is None or dt > latest_ts:
                    latest_ts = dt

        # get path portion (after last '] ' if present)
        raw_path = line.split("]")[-1].strip() if "] " in line else line.strip()
        raw_path = _clean_path(raw_path)

        # split and extract
        parts = raw_path.split("/")
        filename = parts[-1] if parts else ""
        extension = filename.split(".")[-1].lower() if "." in filename else ""
        year = month = customer = None

        # pattern .../<year>/<month>/<customer>/<filename>
        if len(parts) >= 5:
            maybe_year = parts[-4]
            maybe_month = parts[-3]
            maybe_customer = parts[-2]
            if maybe_year.isdigit() and len(maybe_year) == 4 and maybe_month.isdigit():
                year = maybe_year
                month = maybe_month
                customer = maybe_customer

        cleaned_filename = _clean_filename(filename)
        # rebuild path with cleaned filename
        cleaned_path = (
            "/".join(parts[:-1] + [cleaned_filename]) if parts else cleaned_filename
        )

        entries.append(
            {
                "path": cleaned_path,
                "filename": cleaned_filename,
                "extension": extension,
                "customer": customer,
                "year": year,
                "month": month,
            }
        )

    meta = {
        "log_date": p.stem.split("_")[0] if "_" in p.stem else p.stem,
        "file_count": len(entries),
        "earliest_timestamp": earliest_ts.isoformat() if earliest_ts else None,
        "latest_timestamp": latest_ts.isoformat() if latest_ts else None,
        "log_hash_sha1": _file_hash(p),
        "source_path": str(p),
    }

    return entries, meta


# -------------------------
# Merging / dedup
# -------------------------
def _dedupe_entries(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for e in entries:
        key = e.get("path") or e.get("filename")
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


# -------------------------
# Exporters
# -------------------------
def _export_json(payload: dict, out_file: str | Path):
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def _export_ndjson(entries: Iterable[Dict[str, Any]], out_file: str | Path):
    with open(out_file, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def _export_csv(entries: Iterable[Dict[str, Any]], out_file: str | Path):
    entries = list(entries)
    if not entries:
        # write empty csv with headers
        headers = ["path", "filename", "extension", "customer", "year", "month"]
        with open(out_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=headers)
            writer.writeheader()
        return

    headers = list({k for e in entries for k in e.keys()})
    with open(out_file, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for e in entries:
            writer.writerow({k: e.get(k) for k in headers})


# -------------------------
# Summary generator
# -------------------------
def _generate_summary(per_log_meta: List[dict], global_entries: List[dict]) -> str:
    lines: List[str] = []
    lines.append(f"Generated at: {datetime.now().isoformat()}")
    lines.append(f"Processed logs: {len(per_log_meta)}")
    total_files = sum(m.get("file_count", 0) for m in per_log_meta)
    lines.append(f"Total entries across logs: {total_files}")
    lines.append("")

    # Per-log brief
    for m in per_log_meta:
        lines.append(
            f"- {m.get('log_date')} : {m.get('file_count')} entries (hash: {m.get('log_hash_sha1')})"
        )
        if m.get("earliest_timestamp") or m.get("latest_timestamp"):
            lines.append(
                f"    earliest: {m.get('earliest_timestamp')}  latest: {m.get('latest_timestamp')}"
            )

    lines.append("")
    # Global stats: files per customer
    customer_counts = {}
    for e in global_entries:
        c = e.get("customer") or "UNKNOWN"
        customer_counts[c] = customer_counts.get(c, 0) + 1

    lines.append("Top customers by indexed file count:")
    for c, cnt in sorted(customer_counts.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {c}: {cnt}")

    lines.append("")
    # duplicates detection
    paths = [e.get("path") for e in global_entries]
    dup_count = len(paths) - len(set(paths))
    lines.append(f"Duplicate path occurrences across inputs: {dup_count}")

    lines.append("")
    return "\n".join(lines)


# -------------------------
# High-level orchestration
# -------------------------
def _collect_log_files(source: str | Path) -> List[Path]:
    p = Path(source)
    if p.is_file():
        return [p]
    if not p.exists():
        raise FileNotFoundError(f"Source path not found: {source}")
    # scan for *_index.log files
    files = sorted(
        [f for f in p.glob("*_index.log") if _is_index_log(f)], key=lambda x: x.name
    )
    return files


def _default_individual_out_name(log_path: Path, fmt: str) -> str:
    date = log_path.stem.split("_")[0]
    return f"{date}_cleaned.{fmt}"


def _default_combined_name(fmt: str) -> str:
    return f"index-cleaned-all.{fmt}"


def process_logs(
    source: str | Path,
    export: str = "json",
    out_path: str | Path | None = None,
    combine: bool = False,
    dedupe: bool = True,
) -> Dict[str, Any]:
    """
    Main entry point for multi-log processing.

    - source: file or directory
    - export: 'json'|'ndjson'|'csv'
    - out_path: when provided:
        * if source is a file -> used as exact output file path
        * if source is a directory:
            - combine=False -> if out_path is dir or None -> per-log outputs in that dir (or source dir)
            - combine=True -> out_path used as combined output file (if provided)
    - combine: merge all logs into single output if True
    - dedupe: when combining, dedupe entries by path
    """
    src = Path(source)
    log_files = _collect_log_files(src)
    if not log_files:
        print(f"[indexly] ⚠️  No index log files found in source: {src}")
        return {"written": [], "summary": None}


    per_log_meta = []
    all_entries: List[Dict[str, Any]] = []
    out_paths_written: List[str] = []

    # determine output base dir
    if out_path:
        out_target = Path(out_path)
    else:
        out_target = None

    # if source is file and out_path provided -> single-file behavior
    if src.is_file():
        entries, meta = _parse_log_lines(src)
        per_log_meta.append(meta)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "total_files": len(entries),
            "files": entries,
            "log_meta": meta,
        }
        # determine output name
        if out_target:
            out_file = out_target
        else:
            out_file = Path(_default_individual_out_name(src, "json"))
        if export == "json":
            _export_json(payload, out_file)
        elif export == "ndjson":
            _export_ndjson(entries, out_file)
        elif export == "csv":
            _export_csv(entries, out_file)
        out_paths_written.append(str(out_file))
        # write summary.txt beside out_file
        summary = _generate_summary(per_log_meta, entries)
        summary_path = out_file.parent / "summary.txt"
        summary_path.write_text(summary, encoding="utf-8")
        return {"written": out_paths_written, "summary": str(summary_path)}

    # source is dir: process multiple
    for logf in log_files:
        entries, meta = _parse_log_lines(logf)
        per_log_meta.append(meta)
        all_entries.extend(entries)

        if not combine:
            # per-log output
            if out_target:
                # if out_target exists and is dir -> write into it
                if out_target.exists() and out_target.is_dir():
                    out_file = out_target / _default_individual_out_name(logf, export)
                else:
                    # treat out_target as directory path (create) if it ends with os.sep or doesn't have extension
                    if str(out_target).endswith(os.sep) or out_target.suffix == "":
                        out_target.mkdir(parents=True, exist_ok=True)
                        out_file = out_target / _default_individual_out_name(
                            logf, export
                        )
                    else:
                        # user provided a filename; only meaningful when combine=True — fallback to source dir
                        out_file = Path(logf.parent) / _default_individual_out_name(
                            logf, export
                        )
                # ensure parent exists
                out_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_file = Path(logf.parent) / _default_individual_out_name(
                    logf, export
                )

            payload = {
                "timestamp": datetime.now().isoformat(),
                "total_files": len(entries),
                "files": entries,
                "log_meta": meta,
            }

            if export == "json":
                _export_json(payload, out_file)
            elif export == "ndjson":
                _export_ndjson(entries, out_file)
            elif export == "csv":
                _export_csv(entries, out_file)
            out_paths_written.append(str(out_file))

    # Post-processing for combined mode
    if combine:
        combined_entries = all_entries
        if dedupe:
            combined_entries = _dedupe_entries(combined_entries)

        combined_meta = {
            "combined_at": datetime.now().isoformat(),
            "source_count": len(log_files),
            "entry_count": len(combined_entries),
        }

        payload = {
            "timestamp": datetime.now().isoformat(),
            "total_files": len(combined_entries),
            "files": combined_entries,
            "combined_meta": combined_meta,
            "per_log_meta": per_log_meta,
        }

        # choose combined output path
        if out_target:
            # if target is a directory -> write index-cleaned-all
            if out_target.exists() and out_target.is_dir():
                out_file = out_target / _default_combined_name(export)
            else:
                # if looks like a directory path (endswith sep or has no suffix), create it
                if str(out_target).endswith(os.sep) or out_target.suffix == "":
                    out_target.mkdir(parents=True, exist_ok=True)
                    out_file = out_target / _default_combined_name(export)
                else:
                    out_file = out_target
        else:
            out_file = Path(_default_combined_name(export))

        out_file.parent.mkdir(parents=True, exist_ok=True)

        if export == "json":
            _export_json(payload, out_file)
        elif export == "ndjson":
            _export_ndjson(combined_entries, out_file)
        elif export == "csv":
            _export_csv(combined_entries, out_file)

        out_paths_written.append(str(out_file))

    # write global summary (summary.txt) in first out path's directory or source dir
    summary_dir = (
        Path(out_paths_written[0]).parent if out_paths_written else Path(source)
    )
    summary = _generate_summary(per_log_meta, all_entries)
    summary_path = summary_dir / "summary.txt"
    summary_path.write_text(summary, encoding="utf-8")

    return {"written": out_paths_written, "summary": str(summary_path)}


# -------------------------
# CLI wrapper kept simple
# -------------------------
def cli_log_clean(
    input_path: str,
    export_format: str = "json",
    out_path: str | None = None,
    combine: bool = False,
    dedupe: bool = True,
):
    """
    Backwards-compatible wrapper used by your argparse handler.
    - input_path: file or dir
    - export_format: json|ndjson|csv
    - out_path: optional path (file or directory) for outputs
    - combine: when source is dir, combine all logs
    - dedupe: when combine True, dedupe by path
    """
    res = process_logs(
        source=input_path,
        export=export_format,
        out_path=out_path,
        combine=combine,
        dedupe=dedupe,
    )
    # return info for caller / tests
    return res


# -------------------------
# Old-style handler for argparse integration
# -------------------------
def handle_log_clean(args):
    """
    Expect args to have:
      - file (path or directory)
      - export (json|ndjson|csv)
      - out (optional)
      - combine_logs (optional bool)
      - dedupe (optional bool)
    """
    out = getattr(args, "out", None)
    combine = getattr(args, "combine_log", False)
    dedupe = getattr(args, "dedupe", True)
    res = cli_log_clean(
        input_path=args.file,
        export_format=args.export,
        out_path=out,
        combine=combine,
        dedupe=dedupe,
    )
    print(f"✓ Written: {res.get('written')}")
    print(f"✓ Summary: {res.get('summary')}")
    return res
