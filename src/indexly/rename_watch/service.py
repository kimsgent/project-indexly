"""Independent Watchdog and reconciliation service for rename-watch."""
from __future__ import annotations
import os, threading, time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from .config import (
    RenameWatchConfigError,
    RenameWatchJob,
    ensure_watch_directory,
    initialize_settings,
    load_settings,
)
from .logging import log_failure, log_move
from .locking import WatchRootLock
from .planner import PlanMoveLog

def _temporary(path: Path) -> bool:
    return path.name.startswith(("~$", ".~")) or path.name.lower().endswith((".tmp", ".lock"))

def _inside(path: Path, parent: Path) -> bool:
    try: path.resolve().relative_to(parent.resolve()); return True
    except (ValueError, OSError): return False

class RenameWatchService:
    def __init__(self, jobs, state_root=None, clock=time.monotonic, sleeper=time.sleep):
        self.jobs = jobs; self.clock = clock; self.sleeper = sleeper; self.stop_event = threading.Event()
        self.state_root = state_root
        self._state_lock = threading.Lock()
        self.pending = {}; self.snapshots = {}; self.next_scan = {j.job_id: 0.0 for j in jobs}
        self.movers = {j.job_id: PlanMoveLog(j, state_root) for j in jobs}; self.observers = []; self.root_locks = []
    def _eligible(self, job, path):
        return path.exists() and path.is_file() and not path.is_symlink() and not _temporary(path) and _inside(path, job.watch_path) and not _inside(path, job.destination_path)
    def schedule(self, job, path, attempts=0, delay=0.0, reset_settle=False, required_delay=False):
        path = Path(path)
        if not self._eligible(job, path): return
        resolved = path.resolve(); key = (job.job_id, str(resolved)); now = self.clock(); due = now + delay
        with self._state_lock:
            old = self.pending.get(key)
            if reset_settle and key in self.snapshots:
                due = now + job.settle_seconds
                required_delay = True
            if old is not None:
                attempts = max(attempts, old[3])
                old_required = old[4]
                if old_required and required_delay:
                    due = max(due, old[2])
                elif old_required:
                    due = old[2]
                elif not required_delay:
                    due = min(due, old[2])
                required_delay = required_delay or old_required
            self.pending[key] = (job, resolved, due, attempts, required_delay)
    def _claim_due(self, now):
        claimed = []
        with self._state_lock:
            for key, value in list(self.pending.items()):
                if value[2] <= now:
                    claimed.append((key, value))
                    del self.pending[key]
        return claimed
    def _has_pending(self):
        with self._state_lock:
            return bool(self.pending)
    def _discard_snapshot(self, key):
        with self._state_lock:
            self.snapshots.pop(key, None)
    def _prepare_watch_paths(self):
        for job in self.jobs:
            ensure_watch_directory(job.watch_path, "job '{0}' watch_path".format(job.job_id))
    def _audit_move(self, job, result):
        log_move(
            job.job_id,
            result.source,
            result.destination,
            result.pattern,
            result.attempts,
            operation_id=result.operation_id,
            recovered=result.recovered,
        )
        self.movers[job.job_id].complete(result.operation_id)
    def _recover_job(self, job):
        for result in self.movers[job.job_id].recover_pending():
            self._audit_move(job, result)
    def _recover_pending_moves(self):
        for job in self.jobs:
            self._recover_job(job)
    def _acquire_root_locks(self):
        locks = []
        covered_keys = set()
        for job in self.jobs:
            lock = WatchRootLock(job.watch_path)
            if covered_keys.intersection(lock.keys):
                continue
            covered_keys.update(lock.keys)
            locks.append(lock)
        locks.sort(key=lambda item: item.key)
        acquired = []
        try:
            for lock in locks:
                lock.acquire(); acquired.append(lock)
        except BaseException:
            self.root_locks = acquired
            try:
                self._release_root_locks()
            except BaseException:
                pass
            raise
        self.root_locks = locks
    def _release_root_locks(self):
        first_error = None
        for lock in reversed(self.root_locks):
            try:
                lock.release()
            except BaseException as exc:
                if first_error is None: first_error = exc
        self.root_locks = []
        if first_error is not None: raise first_error
    def _stop_and_release(self):
        first_error = None
        try:
            self.stop()
        except BaseException as exc:
            first_error = exc
        try:
            self._release_root_locks()
        except BaseException as exc:
            if first_error is None: first_error = exc
        if first_error is not None: raise first_error
    def reconcile(self, job):
        ensure_watch_directory(job.watch_path, "job '{0}' watch_path".format(job.job_id))
        try:
            paths = list(job.watch_path.iterdir())
        except OSError as exc:
            raise RenameWatchConfigError(
                "job '{0}' watch_path could not be scanned: {1} ({2})".format(
                    job.job_id, job.watch_path, exc
                )
            ) from exc
        for path in paths: self.schedule(job, path)
    def _handle_processing_error(self, job, source, key, attempts, error):
        self._discard_snapshot(key)
        if attempts + 1 < job.retry.max_attempts and source.exists():
            delay = min(job.retry.initial_delay_seconds * (2 ** attempts), job.retry.max_delay_seconds)
            self.schedule(job, source, attempts + 1, delay, required_delay=True)
        elif source.exists():
            target = job.destination_path / source.name
            log_failure(job.job_id, source, target, job.pattern, attempts + 1, error)
    def _process(self, job, source, attempts):
        key = (job.job_id, str(source))
        try:
            recovered = self.movers[job.job_id].recover_pending(source, attempts + 1)
        except (PermissionError, OSError) as error:
            self._handle_processing_error(job, source, key, attempts, error)
            return
        for recovered_result in recovered:
            self._audit_move(job, recovered_result)
        if not self._eligible(job, source): self._discard_snapshot(key); return
        try:
            stat = source.stat(); fingerprint = (stat.st_size, stat.st_mtime_ns)
            with self._state_lock:
                previous = self.snapshots.get(key)
                if previous != fingerprint:
                    self.snapshots[key] = fingerprint
                replacement = self.pending.get(key)
                rescheduled = replacement is not None
                if replacement is not None and replacement[3] < attempts:
                    self.pending[key] = (
                        replacement[0], replacement[1], replacement[2], attempts, replacement[4]
                    )
            if previous != fingerprint:
                self.schedule(job, source, attempts, job.settle_seconds, required_delay=True); return
            if rescheduled:
                return
            result = self.movers[job.job_id].plan_and_move_operation(source, attempts + 1)
        except (PermissionError, OSError) as error:
            self._handle_processing_error(job, source, key, attempts, error)
        else:
            self._discard_snapshot(key)
            self._audit_move(job, result)
    def tick(self):
        now = self.clock()
        for job in self.jobs:
            if job.mode in ("interval", "hybrid") and now >= self.next_scan[job.job_id]:
                self.reconcile(job); self.next_scan[job.job_id] = now + job.scan_interval_seconds
        for _, (job, path, _, attempts, _) in self._claim_due(now):
            self._process(job, path, attempts)
    def run_once(self):
        self._prepare_watch_paths(); self._acquire_root_locks()
        try:
            self._recover_pending_moves()
            for job in self.jobs: self.reconcile(job)
            deadline = self.clock() + max(j.settle_seconds for j in self.jobs) + 0.1
            while self._has_pending() and self.clock() <= deadline:
                self.tick(); self.sleeper(0.01)
        finally:
            self._release_root_locks()
    def _start_observers(self):
        service = self
        class Handler(FileSystemEventHandler):
            def __init__(self, job): self.job = job
            def on_created(self, event):
                if not event.is_directory: service.schedule(self.job, event.src_path, reset_settle=True)
            def on_modified(self, event):
                if not event.is_directory: service.schedule(self.job, event.src_path, reset_settle=True)
            def on_moved(self, event):
                if not event.is_directory: service.schedule(self.job, event.dest_path, reset_settle=True)
        for job in self.jobs:
            if job.mode not in ("event", "hybrid"): continue
            ensure_watch_directory(job.watch_path, "job '{0}' watch_path".format(job.job_id))
            observer = Observer()
            self.observers.append(observer)
            try:
                observer.schedule(Handler(job), str(job.watch_path), recursive=False)
                observer.start()
            except Exception as exc:
                raise RenameWatchConfigError(
                    "job '{0}' watch_path could not be watched: {1} ({2})".format(
                        job.job_id, job.watch_path, exc
                    )
                ) from exc
    def run_forever(self):
        try:
            self._prepare_watch_paths(); self._acquire_root_locks()
            self._recover_pending_moves()
            self._start_observers()
            while not self.stop_event.is_set(): self.tick(); self.stop_event.wait(0.1)
        finally:
            self._stop_and_release()
    def stop(self):
        self.stop_event.set()
        for observer in self.observers: observer.stop()
        for observer in self.observers:
            if observer.is_alive(): observer.join(timeout=2)
        self.observers = []

def handle_rename_watch(args):
    if getattr(args, "init", False):
        try:
            path = initialize_settings(args.config)
        except RenameWatchConfigError as error:
            raise ValueError(str(error))
        print("Created rename-watch configuration: {0}".format(path))
        print("Created default watch folder: {0}".format(path.parent / "inbox"))
        return
    try:
        settings = load_settings(args.config)
        jobs = settings.jobs
        if getattr(args, "mode", None):
            jobs = [type(job)(**dict(job.__dict__, mode=args.mode)) for job in jobs]
        service = RenameWatchService(jobs)
        if getattr(args, "once", False):
            service.run_once()
        else:
            service.run_forever()
    except RenameWatchConfigError as error:
        raise ValueError(str(error))
