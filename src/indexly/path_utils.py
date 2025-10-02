import os
import sys

def normalize_path(path: str) -> str:
    """
    Normalize file paths for consistent comparison and storage.

    - Expands ~ and environment variables
    - Converts to absolute, real path
    - Strips any Win32 long path prefix (\\?\)
    - Converts UNC \\server\share -> //server/share
    - Converts backslashes -> forward slashes
    - Removes trailing slash (except for root or network share root)
    - Lowercases only on Windows (case-insensitive FS),
      but preserves drive letter uppercase for readability
    """
    try:
        # Expand ~ and environment variables
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

        # Remove trailing slash except for "/" or "//server/share"
        if len(norm) > 1 and norm.endswith("/"):
            parts = norm.rstrip("/").split("/")
            # Keep //server/share intact
            if not (norm.startswith("//") and len(parts) == 3):
                norm = norm.rstrip("/")

        # Lowercase on Windows (case-insensitive FS),
        # but preserve drive letter uppercase
        if sys.platform.startswith("win"):
            if len(norm) >= 2 and norm[1] == ":":
                norm = norm[0].upper() + norm[1:].lower()
            else:
                norm = norm.lower()

        return norm

    except Exception:
        # Fallback: return absolute path to avoid relative surprises
        return os.path.abspath(path)
