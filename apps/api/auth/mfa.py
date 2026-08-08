"""TOTP (RFC 6238) enrollment/verification and backup codes (roadmap
step 078).

The TOTP secret is encrypted at rest (Fernet, symmetric) rather than
hashed — unlike a password, a TOTP code can only be verified by
regenerating the expected code from the secret, which means the secret
itself must be recoverable in plaintext. Encryption, not hashing, is the
correct primitive for that; a compromised database still doesn't hand an
attacker the plaintext secrets without also having mfa_encryption_key
(config.py), which is deployment config, not stored alongside the data
it protects.

Backup codes are the opposite: they're compared for exact match, never
regenerated from something else, so they're hashed (argon2, same as
passwords — see models/mfa_backup_code.py's docstring for why a fast
hash wouldn't be enough here).
"""

import secrets
from dataclasses import dataclass

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from auth.passwords import hash_password, verify_password
from config import settings

_BACKUP_CODE_COUNT = 10
_BACKUP_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/1/i/l/o — hand-transcription
_ISSUER_NAME = "AgentForge"


def _fernet() -> Fernet:
    return Fernet(settings.mfa_encryption_key.encode("utf-8"))


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI an authenticator app scans as a QR code. Rendering
    the actual QR code is a frontend concern — the backend's job ends at
    handing back a URI any TOTP app can consume."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER_NAME)


def verify_totp_code(secret: str, code: str) -> bool:
    # valid_window=1 tolerates one 30-second step of clock drift either
    # side — standard practice; without it, a device even slightly out of
    # sync produces codes that never verify.
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_totp_secret(encrypted_secret: str) -> str | None:
    """None (not an exception) on a bad token — a corrupted/foreign
    ciphertext should read the same as "no secret," not crash the login
    attempt trying to use it."""
    try:
        return _fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


@dataclass(frozen=True)
class GeneratedBackupCodes:
    raw_codes: list[str]
    hashes: list[str]


def generate_backup_codes() -> GeneratedBackupCodes:
    """Ten codes, shown to the user exactly once by the caller — only the
    hashes are ever persisted (models/mfa_backup_code.py)."""
    raw_codes = [
        "".join(secrets.choice(_BACKUP_CODE_ALPHABET) for _ in range(10))
        for _ in range(_BACKUP_CODE_COUNT)
    ]
    return GeneratedBackupCodes(raw_codes=raw_codes, hashes=[hash_password(c) for c in raw_codes])


def verify_backup_code(raw_code: str, code_hash: str) -> bool:
    return verify_password(raw_code, code_hash)
