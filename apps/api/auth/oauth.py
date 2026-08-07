"""Google OAuth2 (roadmap step 076) — authorization-code flow, server-side
token exchange.

Deliberately does NOT decode/verify Google's id_token JWT itself. The
code exchange (exchange_google_code_for_userinfo) is a direct,
authenticated HTTPS call from this server to Google using our
client_secret — Google's response is trusted the same way any other
server-to-server API response is, not treated as untrusted client input.
Independently re-verifying an id_token's signature only matters for the
*implicit* flow, where a client-supplied token could be forged or
substituted; that risk doesn't apply here. Calling the userinfo endpoint
with the access token (rather than parsing the id_token ourselves) keeps
this simple and avoids a second, redundant trust mechanism.

The callback endpoint (routers/oauth.py) lives on this API directly,
not on the frontend — apps/web has no auth pages yet (see
config.py:app_base_url's docstring), and this milestone is backend-only.
A future frontend-hosted callback (matching the magic-link pattern of
"frontend owns the URL, backend does the work when asked") is a frontend
task for whenever apps/web grows auth pages, not a reason to block this
step on work that isn't scheduled yet.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from config import settings
from errors import UnauthorizedError

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class GoogleUserInfo:
    subject: str
    email: str
    email_verified: bool
    full_name: str


def build_google_authorize_url(state: str) -> str:
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
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_google_code_for_userinfo(code: str) -> GoogleUserInfo:
    """Exchanges an authorization code for Google's userinfo, or raises
    UnauthorizedError — a bad/expired/replayed code and a network-level
    failure both mean "this login attempt didn't work," and neither
    should leak Google's internal error detail to our caller."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            token_response = await client.post(
                _TOKEN_URL,
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
                _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo_response.raise_for_status()
            payload = userinfo_response.json()

            return GoogleUserInfo(
                subject=payload["sub"],
                email=payload["email"],
                email_verified=bool(payload.get("email_verified", False)),
                full_name=payload.get("name", payload["email"]),
            )
        except (httpx.HTTPError, KeyError) as exc:
            raise UnauthorizedError("Google sign-in failed.") from exc
