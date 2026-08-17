"""Confirms every sensitive-looking column across the real schema is
hashed or encrypted before storage, never stored in plaintext (roadmap
step 254). A genuine audit, not an assumption: every real model was
checked by hand for this step and every credential-shaped column
already uses a real hash (argon2 for passwords/backup codes, a fast
hash for high-entropy tokens/API keys -- see each model's own docstring
for why) or real Fernet encryption (MFA TOTP secrets, which unlike a
password must be recoverable in plaintext to verify a code against
them). This test makes that state permanent -- a future column named
`api_secret`/`webhook_token`/etc. that stores a raw value fails here
immediately, rather than the gap only surfacing in a real incident.

Iterates `models.__all__` (the same canonical, Alembic-relied-upon
registry every real model is already required to appear in), not a
hand-maintained list of "sensitive tables" that could drift out of
date. A column counts as sensitive if its name contains one of a real
credential-shaped word (password/secret/token/credential/key) as a
whole `_`-separated token -- "encrypted"/"hash" appearing anywhere in
the name is the real signal it's already protected. Everything left
over must be in the explicit, reasoned exception list below, not a
blanket bypass -- each entry names the real, non-credential thing that
column actually is.
"""

import models

_SENSITIVE_TOKENS = {"password", "secret", "token", "credential", "key"}

# Confirmed NOT a raw credential, each for a real, specific reason --
# not "close enough" guesses. Adding a table/column here should be rare
# and should come with the same real justification as these.
_EXCEPTIONS = {
    # A deliberate, documented partial-plaintext display value (models/
    # api_key.py's own docstring): the raw key's own first several
    # characters, shown in a list view so a user can tell which key is
    # which without ever re-displaying the full secret -- the same UX
    # GitHub/Stripe use for their own API keys. key_hash (same model)
    # is the real credential, and it's already hashed.
    ("ApiKey", "key_prefix"),
    # An object-storage path/object-key (MinIO/S3), not a credential --
    # the same sense "key" has in "primary key" or "S3 object key", not
    # "secret key". storage.py's own real access/secret keys live in
    # config.py, never in this column.
    ("Document", "storage_key"),
    ("DocumentVersion", "storage_key"),
    # A permission identifier string (e.g. "analytics:read"), not a
    # secret -- the same sense "key" has in "dictionary key".
    ("Permission", "key"),
    # Real security-policy CONFIGURATION values (an int and three bools
    # -- minimum length, whether uppercase/a number/a symbol is
    # required), not a password itself.
    ("SecuritySettings", "password_min_length"),
    ("SecuritySettings", "password_require_uppercase"),
    ("SecuritySettings", "password_require_number"),
    ("SecuritySettings", "password_require_symbol"),
}


def test_every_sensitive_named_column_is_hashed_encrypted_or_a_reviewed_exception() -> None:
    unprotected: list[str] = []
    for model_name in models.__all__:
        model_class = getattr(models, model_name)
        table = getattr(model_class, "__table__", None)
        if table is None:
            continue
        for column in table.columns:
            tokens = set(column.name.split("_"))
            if not tokens & _SENSITIVE_TOKENS:
                continue
            if "hash" in column.name or "encrypted" in column.name:
                continue
            if (model_name, column.name) in _EXCEPTIONS:
                continue
            unprotected.append(f"{model_name}.{column.name}")

    assert unprotected == [], (
        "Sensitive-looking column(s) with no hash/encryption and no reviewed "
        f"exception: {unprotected}. Either hash/encrypt the real value before "
        "storage, or add a reasoned entry to _EXCEPTIONS above if it's genuinely "
        "not a credential."
    )
