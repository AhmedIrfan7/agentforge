"""Generic OAuth2 login (roadmap step 077, generalizing step 076's
Google-only routes to /auth/{provider}/... over auth/oauth.py's
PROVIDERS registry — adding a new provider is a new entry there, not a
change here).

CSRF protection for the state parameter uses a double-submit cookie
(random nonce set as an httponly cookie on /login, compared byte-for-byte
against the query-string `state` the provider echoes back on /callback)
rather than server-side storage — there's nothing to look up, just a
match check, so a new stateful table would be pure overhead. One cookie
name shared across every provider is fine: the nonce itself, not the
cookie name, is what's checked, and only one OAuth attempt is ever in
flight per browser at a time.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth.oauth import PROVIDERS, OAuthProvider
from config import settings
from dependencies.db import get_db
from errors import NotFoundError, UnauthorizedError
from rate_limit import rate_limit
from repositories.oauth_identity import OAuthIdentityRepository
from repositories.user import UserRepository
from routers.auth import complete_login
from schemas.auth import MfaRequiredResponse, TokenResponse

router = APIRouter(prefix="/auth/{provider}", tags=["auth"])

_STATE_COOKIE_NAME = "oauth_state"
_STATE_COOKIE_MAX_AGE_SECONDS = 600


def _get_provider(provider: str) -> OAuthProvider:
    resolved = PROVIDERS.get(provider)
    if resolved is None:
        raise NotFoundError(f"Unknown auth provider '{provider}'.")
    return resolved


@router.get(
    "/login",
    dependencies=[Depends(rate_limit(key_prefix="oauth-login", limit=10, window_seconds=300))],
)
def oauth_login(provider: str) -> Response:
    provider_impl = _get_provider(provider)
    state = secrets.token_urlsafe(32)
    response = Response(status_code=302, headers={"Location": provider_impl.authorize_url(state)})
    response.set_cookie(
        _STATE_COOKIE_NAME,
        state,
        max_age=_STATE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        # Secure cookies are dropped outright over plain HTTP by any
        # spec-compliant client (browsers, httpx's cookie jar) -- "not
        # is_development" caught staging/production correctly but also
        # caught "test" (pytest's TestClient talks http://testserver),
        # silently discarding the cookie before the callback request ever
        # sent it. Real deployments terminate TLS in front of the app, so
        # explicit environments here, not a not-development guess.
        secure=settings.environment in ("staging", "production"),
        samesite="lax",
    )
    return response


@router.get(
    "/callback",
    response_model=TokenResponse | MfaRequiredResponse,
    dependencies=[Depends(rate_limit(key_prefix="oauth-callback", limit=10, window_seconds=300))],
)
async def oauth_callback(
    provider: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> TokenResponse | MfaRequiredResponse:
    provider_impl = _get_provider(provider)

    # Best-effort: only actually reaches the client on the success path
    # below — errors.py's AppError handler builds its own JSONResponse,
    # not this one, so a failed attempt leaves the cookie in place. Not a
    # real gap in practice: it's httponly, 10 minutes, and gets
    # overwritten by the next login attempt's fresh cookie anyway.
    response.delete_cookie(_STATE_COOKIE_NAME)
    cookie_state = request.cookies.get(_STATE_COOKIE_NAME)
    if cookie_state is None or not secrets.compare_digest(cookie_state, state):
        raise UnauthorizedError("Invalid or expired sign-in attempt.")

    oauth_user = await provider_impl.exchange_code_for_userinfo(code)
    if not oauth_user.email_verified:
        # The provider itself is the thing vouching for this email —
        # without that, linking or creating an account off it would be
        # trusting an unverified claim, exactly what the rest of this
        # app's email verification flow exists to prevent.
        raise UnauthorizedError(f"Your {provider_impl.name} account's email is not verified.")

    identity_repo = OAuthIdentityRepository(session)
    identity = await identity_repo.get_by_provider_and_subject(
        provider=provider_impl.name, provider_user_id=oauth_user.subject
    )

    user_repo = UserRepository(session)
    if identity is not None:
        user = await user_repo.get(identity.user_id)
        if user is None:
            raise UnauthorizedError("Invalid or expired sign-in attempt.")
    else:
        # The provider verified this email, so it satisfies our own
        # is_email_verified requirement too — same reasoning a verify-
        # email link would, just from a provider we trust instead of our
        # own token.
        user = await user_repo.get_by_email(oauth_user.email)
        if user is None:
            user = await user_repo.create(
                email=oauth_user.email,
                full_name=oauth_user.full_name,
                hashed_password=None,
                is_email_verified=True,
            )
        elif not user.is_email_verified:
            user.is_email_verified = True

        await identity_repo.create(
            user_id=user.id,
            provider=provider_impl.name,
            provider_user_id=oauth_user.subject,
            email=oauth_user.email,
        )

    return await complete_login(session, user, request)
