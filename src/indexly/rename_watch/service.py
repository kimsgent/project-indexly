"""Independent Watchdog and reconciliation service for rename-watch."""
from __future__ import annotations
import os, threading, time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from .config import RenameWatchConfigError, RenameWatchJob, initialize_settings, load_settings
from .logging import log_failure, log_move
from .planner import PlanMoveLog

def _temporary(path: Path) -> bool:
    return path.name.startswith(("~$", ".~")) or path.name.lower().endswith((".tmp", ".lock"))

def _inside(path: Path, parent: Path) -> bool:
    try: path.resolve().relative_to(parent.resolve()); return True
    except (ValueError, OSError): return False

class RenameWatchService:
    def __init__(self, jobs, state_root=None, clock=time.monotonic, sleeper=time.sleep):
        self.jobs = jobs; self.clock = clock; self.sleeper = sleeper; self.stop_event = threading.Event()
        self.pending = {}; self.snapshots = {}; self.next_scan = {j.job_id: 0.0 for j in jobs}
        self.movers = {j.job_id: PlanMoveLog(j, state_root) for j in jobs}; self.observers = []
    def _eligible(self, job, path):
        return path.exists() and path.is_file() and not _temporary(path) and _inside(path, job.watch_path) and not _inside(path, job.destination_path)
    def schedule(self, job, path, attempts=0, delay=0.0):
        path = Path(path)
        if not self._eligible(job, path): return
        key = (job.job_id, str(path.resolve())); due = self.clock() + delay
        old = self.pending.get(key)
        if old is None or due < old[2]: self.pending[key] = (job, path.resolve(), due, attempts)
    def reconcile(self, job):
        for path in job.watch_path.iterdir(): self.schedule(job, path)
    def _process(self, job, source, attempts):
        key = (job.job_id, str(source)); self.pending.pop(key, None)
        if not self._eligible(job, source): self.snapshots.pop(key, None); return
        stat = source.stat(); fingerprint = (stat.st_size, stat.st_mtime_ns)
        previous = self.snapshots.get(key)
        if previous != fingerprint:
            self.snapshots[key] = fingerprint; self.schedule(job, source, attempts, job.settle_seconds); return
        try:
            target = self.movers[job.job_id].plan_and_move(source)
            self.snapshots.pop(key, None); log_move(job.job_id, source, target, job.pattern, attempts + 1)
        except (PermissionError, OSError) as error:
            self.snapshots.pop(key, None)
            if attempts + 1 < job.retry.max_attempts and source.exists():
                delay = min(job.retry.initial_delay_seconds * (2 ** attempts), job.retry.max_delay_seconds)
                self.schedule(job, source, attempts + 1, delay)
            elif source.exists():
                target = job.destination_path / source.name
                log_failure(job.job_id, source, target, job.pattern, attempts + 1, error)
    def tick(self):
        now = self.clock()
        for job in self.jobs:
            if job.mode in ("interval", "hybrid") and now >= self.next_scan[job.job_id]:
                self.reconcile(job); self.next_scan[job.job_id] = now + job.scan_interval_seconds
        for job, path, due, attempts in list(self.pending.values()):
            if due <= now: self._process(job, path, attempts)
    def run_once(self):
        for job in self.jobs: self.reconcile(job)
        deadline = self.clock() + max(j.settle_seconds for j in self.jobs) + 0.1
        while self.pending and self.clock() <= deadline:
            self.tick(); self.sleeper(0.01)
    def _start_observers(self):
        service = self
        class Handler(FileSystemEventHandler):
            def __init__(self, job): self.job = job
            def on_created(self, event):
                if not event.is_directory: service.schedule(self.job, event.src_path)
            def on_modified(self, event):
                if not event.is_directory: service.schedule(self.job, event.src_path)
            def on_moved(self, event):
                if not event.is_directory: service.schedule(self.job, event.dest_path)
        for job in self.jobs:
            if job.mode not in ("event", "hybrid"): continue
            observer = Observer(); observer.schedule(Handler(job), str(job.watch_path), recursive=False); observer.start(); self.observers.append(observer)
    def run_forever(self):
        self._start_observers()
        try:
            while not self.stop_event.is_set(): self.tick(); self.stop_event.wait(0.1)
        finally: self.stop()
    def stop(self):
        self.stop_event.set()
        for observer in self.observers: observer.stop()
        for observer in self.observers: observer.join(timeout=2)
        self.observers = []

def handle_rename_watch(args):
    if getattr(args, "init", False):
        try:
            path = initialize_settings(args.config)
        except RenameWatchConfigError as error:
            raise ValueError(str(error))
        print("Created rename-watch configuration: {0}".format(path))
        print("Create the 'inbox' folder beside it, then run rename-watch again.")
        return
    try:
        settings = load_settings(args.config)
    except RenameWatchConfigError as error:
        raise ValueError(str(error))
    jobs = settings.jobs
    if getattr(args, "mode", None):
        jobs = [type(job)(**dict(job.__dict__, mode=args.mode)) for job in jobs]
    service = RenameWatchService(jobs)
    if getattr(args, "once", False):
        service.run_once()
    else:
        service.run_forever()