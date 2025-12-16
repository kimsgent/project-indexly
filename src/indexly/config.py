"""
📄 config.py

Purpose:
    Central configuration for database and profile storage paths.

Key Features:
    - DB_FILE: SQLite database file path.
    - PROFILE_FILE: JSON file for saved search profiles.

Usage:
    Import constants into main script (e.g., `indexly.py`) or utility modules.
    
Access fonts in code with something like

import importlib.resources

with importlib.resources.path("indexly.assets", "DejaVuSans.ttf") as font_path:
    print("Font path:", font_path)
    
"""



import os

# Base directory (always where indexly.py is located)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROFILE_FILE = os.path.join(BASE_DIR, "profiles.json")
DB_FILE = os.path.join(BASE_DIR, "fts_index.db")
CACHE_FILE = os.path.join(BASE_DIR, "search_cache.json")

MAX_REFRESH_ENTRIES = 50
CACHE_REFRESH_INTERVAL = 86400  # 24h

LOG_DIR = os.path.join(BASE_DIR, "log")

MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB rotation limit
BATCH_SIZE = 50
FLUSH_INTERVAL = 2.0
COMPRESS_THRESHOLD = 4096  # 4KB
LOG_RETENTION_DAYS = 30
LOG_PARTITION = "daily"  # 'daily' or 'hourly'