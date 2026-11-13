"""Authenticated encryption for Swiggy OAuth credentials."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SwiggyEncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.swiggy_token_encryption_key.strip()

    if not key:
        raise SwiggyEncryptionError(
            "SWIGGY_TOKEN_ENCRYPTION_KEY is not configured."
        )

    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SwiggyEncryptionError(
            "SWIGGY_TOKEN_ENCRYPTION_KEY is invalid. "
            "Generate a Fernet key before enabling Swiggy OAuth."
        ) from exc


def encrypt_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot encrypt an empty secret.")

    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        raise ValueError("Cannot decrypt an empty secret.")

    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, ValueError) as exc:
        raise SwiggyEncryptionError(
            "Stored Swiggy credential could not be decrypted."
        ) from exc
