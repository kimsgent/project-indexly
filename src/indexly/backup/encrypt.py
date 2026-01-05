from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
from pathlib import Path
import base64
import os

def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_file(path: Path, password: str):
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    f = Fernet(key)

    data = path.read_bytes()
    encrypted = f.encrypt(data)

    path.write_bytes(salt + encrypted)

def decrypt_file(path: Path, password: str):
    raw = path.read_bytes()
    salt, encrypted = raw[:16], raw[16:]
    key = _derive_key(password, salt)
    f = Fernet(key)

    path.write_bytes(f.decrypt(encrypted))
