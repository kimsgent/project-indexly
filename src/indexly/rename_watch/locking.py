"""Portable interprocess locking for rename-watch roots."""

from __future__ import annotations

import ctypes
import os
import threading
from pathlib import Path

from .config import RenameWatchConfigError
from .identity import identity_hash, root_identity_strings

_PROCESS_KEYS = set()
_PROCESS_KEYS_LOCK = threading.Lock()


def _root_identities(root: Path) -> tuple[str, ...]:
    return root_identity_strings(root)


class WatchRootLock:
    """Hold non-blocking OS locks for one canonical watch root."""

    def __init__(self, watch_root: Path):
        self.watch_root = watch_root.resolve()
        identities = _root_identities(self.watch_root)
        self.key = identity_hash(identities[0])
        self.keys = tuple(sorted({identity_hash(value) for value in identities}))
        self._handles = []
        self._reserved = False

    def acquire(self) -> None:
        if self._reserved:
            return
        try:
            self._reserve_process_keys()
            for key in self.keys:
                self._handles.append(self._acquire_platform_lock(key))
        except BaseException as exc:
            self._release_handles()
            self._release_process_keys()
            if not isinstance(exc, OSError):
                raise
            raise RenameWatchConfigError(
                "watch_path is locked or unavailable for job execution: {0} ({1})".format(
                    self.watch_root, exc
                )
            ) from exc

    def release(self) -> None:
        first_error = self._release_handles()
        self._release_process_keys()
        if first_error is not None:
            raise first_error

    def _reserve_process_keys(self) -> None:
        with _PROCESS_KEYS_LOCK:
            if any(key in _PROCESS_KEYS for key in self.keys):
                raise BlockingIOError("watch root is already held by this process")
            _PROCESS_KEYS.update(self.keys)
            self._reserved = True

    def _release_process_keys(self) -> None:
        if not self._reserved:
            return
        with _PROCESS_KEYS_LOCK:
            for key in self.keys:
                _PROCESS_KEYS.discard(key)
            self._reserved = False

    def _acquire_platform_lock(self, key):
        if os.name == "nt":
            return ("windows", self._acquire_windows_mutex(key))
        return ("posix", self._acquire_posix_lock(key))

    @staticmethod
    def _acquire_windows_mutex(key):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        wait = kernel32.WaitForSingleObject
        wait.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        wait.restype = ctypes.c_uint32
        close = kernel32.CloseHandle
        close.argtypes = (ctypes.c_void_p,)
        close.restype = ctypes.c_int

        handle = create_mutex(None, False, "Global\\IndexlyRenameWatch-{0}".format(key))
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        result = wait(handle, 0)
        if result not in (0x00000000, 0x00000080):
            close(handle)
            if result == 0x00000102:
                raise BlockingIOError("named mutex is already held")
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    @staticmethod
    def _acquire_posix_lock(key):
        import fcntl

        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        path = Path("/tmp") / ("indexly-rename-watch-{0}.lock".format(key))
        descriptor = os.open(str(path), flags, 0o600)
        try:
            os.ftruncate(descriptor, 1)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    def _release_handles(self):
        first_error = None
        for kind, handle in reversed(self._handles):
            try:
                if kind == "windows":
                    self._release_windows_mutex(handle)
                else:
                    self._release_posix_lock(handle)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        self._handles = []
        return first_error

    @staticmethod
    def _release_windows_mutex(handle):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        release = kernel32.ReleaseMutex
        release.argtypes = (ctypes.c_void_p,)
        release.restype = ctypes.c_int
        close = kernel32.CloseHandle
        close.argtypes = (ctypes.c_void_p,)
        close.restype = ctypes.c_int
        try:
            if not release(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            close(handle)

    @staticmethod
    def _release_posix_lock(descriptor):
        import fcntl

        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
