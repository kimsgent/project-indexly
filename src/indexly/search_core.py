"""
📄 search_core.py

Purpose:
    Encapsulates FTS5 and regex-based file search logic.

Key Features:
    - search_fts5(): Full-text search with context, filters, fuzzy matching.
    - search_regex(): Pattern-based search using Python's re module.

Used by:
    - `indexly.py` (entry point)
"""

import os
import re
import time
import signal
import sqlite3
from datetime import datetime
from .ripple import Ripple
from .utils import build_snippet
from .db_utils import connect_db, get_tags_for_file
from .cache_utils import (
    load_cache,
    save_cache,
    cache_key,
    calculate_query_hash,
    is_cache_stale,
)
from .path_utils import normalize_path
from .cli_utils import filter_files_by_tag, enrich_results_with_tags
from nltk.tokenize import sent_tokenize
from rapidfuzz import fuzz, process
from colorama import Fore, Style
from .config import DB_FILE, PROFILE_FILE



user_interrupted = False


def handle_sigint(signum, frame):
    global user_interrupted
    user_interrupted = True
    print("\n⛔ Ctrl+C detected. Cleaning up...")


signal.signal(signal.SIGINT, handle_sigint)


def refresh_cache_if_stale(cache_key, cache_entry, no_write=False):
    entries = (
        cache_entry.get("results", []) if isinstance(cache_entry, dict) else cache_entry
    )
    if not entries:
        return []

    normalized_map = {
        normalize_path(e.get("path", e.get("normalized_path", ""))): e for e in entries
    }

    existing_paths = {p for p in normalized_map if p and os.path.exists(p)}
    stale_paths = [p for p in existing_paths if is_cache_stale(p, normalized_map[p])]

    if not stale_paths:
        return entries

    conn = connect_db()
    cursor = conn.cursor()

    # Batch SELECT for stale paths
    placeholders = ",".join("?" for _ in stale_paths)
    cursor.execute(
        f"SELECT path, content, modified, hash FROM file_index WHERE path IN ({placeholders})",
        stale_paths,
    )

    row_map = {
        normalize_path(row["path"]): {
            "path": normalize_path(row["path"]),
            "snippet": normalized_map.get(normalize_path(row["path"]), {}).get(
                "snippet", ""
            ),
            "content": row["content"],
            "modified": row["modified"],
            "hash": row["hash"],
            "tags": get_tags_for_file(row["path"]),
        }
        for row in cursor.fetchall()
    }

    conn.close()

    # Final updated entries
    updated_entries = [row_map.get(p, normalized_map[p]) for p in normalized_map]

    if updated_entries == entries:
        return entries

    if not no_write:
        cache = load_cache()
        cache[cache_key] = {"timestamp": time.time(), "results": updated_entries}
        save_cache(cache)
        print("💾 Updated cache after stale refresh.")

    return updated_entries


# --- Hybrid fuzzy fallback (vocab expansion + refined snippets) ---
def fuzzy_fallback(term, threshold=80, topn=5, context_chars=150, max_snippets=3):
    """
    Hybrid fuzzy fallback:
    - Expands query using vocab tokens + fuzzy ratio.
    - Executes expanded MATCH query with prefix matching.
    - Builds refined snippets around approximate matches.
    - Deduplicates results and enriches with tags.
    """
    term_words = [w.lower() for w in re.findall(r"\w+", term)
                  if w.upper() not in ("AND", "OR", "NOT") and len(w) > 1]
    if not term_words:
        return []

    conn = connect_db()
    cursor = conn.cursor()

    # Get vocab tokens
    try:
        cursor.execute("SELECT term FROM file_index_vocab")
        tokens = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"⚠️ Could not read vocab table: {e}")
        conn.close()
        return []

    query = " ".join(term_words)

    # Fuzzy match against vocab tokens
    matches = process.extract(query, tokens, scorer=fuzz.ratio, limit=topn)
    candidates = [m[0] for m in matches if m[1] >= threshold]

    if not candidates:
        conn.close()
        return []

    expanded = " OR ".join(f"{c}*" for c in candidates)
    print(f"🔁 Fuzzy expanded query: {expanded}")

    cursor.execute(
        "SELECT path, content FROM file_index WHERE file_index MATCH ?",
        (expanded,),
    )
    rows = cursor.fetchall()
    conn.close()

    results = []
    query_lc = query.lower()

    for row in rows:
        path = normalize_path(row["path"])
        content = row["content"] or ""

        # Fuzzy snippet: highlight approximate hits with fallback
        snippet_text = build_snippet(
            content,
            [query_lc],
            context_chars=context_chars,
            fuzzy=True,
            max_snippets=max_snippets,
        )

        results.append({
            "path": path,
            "snippet": snippet_text,
            "tags": get_tags_for_file(path),
            "source": "fuzzy",
        })

    # Deduplicate by normalized path
    dedup = {r["path"]: r for r in results}
    return list(dedup.values())


