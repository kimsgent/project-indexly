import pytest
import asyncio
import threading
import time
import importlib


def _load_log_utils_with_home(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEXLY_HOME", str(tmp_path))

    import indexly.config as config
    import indexly.log_utils as log_utils

    importlib.reload(config)
    importlib.reload(log_utils)
    return log_utils


def test_flush_does_not_force_small_batch_to_disk(tmp_path, monkeypatch):
    log_utils = _load_log_utils_with_home(tmp_path, monkeypatch)
    logger = log_utils.LogManager(
        log_dir=tmp_path / "log",
        batch_size=50,
        flush_interval=60,
    )

    logger.log({"event": "SMALL_BATCH", "path": "/tmp/file.txt"})
    logger.flush(timeout=1.5)

    assert list((tmp_path / "log").rglob("*.ndjson")) == []
    logger.stop(timeout=2.0)


@pytest.mark.asyncio
async def test_async_logger_stress(tmp_path, monkeypatch):
    log_utils = _load_log_utils_with_home(tmp_path, monkeypatch)

    logger = log_utils.LogManager(log_dir=tmp_path / "log")

    # -----------------------------
    # async spam
    # -----------------------------
    async def spam_async(id_: int, n: int = 1500):
        for i in range(n):
            logger.log({"event": f"ASYNC_{id_}", "path": f"/tmp/file_{i}.txt"})
            await asyncio.sleep(0)

    # -----------------------------
    # thread spam
    # -----------------------------
    def spam_thread(id_: int, n: int = 1500):
        for i in range(n):
            logger.log({"event": f"THREAD_{id_}", "path": f"/tmp/file_{i}.txt"})
            time.sleep(0.0001)

    # launch async tasks
    async_tasks = [asyncio.create_task(spam_async(i)) for i in range(5)]

    # launch threads
    threads = [threading.Thread(target=spam_thread, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()

    # extra burst on main thread
    for _ in range(1000):
        logger.log({"event": "MAIN", "path": "/tmp/file_main.txt"})

    # wait for async tasks
    await asyncio.gather(*async_tasks)

    # wait for threads
    for t in threads:
        t.join()

    # shutdown logger cleanly
    logger.stop(timeout=5.0)

    # simple check: reached here without exceptions
    assert True
