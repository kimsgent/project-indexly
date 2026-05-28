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
import sys
from pathlib import Path


def _resolve_base_dir() -> str:
    """Return a user-writable runtime directory for Indexly state files."""
    explicit = os.environ.get("INDEXLY_HOME")
    if explicit:
        return str(Path(explicit).expanduser())

    home = Path.home()

    if sys.platform == "darwin":
        return str(home / "Library" / "Application Support" / "indexly")

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return str(Path(appdata) / "indexly")
        return str(home / "AppData" / "Roaming" / "indexly")

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return str(Path(xdg_data_home) / "indexly")

    return str(home / ".local" / "share" / "indexly")


# User data root (db/profile/cache/log files)
BASE_DIR = _resolve_base_dir()
os.makedirs(BASE_DIR, exist_ok=True)

PROFILE_FILE = os.path.join(BASE_DIR, "profiles.json")
DB_FILE = os.path.join(BASE_DIR, "fts_index.db")
CACHE_FILE = os.path.join(BASE_DIR, "search_cache.json")


def get_analysis_db_file() -> str:
    """Return the legacy analysis database path used by cleaned_data workflows."""
    explicit = os.environ.get("INDEXLY_ANALYSIS_DB")
    if explicit:
        return str(Path(explicit).expanduser())
    return str(Path.home() / ".indexly" / "indexly.db")


ANALYSIS_DB_FILE = get_analysis_db_file()

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
    "source",  # added: already used in async_index_file
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


# -------------------------
# Extraction cleanup
# -------------------------

# Regex patterns that mark the start of low-value email boilerplate.
# Keep these conservative: extraction stops at the first matching line.
EMAIL_BOILERPLATE_CUTOFFS = [
    r"^\s*mit freundlichen gr[üu]ßen\b",
    r"^\s*freundliche gr[üu]ße\b",
    r"^\s*viele gr[üu]ße\b",
    r"^\s*best regards\b",
    r"^\s*kind regards\b",
    r"^\s*regards\b",
    r"^\s*yours sincerely\b",
    r"^\s*_{5,}\s*$",
    r"^\s*-{5,}\s*$",
    r"^\s*von:\s",
    r"^\s*from:\s",
    r"^\s*gesendet:\s",
    r"^\s*sent:\s",
    r"^\s*betreff:\s",
    r"^\s*subject:\s",
    r"^\s*this email and any attachments are confidential\b",
    r"^\s*diese e-?mail und (?:alle )?anh[äa]nge sind vertraulich\b",
    r"^\s*please consider the environment before printing\b",
    r"^\s*bitte denken sie an die umwelt\b",
    r"^\s*company disclaimer\b",
    r"^\s*confidentiality notice\b",
    r"^\s*auto-?generated ticket\b",
    r"^\s*automatisch generierte ticket\b",
]
