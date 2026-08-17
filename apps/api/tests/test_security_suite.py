"""Consolidated security test suite (roadmap step 262): auth bypass,
cross-tenant access, and injection attempts.

Cross-tenant access and permission-denial already have extensive, real
coverage elsewhere in this suite -- not duplicated here, only pointed
at, so a reviewer looking for "does this app defend against X" doesn't
have to guess whether it's covered:
- test_tenant_isolation.py / test_memory_tenant_isolation.py /
  test_retrieval_tenant_isolation.py / test_voice_tenant_isolation.py
  prove real Postgres RLS blocks cross-tenant reads/writes at the DB
  level, independent of any application code.
- Nearly every *_endpoints.py file has its own
  "...not_visible_under_a_different_..." tests proving the same thing
  at the HTTP level, per resource type.
- test_security_event_logging.py's own
  test_cross_tenant_attempt_writes_a_real_audit_log_row_on_the_targeted_org
  and test_permission_denial_writes_a_real_audit_log_row prove the real
  audit trail both attack classes produce.
- test_rbac_enforcement.py proves the full role->permission matrix
  end-to-end, not just one spot-checked permission per role.

This file adds the two real gaps an audit of the existing suite found:

1. Auth bypass at the HTTP layer. test_jwt.py only unit-tests
   decode_access_token() directly -- nothing proved a real protected
   endpoint's own dependency wiring (dependencies/auth.py:
   get_current_user_id, HTTPBearer(auto_error=False)) actually rejects
   a missing/malformed/forged/expired token when called through a real
   request. Includes a permanent regression check that a wrong-secret-
   signed token is rejected (the real thing that would break if a
   future refactor ever disabled signature verification, e.g. PyJWT's
   own `options={"verify_signature": False}` -- confirmed live that
   this genuinely bypasses everything else) and that an alg=none
   forgery is rejected (a well-known, real JWT attack class).

2. Injection attempts. Zero existing coverage anywhere. SQLAlchemy's
   ORM (Column comparisons, func.plainto_tsquery(...) via
   repositories/chunk.py) parameterizes every query by construction --
   there is no raw, string-formatted SQL anywhere in this codebase to
   inject into -- but that invariant deserves a real, permanent test
   proving a SQL-injection-shaped payload is stored/returned as inert
   literal text, not executed, rather than resting on "the ORM
   probably handles it."
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from auth.jwt import create_access_token
from config import settings
from main import app
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


# --- Auth bypass -------------------------------------------------------


def test_missing_authorization_header_is_rejected() -> None:
    response = client.get("/organizations")
    assert response.status_code == 401


def test_malformed_authorization_scheme_is_rejected() -> None:
    response = client.get("/organizations", headers={"Authorization": "not-a-bearer-scheme"})
    assert response.status_code == 401


def test_garbage_bearer_token_is_rejected() -> None:
    response = client.get("/organizations", headers=auth_headers("garbage.not.a.jwt"))
    assert response.status_code == 401


def test_token_signed_with_the_wrong_secret_is_rejected() -> None:
    forged = pyjwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access"},
        "an-attackers-guess-at-the-secret",
        algorithm="HS256",
    )
    response = client.get("/organizations", headers=auth_headers(forged))
    assert response.status_code == 401


def test_algorithm_none_forgery_is_rejected() -> None:
    # A classic real JWT attack: a token whose own header claims
    # alg=none, no signature at all. Some JWT libraries have historically
    # trusted whatever algorithm the CALLER's own token header claimed.
    # Confirmed live (python -c, not assumed) that TWO independent layers
    # both have to hold for this to stay rejected: PyJWT itself refuses
    # alg=none unless the verification key is literally None (ours is a
    # real secret string, never None), AND auth/jwt.py's own explicit
    # `algorithms=["HS256"]` pin rejects "none" outright regardless. This
    # test is the permanent regression check for that combination, not
    # just one of the two.
    forged = pyjwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access"},
        key=None,  # type: ignore[arg-type]
        algorithm="none",
    )
    response = client.get("/organizations", headers=auth_headers(forged))
    assert response.status_code == 401


def test_expired_token_is_rejected() -> None:
    expired = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": datetime.now(UTC) - timedelta(hours=1),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    response = client.get("/organizations", headers=auth_headers(expired))
    assert response.status_code == 401


def test_a_real_valid_token_is_accepted() -> None:
    # The negative-only assertions above would trivially pass if EVERY
    # request were rejected regardless of the token -- this proves the
    # endpoint really does accept a genuinely valid one, so the 401s
    # above are proof of real validation, not a broken/always-401 route.
    token = create_access_token(uuid.uuid4())
    response = client.get("/organizations", headers=auth_headers(token))
    assert response.status_code == 200


# --- Injection attempts --------------------------------------------------

SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE organizations; --",
    "' OR '1'='1",
    "Robert'); DROP TABLE organizations;--",
]


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_shaped_organization_name_is_stored_as_inert_text(payload: str) -> None:
    token = signup_and_login(
        client,
        email=f"security-suite-sqli-{uuid.uuid4().hex[:8]}@example.com",
        password="correct horse battery staple 1",
        full_name="Security Suite Test User",
    )
    response = client.post(
        "/organizations",
        json={"name": payload, "slug": f"sqli-test-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    # Stored and returned VERBATIM as a literal string, not executed --
    # the real proof SQLAlchemy's parameterized queries hold against a
    # real injection attempt, not just "no exception was raised."
    assert response.json()["name"] == payload

    # The table this payload TRIES to drop is still there and still
    # works -- the strongest possible proof nothing was executed.
    list_response = client.get("/organizations", headers=auth_headers(token))
    assert list_response.status_code == 200


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_shaped_login_email_is_rejected_as_invalid_credentials(payload: str) -> None:
    # A classic login-form injection attempt (the payload IS the
    # username field) -- must fail as ordinary bad credentials, not
    # crash, not 500, not bypass authentication.
    response = client.post("/auth/login", json={"email": payload, "password": "irrelevant"})
    assert response.status_code in (401, 422)
