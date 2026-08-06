"""Password hashing — argon2id via argon2-cffi's high-level PasswordHasher,
which already uses sane defaults (time_cost, memory_cost, parallelism)
recommended by the OWASP password storage cheat sheet. Do not hand-roll
these parameters without a specific, documented reason.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    return True


def needs_rehash(hashed_password: str) -> bool:
    """True if the hash was made with older/weaker parameters than the
    hasher's current defaults — check this on successful login and
    re-hash+save if true, so stored hashes migrate forward automatically
    as argon2-cffi's recommended defaults improve over time."""
    return _hasher.check_needs_rehash(hashed_password)
