from __future__ import annotations

from functools import lru_cache

from indexly.optional_deps import require_extra_dependency


@lru_cache(maxsize=1)
def load_crypto_primitives():
    """Load cryptography primitives only when encrypted backup paths are used."""
    hashes = require_extra_dependency(
        module_name="cryptography.hazmat.primitives.hashes",
        package_name="cryptography",
        extra="backup",
    )
    pbkdf2 = require_extra_dependency(
        module_name="cryptography.hazmat.primitives.kdf.pbkdf2",
        package_name="cryptography",
        extra="backup",
    )
    fernet = require_extra_dependency(
        module_name="cryptography.fernet",
        package_name="cryptography",
        extra="backup",
    )
    return hashes, pbkdf2.PBKDF2HMAC, fernet.Fernet
