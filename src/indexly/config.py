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

# -------------------------
# Semantic tiers
# -------------------------

TIER1_HUMAN = "human"
TIER2_SEMANTIC = "semantic"
TIER3_TECHNICAL = "technical"


# -------------------------
# Metadata classification
# -------------------------
# These keys MAY be converted into searchable text (Tier 2)

SEMANTIC_METADATA_KEYS = {
    "title",
    "author",
    "subject",
    "camera",
    "format",
    "source",          # added: already used in async_index_file
}


# These keys MUST NOT enter FTS text (Tier 3)
# Stored only as structured metadata

TECHNICAL_METADATA_KEYS = {
    "created",
    "modified",
    "last_modified",
    "image_created",
    "gps",
    "latitude",
    "longitude",
    "width",
    "height",
    "dimensions",
    "filesize",
    "size",
    "hash",
    "checksum",
    "md5",
    "sha1",
    "sha256",
}


# -------------------------
# Token policy
# -------------------------

# Minimum length for a token to be indexed
MIN_TOKEN_LENGTH = 3

# Drop tokens consisting only of digits
DROP_NUMERIC_ONLY = True


# -------------------------
# Safety / future-proofing
# -------------------------

# Characters that split tokens aggressively
# (used later in pre-filter, not tokenizer)
TOKEN_SPLIT_CHARS = r"[^\w:]+"


# Explicitly allowed tiers for FTS injection
# (used to prevent accidental Tier-3 leakage)
FTS_ALLOWED_TIERS = {
    TIER1_HUMAN,
    TIER2_SEMANTIC,
}
