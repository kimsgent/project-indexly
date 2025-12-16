import pytest
import asyncio
import threading
import time
from indexly.log_utils import _default_logger, shutdown_logger

@pytest.mark.asyncio
async def test_async_logger_stress():
    logger = _default_logger  # <-- do not call, it's an instance

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
    shutdown_logger(timeout=5.0)

    # simple check: reached here without exceptions
    assert True
