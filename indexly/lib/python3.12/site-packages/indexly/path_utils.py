import os
import sys

def normalize_path(path: str) -> str:
    """
    Normalize file paths for consistent comparison and storage.
    - Expands ~ and environment variables
    - Converts to absolute, real path
    - Strips any Win32 long path prefix (\\?\)
    - Converts UNC \\server\share -> //server/share
    - Lowercases only on Windows (case-insensitive FS)
    - Converts backslashes -> forward slashes for cross-platform consistency
    - Removes trailing slash (except for root or network share root)
    """
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        norm = os.path.abspath(os.path.realpath(path))

        # Strip Windows long path prefix
        if norm.startswith("\\\\?\\"):
            norm = norm[4:]

        # UNC handling (\\server\share -> //server/share)
        if norm.startswith("\\\\"):
            norm = "//" + norm.lstrip("\\")

        # Always use forward slashes
        norm = norm.replace("\\", "/")

        # Remove trailing slash (except root "/" or "//server/share")
        if len(norm) > 1 and norm.endswith("/"):
            # Keep `//server/share` intact
            if not (norm.startswith("//") and norm.count("/") == 3):
                norm = norm.rstrip("/")

        # Lowercase only on Windows (case-insensitive FS)
        if sys.platform.startswith("win"):
            return norm.lower()

        return norm
    except Exception:
        return path
