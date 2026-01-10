# semantic_index.py
import re
from typing import Dict, Any, Optional, Union, Tuple

from .config import (
    MIN_TOKEN_LENGTH,
    DROP_NUMERIC_ONLY,
    SEMANTIC_METADATA_KEYS,
    TECHNICAL_METADATA_KEYS,
)

# Check for overlapping keys
_overlap = SEMANTIC_METADATA_KEYS & TECHNICAL_METADATA_KEYS
if _overlap:
    raise RuntimeError(
        f"Metadata keys cannot be both semantic and technical: {_overlap}"
    )

_NUMERIC_RE = re.compile(r"^\d+$")

def _normalize_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(map(str, value))
    return str(value)

# -------------------------
# Phase 2.2 — Weighted semantic fields
# -------------------------
SEMANTIC_WEIGHTS = {
    "title": 3,
    "subject": 2,
    "author": 1,
    "camera": 1,
    "format": 1,
}

def semantic_filter_text(
    text: str,
    *,
    tier: str = "human",
    allow_numeric: bool = False
) -> str:
    """
    Tier-aware semantic pre-filter.
    - tier: 'human' (Tier1), 'semantic' (Tier2), 'technical' (Tier3)
    - Drops tokens < MIN_TOKEN_LENGTH
    - Drops numeric-only tokens unless allowed
    - Preserves key:value structure for Tier2 metadata
    """
    if not text:
        return ""

    tokens = text.split()
    out = []

    for tok in tokens:
        # Always drop short tokens
        if len(tok) < MIN_TOKEN_LENGTH:
            continue

        # Drop numeric-only tokens unless allowed
        if DROP_NUMERIC_ONLY and not allow_numeric and _NUMERIC_RE.match(tok):
            continue

        # Tier 2 metadata: preserve key:value if present
        if tier == "semantic" and ":" in tok:
            key, val = tok.split(":", 1)
            key = key.strip()
            val = val.strip()
            if len(val) < MIN_TOKEN_LENGTH:
                continue
            out.append(f"{key}:{val}")
            continue

        # For Tier 1 and Tier 3, normal token inclusion
        out.append(tok)

    return " ".join(out)


def split_metadata_tiers(metadata: dict) -> Tuple[dict, dict]:
    """Separate metadata into semantic (Tier 2) and technical (Tier 3)"""
    semantic = {}
    technical = {}

    for k, v in metadata.items():
        if v in (None, "", []):
            continue
        if k in SEMANTIC_METADATA_KEYS:
            semantic[k] = v
        elif k in TECHNICAL_METADATA_KEYS:
            technical[k] = v

    return semantic, technical

def build_semantic_fts_text(metadata: dict, weighted: bool = True) -> str:
    """
    Build Tier-2 FTS text with optional weighting
    Phase 2.2: weighted semantic fields
    """
    semantic, _ = split_metadata_tiers(metadata)
    parts: list[str] = []

    for key, value in semantic.items():
        normalized = _normalize_value(value)
        filtered = semantic_filter_text(normalized)
        if not filtered:
            continue

        if weighted and key in SEMANTIC_WEIGHTS:
            # Repeat key proportional to weight for FTS ranking
            parts.extend([f"{key}:{filtered}"] * SEMANTIC_WEIGHTS[key])
        else:
            parts.append(f"{key}:{filtered}")

    return " ".join(parts)

# -------------------------
# Phase 2.3 — Tier 3 numeric / range filters
# -------------------------
def build_technical_filters(metadata: dict) -> dict:
    """
    Returns only Tier 3 technical fields (filtered numeric/text)
    Useful for numeric/range queries
    """
    _, technical = split_metadata_tiers(metadata)
    filters = {}
    for key, value in technical.items():
        normalized = _normalize_value(value)
        if isinstance(value, (int, float)) or _NUMERIC_RE.match(normalized):
            filters[key] = float(normalized)
        else:
            filters[key] = normalized
    return filters

# -------------------------
# Phase 2.4 — Metadata query parsing
# -------------------------
def parse_metadata_query(
    query: str,
) -> Tuple[dict, dict]:
    """
    Parse query like 'author:John year:2023 width:>=1024'
    Returns:
        semantic_q: dict for Tier2 FTS matching
        technical_q: dict for Tier3 SQL filtering
    """
    semantic_q = {}
    technical_q = {}
    tokens = query.split()

    for tok in tokens:
        if ":" not in tok:
            continue
        key, val = tok.split(":", 1)
        key = key.strip()
        val = val.strip()
        if key in SEMANTIC_METADATA_KEYS:
            semantic_q[key] = val
        elif key in TECHNICAL_METADATA_KEYS:
            technical_q[key] = val

    return semantic_q, technical_q

# -------------------------
# Utility to combine full metadata FTS text
# -------------------------
def build_metadata_text(metadata: dict) -> Tuple[str, dict]:
    """
    Returns:
      - semantic_text (Tier 2 only, filtered & weighted)
      - full_metadata (Tier 2 + Tier 3, untouched)
    """
    semantic_text = build_semantic_fts_text(metadata)
    return semantic_text, metadata
