from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Final

from cryptography.fernet import Fernet


PBKDF2_ITERS: Final[int] = int(os.getenv("GRID_PBKDF2_ITERS", "200000"))


def new_salt_b64(length: int = 16) -> str:
    return base64.urlsafe_b64encode(os.urandom(length)).decode("ascii")


def pbkdf2_bytes(password: str, salt_b64: str, length: int = 32) -> bytes:
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS, dklen=length)


def password_hash_b64(password: str, salt_b64: str) -> str:
    return base64.urlsafe_b64encode(pbkdf2_bytes(password, salt_b64, length=32)).decode("ascii")


def verify_password(password: str, salt_b64: str, expected_hash_b64: str) -> bool:
    actual = password_hash_b64(password, salt_b64)
    return hmac.compare_digest(actual, expected_hash_b64)


def derive_fernet(password: str, kdf_salt_b64: str) -> Fernet:
    key_raw = pbkdf2_bytes(password, kdf_salt_b64, length=32)
    key = base64.urlsafe_b64encode(key_raw)
    return Fernet(key)


def encrypt_str(fernet: Fernet, plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(fernet: Fernet, token: str) -> str:
    return fernet.decrypt(token.encode("ascii")).decode("utf-8")

