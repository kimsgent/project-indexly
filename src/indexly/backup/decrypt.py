# ------------------------------
# src/indexly/backup/decrypt.py
# ------------------------------

import base64
import os
from pathlib import Path

from .crypto_deps import load_crypto_primitives


def _derive_key(password: str, salt: bytes) -> bytes:
    hashes, PBKDF2HMAC, _ = load_crypto_primitives()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def is_encrypted(path: Path) -> bool:
    return path.suffix == ".enc"


def decrypt_archive(path: Path, password: str, out_dir: Path) -> Path:
    _, _, Fernet = load_crypto_primitives()
    raw = path.read_bytes()
    salt, payload = raw[:16], raw[16:]
    key = _derive_key(password, salt)
    data = Fernet(key).decrypt(payload)

    out = out_dir / path.stem
    out.write_bytes(data)
    return out
