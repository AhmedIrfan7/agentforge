"""OAuth2 provider abstraction (roadmap step 077, generalizing step 076's
Google-only implementation).

OAuthProvider is a structural Protocol, not an ABC — nothing here needs
inheritance, shared state, or template-method behavior between
providers; each provider is a self-contained adapter around one external
service's specific endpoints and response shapes. routers/oauth.py talks
only to this interface (plus the PROVIDERS registry below), so adding
GitHub/Microsoft/SAML/OIDC later means writing one new class and adding
one registry entry — the router, the CSRF handling, and the account
linking/creation logic never change.

Every concrete provider follows the same trust model GoogleOAuthProvider
established in step 076: the authorization-code exchange is a direct,
authenticated HTTPS call from this server to the provider using our
client_secret, so the provider's response is trusted the way any
server-to-server API response is, not treated as untrusted client
input — no independent id_token/JWT re-verification needed, since that
concern only applies to the *implicit* flow's client-supplied tokens.

The callback endpoint lives on this API directly, not on the frontend —
apps/web has no auth pages yet (see config.py:app_base_url's docstring),
and this milestone is backend-only.
"""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from config import settings
from errors import UnauthorizedError


@dataclass(frozen=True)
class OAuthUserInfo:
    subject: str
    email: str
    email_verified: bool
    full_name: str


class OAuthProvider(Protocol):
    name: str

    def authorize_url(self, state: str) -> str: ...

    async def exchange_code_for_userinfo(self, code: str) -> OAuthUserInfo: ...


class GoogleOAuthProvider:
    name = "google"

    _AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            # We mint our own refresh tokens (auth/jwt.py) — no need for
            # Google's, so no offline access / consent-prompt-every-time.
            "access_type": "online",
        }
        return f"{self._AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_userinfo(self, code: str) -> OAuthUserInfo:
        """Exchanges an authorization code for the user's profile, or
        raises UnauthorizedError — a bad/expired/replayed code and a
        network-level failure both mean "this login attempt didn't work,"
        and neither should leak the provider's internal error detail to
        our caller."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                token_response = await client.post(
                    self._TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": settings.google_client_id,
                        "client_secret": settings.google_client_secret,
                        "redirect_uri": settings.google_redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                token_response.raise_for_status()
                access_token = token_response.json()["access_token"]

                userinfo_response = await client.get(
                    self._USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
                )
                userinfo_response.raise_for_status()
                payload = userinfo_response.json()

                return OAuthUserInfo(
                    subject=payload["sub"],
                    email=payload["email"],
                    email_verified=bool(payload.get("email_verified", False)),
                    full_name=payload.get("name", payload["email"]),
                )
            except (httpx.HTTPError, KeyError) as exc:
                raise UnauthorizedError("Google sign-in failed.") from exc


# Keyed by the same string stored in OAuthIdentity.provider and used in
# the /auth/{provider}/... URL segment. A provider missing here is a 404
# at the route, not a crash (routers/oauth.py) — same fail-closed
# reasoning as everywhere else an unknown identifier is looked up.
PROVIDERS: dict[str, OAuthProvider] = {
    "google": GoogleOAuthProvider(),
}
