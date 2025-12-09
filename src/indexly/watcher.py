# watcher.py (async queue + worker pattern)
# Patch: 2025-12-09 – track indexed files, safe delete, debounce

import os
import asyncio
import time
import signal
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .fts_core import index_single_file_async, remove_file_from_index
from .log_utils import _default_logger, _unified_log_entry
from .filetype_utils import SUPPORTED_EXTENSIONS
from .path_utils import normalize_path


def is_temp_file(path):
    filename = os.path.basename(path)
    return (
        filename.startswith("~$")
        or filename.endswith(".tmp")
        or filename.startswith(".~")
        or filename.lower().endswith(".lock")
    )


def start_watcher(paths_to_watch):
    if isinstance(paths_to_watch, str):
        paths_to_watch = [paths_to_watch]

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    queue = asyncio.Queue()
    shutdown_event = asyncio.Event()
    indexed_files = set()  # track successfully indexed files

    observers = []

    class FileChangeHandler(FileSystemEventHandler):
        def __init__(self):
            self._debounce = {}

        def _should_process(self, path):
            now = time.time()
            last = self._debounce.get(path, 0)
            if now - last < 1.0:
                return False
            self._debounce[path] = now
            return True

        def _queue_file(self, path, event_type: str):
            entry = _unified_log_entry(event_type, path)
            if _default_logger.async_mode and _default_logger._loop:
                asyncio.run_coroutine_threadsafe(
                    _default_logger.alog(entry), _default_logger._loop
                )
            else:
                _default_logger._write_sync(entry)

            print(f"🕒 Queued for indexing: {path}")
            event_loop.call_soon_threadsafe(queue.put_nowait, path)

        # -----------------------------
        # ON CREATED
        # -----------------------------
        def on_created(self, event):
            if event.is_directory:
                return

            path = normalize_path(event.src_path)
            if not path:
                return

            if is_temp_file(path):
                return
            if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                return

            if self._should_process(path):
                self._queue_file(path, "CREATED")

        # -----------------------------
        # ON MODIFIED
        # -----------------------------
        def on_modified(self, event):
            if event.is_directory:
                return

            path = normalize_path(event.src_path)
            if not path:
                return

            if is_temp_file(path):
                return
            if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                return

            if self._should_process(path):
                self._queue_file(path, "MODIFIED")

        # -----------------------------
        # ON DELETED
        # -----------------------------
        def on_deleted(self, event):
            if event.is_directory:
                return

            raw_path = event.src_path
            path = normalize_path(raw_path)
            if not path:
                return

            # Log deletion with normalized path
            entry = _unified_log_entry("DELETED", path)
            if _default_logger.async_mode and _default_logger._loop:
                asyncio.run_coroutine_threadsafe(
                    _default_logger.alog(entry), _default_logger._loop
                )
            else:
                _default_logger._write_sync(entry)

            # Remove from index
            if path in indexed_files:
                remove_file_from_index(path)
                indexed_files.discard(path)
                print(f"🗑️ Removed from index: {path}")

            # Fix DOCX temp file cases (normalize here too)
            if raw_path.endswith(".docx") and "~$" in raw_path:
                base_name = normalize_path(raw_path.replace("~$", ""))
                if base_name and os.path.exists(base_name):
                    print(f"🔁 Rechecking modified file: {base_name}")
                    event_loop.call_soon_threadsafe(queue.put_nowait, base_name)


    # -----------------------------
    # QUEUE PROCESSOR (unchanged except normalization)
    # -----------------------------
    async def process_queue():
        while not shutdown_event.is_set():
            try:
                path = await asyncio.wait_for(queue.get(), timeout=1.0)

                # path is already normalized when queued, but check anyway
                norm = normalize_path(path)
                if not norm:
                    continue

                if os.path.exists(norm):
                    await index_single_file_async(norm)
                    indexed_files.add(norm)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"⚠️ Queue processing error: {e}")


    def stop_all():
        print("🛑 Stopping watchers...")
        shutdown_event.set()
        for observer in observers:
            observer.stop()
        for observer in observers:
            observer.join()
        event_loop.stop()
        print("✅ All watchers stopped.")

    for path in paths_to_watch:
        path = Path(path).resolve()
        if not path.exists() or not path.is_dir():
            print(f"❌ Invalid path: {path}")
            continue
        handler = FileChangeHandler()
        observer = Observer()
        observer.schedule(handler, str(path), recursive=True)
        observer.start()
        observers.append(observer)
        print(f"[🔍 WATCHING] {path} ...")

    signal.signal(signal.SIGINT, lambda *_: stop_all())

    try:
        event_loop.create_task(process_queue())
        event_loop.run_forever()
    finally:
        if not shutdown_event.is_set():
            stop_all()
