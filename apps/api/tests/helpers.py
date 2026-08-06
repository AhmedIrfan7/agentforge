"""Shared test helpers for hitting real authenticated endpoints — every
route under /organizations now requires a real access token (roadmap
steps 070-072), so any test exercising them needs one."""

from fastapi.testclient import TestClient


def signup_and_login(client: TestClient, *, email: str, password: str, full_name: str) -> str:
    """Signs up and logs in a real user via the actual endpoints, returns
    a bearer access token. Not a mock — this is the same path a real
    client goes through."""
    client.post("/auth/signup", json={"email": email, "password": password, "full_name": full_name})
    login_response = client.post("/auth/login", json={"email": email, "password": password})
    token: str = login_response.json()["access_token"]
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
