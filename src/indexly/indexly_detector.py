# indexly_detector.py

"""
Lightweight Indexly detector for analyze-db pipeline.
Produces an `indexly` block:
{
  "is_indexly": bool,
  "fts": {"tables": [...], "shadow_map": {...}},
  "schema": {...},
  "metrics": {"vocab_size": int, "text_volume": int, "document_count": int, "token_distribution": {...}}
}

Design goals:
- Safe queries with fallbacks
- Minimal, dependency-free (stdlib only)
- Lightweight sampling for token distribution
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Iterable
import sqlite3
import re
import random

# Patterns for detecting shadow tables related to FTS tables
_FTS_SHADOW_PATTERNS = [
    re.compile(r"(.+)_data$"),
    re.compile(r"(.+)_idx$"),
    re.compile(r"(.+)_content$"),
    re.compile(r"(.+)_docsize$"),
    re.compile(r"(.+)_config$"),
    re.compile(r"(.+)_vocab$"),
]

_INDEXLY_LIKELY_TABLES = {
    "tags",
    "tag_relations",
    "documents",
    "file_index",
    "file_index_content",
    "file_index_docsize",
    "file_index_vocab",
    "file_index_idx",
    "file_metadata",
    "file_tags",
    "files",
}


def _fetch_table_names(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def detect_fts_virtual_tables(conn: sqlite3.Connection) -> List[str]:
    """Detect FTS5 virtual tables by inspecting sqlite_master `sql` column."""
    cur = conn.cursor()
    out: List[str] = []
    try:
        cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
        for name, sql in cur.fetchall():
            if not sql:
                continue
            # crude but effective: look for `USING fts5` or `VIRTUAL TABLE .* USING fts5`
            if "fts5" in sql.lower():
                out.append(name)
    except Exception:
        # best-effort: fall back to table name heuristics
        names = _fetch_table_names(conn)
        out = [n for n in names if any(p.search(n) for p in _FTS_SHADOW_PATTERNS)]
    return out


def detect_shadow_map(table_names: Iterable[str]) -> Dict[str, str]:
    """Map shadow tables to their base FTS table where possible."""
    names = set(table_names)
    shadow_map: Dict[str, str] = {}
    for t in names:
        for pattern in _FTS_SHADOW_PATTERNS:
            m = pattern.match(t)
            if m:
                base = m.group(1)
                # prefer exact base if present
                if base in names:
                    shadow_map[t] = base
                else:
                    # sometimes base is like file_index -> file_index (present)
                    shadow_map[t] = base
                break
    return shadow_map


def detect_indexly_schema(table_names: Iterable[str]) -> Dict[str, bool]:
    """Return boolean flags for commonly expected Indexly tables."""
    names = {t.lower() for t in table_names}
    return {k: (k in names) for k in _INDEXLY_LIKELY_TABLES}


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def compute_vocab_size(conn: sqlite3.Connection, table_candidates: Iterable[str]) -> int:
    """Attempt to compute vocab size by looking for `<fts>_vocab` tables or FTS auxiliary `vocab` if available."""
    cur = conn.cursor()
    total = 0
    for t in table_candidates:
        # common pattern: <fts>_vocab with column `term` or `token`
        try:
            cur.execute(f"SELECT COUNT(1) FROM '{t}'")
            total += _safe_int(cur.fetchone()[0])
        except Exception:
            continue
    return total


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _text_column_for_table(cur: sqlite3.Cursor, table: str) -> str | None:
    text_cols = ["content", "text", "body", "data"]
    quoted_table = _quote_identifier(table)

    try:
        cur.execute(f"PRAGMA table_info({quoted_table})")
        cols = cur.fetchall()
    except Exception:
        return None

    lower_cols = {r[1].lower(): r[1] for r in cols}
    for col in text_cols:
        if col in lower_cols:
            return lower_cols[col]

    for cid, name, ctype, nullable, dflt, pk in cols:
        if ctype and (
            "CHAR" in ctype.upper()
            or "TEXT" in ctype.upper()
            or "CLOB" in ctype.upper()
        ):
            return name

    if cols:
        return cols[0][1]
    return None


def compute_text_volume_and_doccount(
    conn: sqlite3.Connection,
    fts_tables: Iterable[str],
    *,
    exact: bool = False,
    sample_size: int = 500,
) -> Tuple[int, int, bool]:
    """Sum length of text columns for given FTS tables and count documents.
    This is best-effort: try common column names, otherwise fall back to `COUNT(*)`.
    """
    cur = conn.cursor()
    total_bytes = 0
    total_docs = 0
    estimated = False

    for tbl in fts_tables:
        doc_count = 0
        quoted_tbl = _quote_identifier(tbl)
        try:
            # try COUNT(*) first
            cur.execute(f"SELECT COUNT(1) FROM {quoted_tbl}")
            doc_count = _safe_int(cur.fetchone()[0])
            total_docs += doc_count
        except Exception:
            # skip if table inaccessible
            continue

        text_col_name = _text_column_for_table(cur, tbl)
        if not text_col_name:
            continue

        quoted_col = _quote_identifier(text_col_name)
        summed = 0
        if exact:
            try:
                cur.execute(f"SELECT SUM(LENGTH({quoted_col})) FROM {quoted_tbl}")
                summed = _safe_int(cur.fetchone()[0])
            except Exception:
                summed = 0
        else:
            limit = max(1, int(sample_size or 500))
            try:
                cur.execute(
                    f"SELECT AVG(LENGTH({quoted_col})) FROM "
                    f"(SELECT {quoted_col} FROM {quoted_tbl} LIMIT {limit})"
                )
                avg_len = cur.fetchone()[0]
                if avg_len is not None:
                    summed = int(float(avg_len) * doc_count)
                    estimated = True
            except Exception:
                summed = 0

        total_bytes += summed

    return total_bytes, total_docs, estimated


def sample_token_distribution(conn: sqlite3.Connection, fts_tables: Iterable[str], sample_size: int = 500) -> Dict[str, int]:
    """Lightweight token distribution by sampling rows from FTS tables and splitting on whitespace.
    Returns a small dict token -> count (top-k by sampling).
    """
    cur = conn.cursor()
    tokens: Dict[str, int] = {}

    rows_sampled = 0
    for tbl in fts_tables:
        if rows_sampled >= sample_size:
            break
        quoted_tbl = _quote_identifier(tbl)
        # get doc count to allow random sampling
        try:
            cur.execute(f"SELECT COUNT(1) FROM {quoted_tbl}")
            count = _safe_int(cur.fetchone()[0])
        except Exception:
            continue

        if count == 0:
            continue

        chosen_col = _text_column_for_table(cur, tbl)
        if not chosen_col:
            continue

        quoted_col = _quote_identifier(chosen_col)

        # sample row ids (use LIMIT if small, otherwise random offsets)
        to_sample = min(sample_size - rows_sampled, max(10, min(100, count)))
        # if table small, just select all
        if count <= to_sample:
            q = f"SELECT {quoted_col} FROM {quoted_tbl} LIMIT {to_sample}"
            try:
                cur.execute(q)
                for (txt,) in cur.fetchall():
                    if not txt:
                        continue
                    rows_sampled += 1
                    for tok in str(txt).split():
                        tokens[tok] = tokens.get(tok, 0) + 1
            except Exception:
                continue
        else:
            # random sampling by offset (best-effort)
            tried = 0
            attempts = to_sample * 3
            while rows_sampled < sample_size and tried < attempts:
                idx = random.randint(0, count - 1)
                try:
                    cur.execute(
                        f"SELECT {quoted_col} FROM {quoted_tbl} LIMIT 1 OFFSET {idx}"
                    )
                    row = cur.fetchone()
                    tried += 1
                    if not row:
                        continue
                    txt = row[0]
                    if not txt:
                        continue
                    rows_sampled += 1
                    for tok in str(txt).split():
                        tokens[tok] = tokens.get(tok, 0) + 1
                except Exception:
                    tried += 1
                    continue

    # reduce to top 50 tokens for compactness
    if tokens:
        items = sorted(tokens.items(), key=lambda x: x[1], reverse=True)[:50]
        return {k: v for k, v in items}
    return {}


def build_indexly_block(
    conn: sqlite3.Connection,
    schemas: Dict[str, Any],
    *,
    exact_metrics: bool = False,
    fast_mode: bool = False,
    sample_size: int | None = None,
) -> Dict[str, Any]:
    """Main public API: generate the indexly block given a DB connection and schema info.

    `schemas` is the usual mapping table -> list(columns) used by analyze-db pipeline.
    """
    table_names = list(schemas.keys())

    fts_tables = detect_fts_virtual_tables(conn)
    shadow_map = detect_shadow_map(table_names)

    # combine direct fts tables with those inferred by shadow mapping
    inferred_fts = set(fts_tables)
    for shadow, base in shadow_map.items():
        if base in table_names or base in inferred_fts:
            inferred_fts.add(base)

    schema_flags = detect_indexly_schema(table_names)

    # metrics
    # vocab candidates: any table that endswith _vocab or named *vocab*
    vocab_candidates = [t for t in table_names if t.lower().endswith('_vocab') or 'vocab' in t.lower()]
    vocab_size = compute_vocab_size(conn, vocab_candidates)

    metric_sample_size = sample_size or (100 if fast_mode else 500)
    text_volume, doc_count, text_volume_estimated = compute_text_volume_and_doccount(
        conn,
        inferred_fts,
        exact=exact_metrics,
        sample_size=metric_sample_size,
    )

    token_dist = (
        {}
        if fast_mode
        else sample_token_distribution(conn, inferred_fts, sample_size=metric_sample_size)
    )

    is_indexly = False
    # heuristics to determine Indexly-ness
    if any(schema_flags.get(k, False) for k in ("file_index", "file_index_content", "file_metadata", "file_tags")):
        is_indexly = True
    elif len(inferred_fts) >= 1 and len(vocab_candidates) >= 1:
        is_indexly = True

    return {
        "indexly": {
            "is_indexly": bool(is_indexly),
            "fts": {
                "tables": sorted(list(inferred_fts)),
                "shadow_map": shadow_map,
            },
            "schema": schema_flags,
            "metrics": {
                "vocab_size": int(vocab_size),
                "text_volume_bytes": int(text_volume),
                "text_volume_estimated": bool(text_volume_estimated),
                "document_count": int(doc_count),
                "token_distribution_sample": token_dist,
            },
        }
    }

