"""
📄 ripple.py

Purpose:
    Provides animated terminal output ("ripple" effect) during indexing/search.

Key Features:
    - Ripple(): Multithreaded spinner animation with optional rainbow and direction modes.

Usage:
    Wrap your long-running tasks with Ripple.start() and Ripple.stop() for visual feedback.
"""


# ripple.py
import os
import sys
import time
import itertools
import threading
import random


if os.name == 'nt':
    os.system('')  # Enables ANSI escape codes in some Windows terminals


class Ripple:
    def __init__(self, text, speed="medium", rainbow=False, direction="forward"):
        self.text = text
        self.speed = {"fast": 0.01, "medium": 0.03, "slow": 0.07}.get(speed, 0.03)
        self.rainbow = rainbow
        self.direction = direction
        self.running = False
        self.lock = threading.Lock()
        self._stop_event = threading.Event()

    def _ripple_effect(self):
        while not self._stop_event.is_set():
            with self.lock:
                sys.stdout.write("\r" + self._format_text())
                sys.stdout.flush()
            time.sleep(self.speed)

    def _format_text(self):
        chars = list(self.text)
        if self.direction == "reverse":
            chars.reverse()
        if self.rainbow:
            return "".join(f"\033[3{random.randint(1, 7)}m{c}\033[0m" for c in chars)
        return " ".join(chars)

    def start(self):
        with self.lock:
            if not self.running:
                self.running = True
                self._stop_event.clear()
                self.thread = threading.Thread(target=self._ripple_effect, daemon=True)
                self.thread.start()

    def stop(self):
        with self.lock:
            if self.running:
                self._stop_event.set()
                self.thread.join(timeout=0.2)
                sys.stdout.write("\r" + " " * (len(self.text) * 3) + "\r\n")  # add newline after clear
                sys.stdout.flush()
                self.running = False