# ---------------------------------------------------------------------
# --- Expression utilities
# ---------------------------------------------------------------------

# --- Precompiled regex patterns for performance ---
_RE_NEAR = re.compile(r'\bNEAR\s*\(?\s*(\d+)?\s*\)?\b', re.IGNORECASE)
_RE_LOGICAL = re.compile(r'\b(and|or|not)\b', re.IGNORECASE)
_RE_TOKENIZER = re.compile(
    r'"[^"]*"|\(|\)|\bNEAR/\d+\b|\bAND\b|\bOR\b|\bNOT\b|[^"\s()]+',
    flags=re.IGNORECASE,
)
_RE_SAFE = re.compile(r'^[\w\s"\'()*+:\-~<>/]+$', re.IGNORECASE)


def sanitize_fts_term(term: str) -> str:
    """Ensure term contains only safe characters and valid operators."""
    if not term or not isinstance(term, str):
        raise ValueError("FTS term must be a non-empty string.")
    if not _RE_SAFE.match(term):
        raise ValueError(f"Unsafe or invalid FTS term: {term!r}")
    return term


# --- NEAR normalization & auto-quote multi-word terms ---
def normalize_near_term(expr: str, near_distance: int = 5) -> str:
    """
    Normalize NEAR constructs:
    - Converts `NEAR(5)` → `NEAR/5` (if supported)
    - Falls back to plain NEAR if NEAR/x is unsupported
    - Ensures there is a space after NEAR
    """
    if not expr:
        return ""

    # Replace any NEAR() or NEAR constructs with NEAR/x
    def _near_repl(match):
        n = match.group(1)
        return f"NEAR/{n or near_distance} "

    normalized = _RE_NEAR.sub(_near_repl, expr)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()

    # --- Runtime check for NEAR/x support ---
    try:
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        # If this fails, NEAR/x is not supported
        conn.execute("SELECT * FROM t WHERE c MATCH 'a NEAR/5 b'")
        conn.close()
    except sqlite3.OperationalError:
        # Downgrade NEAR/x → NEAR if unsupported
        normalized = re.sub(r"NEAR/\d+", "NEAR", normalized, flags=re.IGNORECASE)

    return normalized


def contains_fts_operators(term: str) -> bool:
    """Detect FTS5 logical operators and NEAR constructs."""
    term_upper = term.upper()
    return bool(re.search(r'\b(AND|OR|NOT|NEAR/?\d*)\b|\*|\(|\)|"', term_upper))


def normalize_logical_expression(query: str, near_distance: int = 5) -> str:
    """
    Normalize FTS5 logical query and safely apply NEAR where possible.
    Falls back gracefully if NEAR/N not supported.
    """
    import re, sqlite3

    if not query or not query.strip():
        return ""

    # Basic sanitization
    if not re.match(r'^[\w\s"\'()*+:\-~<>/]+$', query):
        raise ValueError(f"Unsafe FTS term: {query}")

    q = re.sub(r'\s+', ' ', query.strip())

    # Try to detect if NEAR/N is supported in this SQLite build
    supports_near_n = False
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x);")
        conn.execute("INSERT INTO t (x) VALUES ('a b c d e f g h i j k l');")
        conn.execute("SELECT * FROM t WHERE x MATCH 'a NEAR/3 d';")
        supports_near_n = True
    except sqlite3.OperationalError:
        supports_near_n = False
    finally:
        conn.close()

    # Apply NEAR distance only if supported
    if supports_near_n:
        q = re.sub(r'\bNEAR\b(?!/\d+)', f'NEAR/{near_distance}', q, flags=re.IGNORECASE)
    else:
        # Just ensure NEAR is uppercased and spacing normalized
        q = re.sub(r'\bNEAR\b(?!/\d+)', 'NEAR', q, flags=re.IGNORECASE)

    # Uppercase logical operators
    q = re.sub(r'\b(and|or|not|near(?:/\d+)?)\b', lambda m: m.group(1).upper(), q, flags=re.IGNORECASE)

    # Quote single terms safely
    if not any(op in q.upper() for op in ("AND", "OR", "NOT", "NEAR")) and not re.search(r'["()]', q):
        q = f'"{q}"'

    return q


# ---------------------------------------------------------------------
# --- Main FTS5 search
# ---------------------------------------------------------------------

