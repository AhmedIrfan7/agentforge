from auth.passwords import hash_password, needs_rehash, verify_password


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_hash_is_not_the_plaintext() -> None:
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert hashed.startswith("$argon2id$")


def test_fresh_hash_does_not_need_rehash() -> None:
    hashed = hash_password("hunter2")
    assert not needs_rehash(hashed)
