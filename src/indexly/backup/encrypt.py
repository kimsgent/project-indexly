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
    return _encrypt_to_path(path, path, password)


def encrypt_archive(path: Path, password: str) -> Path:
    encrypted_path = Path(str(path) + ".enc")
    _encrypt_to_path(path, encrypted_path, password)
    path.unlink()
    return encrypted_path


def _encrypt_to_path(source: Path, destination: Path, password: str) -> Path:
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    f = Fernet(key)

    data = source.read_bytes()
    encrypted = f.encrypt(data)

    destination.write_bytes(salt + encrypted)
    return destination

def decrypt_file(path: Path, password: str):
    raw = path.read_bytes()
    salt, encrypted = raw[:16], raw[16:]
    key = _derive_key(password, salt)
    f = Fernet(key)

    path.write_bytes(f.decrypt(encrypted))
