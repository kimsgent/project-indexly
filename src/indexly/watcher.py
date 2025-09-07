# watcher.py (async queue + worker pattern)
# Patch: 2025-07-11 – retry failed extraction, skip temp files, debounce writes

import os
import asyncio
import time
import signal
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .fts_core import index_single_file_async, remove_file_from_index
from .log_utils import log_index_event
from .filetype_utils import SUPPORTED_EXTENSIONS


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

        def on_created(self, event):
            if event.is_directory or is_temp_file(event.src_path):
                return
            if Path(event.src_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                return
            if self._should_process(event.src_path):
                log_index_event("CREATED", event.src_path)
                print(f"🕒 Queued for indexing: {event.src_path}")
                event_loop.call_soon_threadsafe(queue.put_nowait, event.src_path)

        def on_modified(self, event):
            if event.is_directory or is_temp_file(event.src_path):
                return
            if Path(event.src_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                return
            if self._should_process(event.src_path):
                log_index_event("MODIFIED", event.src_path)
                print(f"🕒 Queued for indexing: {event.src_path}")
                event_loop.call_soon_threadsafe(queue.put_nowait, event.src_path)

        def on_deleted(self, event):
            if event.is_directory:
                return
            log_index_event("DELETED", event.src_path)
            remove_file_from_index(event.src_path)
            # if it's a ~$ Word lock file, retry indexing the base file
            if event.src_path.endswith(".docx") and "~$" in event.src_path:
                base_name = event.src_path.replace("~$", "")
                if os.path.exists(base_name):
                    print(f"🔁 Rechecking modified file: {base_name}")
                    event_loop.call_soon_threadsafe(queue.put_nowait, base_name)

    async def process_queue():
        while not shutdown_event.is_set():
            try:
                path = await asyncio.wait_for(queue.get(), timeout=1.0)
                if os.path.exists(path):
                    await index_single_file_async(path)
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