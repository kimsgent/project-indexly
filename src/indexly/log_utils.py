"""
📄 log_utils.py

Purpose:
    Handles logging of indexing activities with timestamped filenames.

Key Features:
    - write_index_log(): Logs all indexed file paths with timestamps.

Usage:
    Called during indexing to keep a persistent record of what was indexed.
"""

from datetime import datetime

def log_index_event(event_type, path):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{event_type}] {path}")
