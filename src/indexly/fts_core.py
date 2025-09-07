"""
📄 fts_core.py

Purpose:
    Core indexing logic for FTS5 database and tag management.

Key Features:
    - calculate_hash(): Content-based MD5 hash generator.
    - index_single_file_async(): Async indexer for individual files.
    - extract_virtual_tags(): Detects and attaches tags from file content or metadata.
    - Tagging utilities: remove, add, format, list, filter.

Used by:
    - Indexing (index action)
    - Tagging operations from CLI
"""



import os
import re
from datetime import datetime
from .filetype_utils import extract_text_from_file, SUPPORTED_EXTENSIONS
from .db_utils import connect_db
from .path_utils import normalize_path
from .cli_utils import add_tags_to_file
from pathlib import Path



def calculate_hash(content: str) -> str:
    import hashlib
    return hashlib.md5(content.encode("utf-8")).hexdigest()



async def index_single_file_async(path):
    path = normalize_path(path)
    if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
        return

    conn = None
    try:
        # Extract text + metadata
        content, metadata = extract_text_from_file(path)

        # Normalize content to string
        if isinstance(content, dict):
            content = "\n".join(f"{k}: {v}" for k, v in content.items())
        elif content is None:
            content = ""

        if not content.strip() and not metadata:
            return  # nothing useful to index

        file_hash = calculate_hash(content)
        last_modified = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT hash FROM file_index WHERE path = ?", (path,))
        row = cursor.fetchone()
        if row and row["hash"] == file_hash:
            print(f"⏭️ Skipped (unchanged): {path}")
            return

        cursor.execute("DELETE FROM file_index WHERE path = ?", (path,))
        cursor.execute(
            """
            INSERT INTO file_index (path, content, modified, hash)
            VALUES (?, ?, ?, ?)
        """,
            (path, content, last_modified, file_hash),
        )
        conn.commit()

        # update metadata if present
        if metadata:
            from .extract_utils import update_file_metadata
            update_file_metadata(path, metadata)

        print(f"✅ Indexed: {path}")

    except Exception as e:
        print(f"⚠️ Failed to index {path}: {e}")
    finally:
        if conn:
            conn.close()


def remove_file_from_index(path):
    path = normalize_path(path)
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM file_index WHERE path = ?", (path,))
        conn.commit()
        print(f"🗑️ Removed from index: {path}")
    except Exception as e:
        print(f"⚠️ Failed to remove {path} from index: {e}")
    finally:
        conn.close()


def extract_virtual_tags(path: str, text: str = None, meta: dict = None):
    
    path = normalize_path(path)
    tags = []

    if meta:
        for k, v in meta.items():
            if v:
                tags.append(f"{k}: {v.strip()}")
    elif text:
        tag_fields = {
            "Kunde": r"\bKunde[:\.]?\s*([\w\-]+)",
            "Key-Nr": r"Key[-‐–]Nr[:\.]?\s*(\d{2}-\d{5})",
            "Erstellt von": r"Erstellt von[:\.]?\s*(\w+)",
            "Bereich": r"Bereich[:\.]?\s*([\w\s\-]+?)\s",
            "Erstellt am": r"Erstellt am[:\.]?\s*(\d{2}\.\d{2}\.\d{2,4})",
            "Version Kunde": r"Version Kunde[:\.]?\s*(V\s*[\d\.]+)",
            "Patch": r"Patch[:\.]?\s*(\d+)",
        }

        for label, pattern in tag_fields.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tags.append(f"{label}: {match.group(1).strip()}")

    if tags:
        add_tags_to_file(path, list(set(tags)))  # deduplicated


    return tags