def search_fts5(
    term,
    query,
    db_path,
    context_chars=150,
    filetypes=None,
    date_from=None,
    date_to=None,
    path_contains=None,
    tag_filter=None,
    use_fuzzy=False,
    fuzzy_threshold=80,
    no_cache=False,
    near_distance=5,
    author=None,
    camera=None,
    image_created=None,
    format=None,
):
    import re, sqlite3, time
    from rich.console import Console
    console = Console()


    # --- Load or skip cache ---
    cache = load_cache() if not no_cache else {}
    args_dict = {
        "term": term,
        "query": query,
        "context_chars": context_chars,
        "filetypes": filetypes,
        "date_from": date_from,
        "date_to": date_to,
        "path_contains": path_contains,
        "tag_filter": tag_filter,
        "use_fuzzy": use_fuzzy,
        "fuzzy_threshold": fuzzy_threshold,
        "near_distance": near_distance,
        "author": author,
        "camera": camera,
        "image_created": image_created,
        "format": format,
    }

    key = calculate_query_hash(term, args_dict)
    console.print(f"[bold green]Cache key:[/bold green] {key}")

    if key in cache:
        cached = cache[key].get("results", []) if isinstance(cache[key], dict) else cache[key]
        console.print("[green]✅ Returning cached results (no refresh)[/green]")
        return cached

    conn = connect_db(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- Normalize FTS5 expression ---
    fts_expr = normalize_logical_expression(query or term or "", near_distance)
    if not fts_expr.strip():
        console.print("[red]⚠️ Empty or invalid FTS expression, falling back to quoted term[/red]")
        fts_expr = f'"{term.strip()}"'
    console.print(f"[cyan]Normalized FTS expression:[/cyan] [white]{fts_expr}[/white]")

    # --- Build base query ---
    query_parts = ["SELECT fi.path, fi.content FROM file_index fi"]
    if any([author, camera, image_created, format]):
        query_parts.append("JOIN file_metadata fm ON fi.path = fm.path")

    # DO NOT use parameter substitution for MATCH
    query_parts.append(f"WHERE fi.content MATCH {fts_expr!r}")

    params = []

    # --- Apply filters (each step debug printed) ---
    if tag_filter:
        console.print(f"[magenta]Tag filter active:[/magenta] {tag_filter}")
        allowed_paths = filter_files_by_tag(tag_filter)
        if not allowed_paths:
            console.print("[yellow]⚠️ No files match the given tag filter[/yellow]")
            conn.close()
            return []
        placeholders = ",".join("?" for _ in allowed_paths)
        query_parts.append(f"AND fi.path IN ({placeholders})")
        params.extend(allowed_paths)

    if filetypes:
        console.print(f"[magenta]Filetype filter:[/magenta] {filetypes}")
        query_parts.append(f"AND ({' OR '.join('fi.path LIKE ?' for _ in filetypes)})")
        params.extend([f"%.{ext.lstrip('.')}" for ext in filetypes])

    if date_from:
        console.print(f"[magenta]Date from:[/magenta] {date_from}")
        query_parts.append("AND fi.modified >= ?")
        params.append(date_from)
    if date_to:
        console.print(f"[magenta]Date to:[/magenta] {date_to}")
        query_parts.append("AND fi.modified <= ?")
        params.append(date_to)
    if path_contains:
        console.print(f"[magenta]Path filter:[/magenta] {path_contains}")
        query_parts.append("AND fi.path LIKE ?")
        params.append(f"%{path_contains}%")
    if author:
        console.print(f"[magenta]Author filter:[/magenta] {author}")
        query_parts.append("AND fm.author LIKE ?")
        params.append(f"%{author}%")
    if camera:
        console.print(f"[magenta]Camera filter:[/magenta] {camera}")
        query_parts.append("AND fm.camera LIKE ?")
        params.append(f"%{camera}%")
    if image_created:
        console.print(f"[magenta]Image date filter:[/magenta] {image_created}")
        query_parts.append("AND fm.image_created LIKE ?")
        params.append(f"%{image_created}%")
    if format:
        console.print(f"[magenta]Format filter:[/magenta] {format}")
        query_parts.append("AND fm.format LIKE ?")
        params.append(f"%{format}%")

    query_parts.append("ORDER BY rank")
    query_str = "\n".join(query_parts)


    # --- Execute query safely ---
    try:
        cursor.execute(query_str, params)
        rows = cursor.fetchall()
        console.print(f"[green]✅ Query executed successfully ({len(rows)} rows)[/green]")
    except sqlite3.OperationalError as e:
        console.print(f"[red]⚠️ OperationalError:[/red] {e}")
        literal_query = " ".join(re.findall(r'\w+', term))
        console.print(f"[yellow]Retrying with fallback literal query:[/yellow] {literal_query}")
        fallback_query = "SELECT fi.path, fi.content FROM file_index fi WHERE fi.content MATCH ? ORDER BY rank"
        try:
            cursor.execute(fallback_query, [literal_query])
            rows = cursor.fetchall()
        except Exception as e2:
            console.print(f"[red]❌ Fallback failed:[/red] {e2}")
            conn.close()
            return []

    conn.close()

    # --- Handle no results / fuzzy fallback ---
    if not rows:
        if use_fuzzy:
            console.print("[yellow]🔁 No results, attempting fuzzy fallback...[/yellow]")
            return fuzzy_fallback(term, threshold=fuzzy_threshold, context_chars=context_chars)
        console.print("[red]❌ No results found, nothing cached.[/red]")
        return []

    # --- Extract search tokens ---
    all_tokens = [t[0] or t[1] for t in re.findall(r'"([^"]+)"|\b([\w-]+)\b', term) if t[0] or t[1]]
    search_terms = [t for t in all_tokens if t.upper() not in ("AND", "OR", "NOT")]

    # --- Build results ---
    serializable_results = [
        {
            "path": normalize_path(row["path"]),
            "snippet": build_snippet(row["content"], search_terms, context_chars=context_chars),
            "tags": get_tags_for_file(row["path"]),
        }
        for row in rows
    ]
    serializable_results = enrich_results_with_tags(serializable_results)

    # --- Cache results ---
    cache[key] = {"timestamp": time.time(), "results": serializable_results}
    save_cache(cache)
    console.print("[green]💾 Cached results successfully.[/green]")

    return serializable_results


def search_regex(
    pattern,
    query,
    db_path,
    context_chars=150,
    filetypes=None,
    date_from=None,
    date_to=None,
    path_contains=None,
    tag_filter=None,
    no_cache=False,
):
    

    cache = load_cache() if not no_cache else {}

    args_dict = {
        "pattern": pattern,
        "context_chars": context_chars,
        "filetypes": filetypes,
        "date_from": date_from,
        "date_to": date_to,
        "path_contains": path_contains,
        "tag_filter": tag_filter,
    }
    key = cache_key(args_dict)
    print(f"🔑 Regex Cache key: {key}")

    if key in cache:
        cached = cache[key].get("results", []) if isinstance(cache[key], dict) else cache[key]
        refreshed = refresh_cache_if_stale(key, cached, no_write=no_cache)
        if refreshed:
            print("✅ Using cached result")
            return refreshed
        else:
            print("⚠️ Cached result was empty. Falling back to DB...")

    conn = connect_db(db_path)
    cursor = conn.cursor()

    words = list(set(re.findall(r"[a-zA-ZÄÖÜäöüß]{4,}", pattern)))
    params = []
    query_parts = ["SELECT path, content FROM file_index"]
    conditions = []

    if len(words) >= 2:
        conditions.extend(["content LIKE ?" for _ in words])
        params.extend([f"%{w}%" for w in words])
    else:
        conditions.append("content REGEXP ?")
        params = [pattern]

    if tag_filter:
        allowed_paths = filter_files_by_tag(tag_filter)
        if not allowed_paths:
            return []
        placeholders = ",".join("?" for _ in allowed_paths)
        conditions.append(f"path IN ({placeholders})")
        params.extend(allowed_paths)

    if path_contains:
        conditions.append("path LIKE ?")
        params.append(f"%{path_contains}%")
    if date_from:
        conditions.append("modified >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("modified <= ?")
        params.append(date_to)
    if filetypes:
        ft_conditions = " OR ".join("path LIKE ?" for _ in filetypes)
        conditions.append(f"({ft_conditions})")
        params.extend([f"%.{ext.lstrip('.')}" for ext in filetypes])
    if conditions:
        query_parts.append("WHERE " + " AND ".join(conditions))

    try:
        cursor.execute(" ".join(query_parts), params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    regex = re.compile(pattern, re.IGNORECASE)

    results = []
    for row in rows:
        path = normalize_path(row["path"])
        content_raw = row["content"]
        if isinstance(content_raw, tuple):
            content_raw = content_raw[0] or ""
        if m := regex.search(content_raw):
            snippet = content_raw[max(0, m.start() - context_chars): m.end() + context_chars]
            results.append({
                "path": path,
                "snippet": snippet,
                "content": content_raw,
                "tags": get_tags_for_file(path),
            })

    results = enrich_results_with_tags(results)

    if results and not no_cache:
        cache[key] = {"timestamp": time.time(), "results": results}
        save_cache(cache)

    return results

