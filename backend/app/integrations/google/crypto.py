"""Authenticated encryption for Google OAuth credentials."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class GoogleCredentialError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.google_token_encryption_key.strip()
    if not key:
        raise GoogleCredentialError("GOOGLE_TOKEN_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise GoogleCredentialError("GOOGLE_TOKEN_ENCRYPTION_KEY is invalid. Generate a Fernet key.") from exc


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
        raise GoogleCredentialError("Stored Google credential could not be decrypted.") from exc
