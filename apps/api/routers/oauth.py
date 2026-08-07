"""Google OAuth2 login (roadmap step 076).

CSRF protection for the state parameter uses a double-submit cookie
(random nonce set as an httponly cookie on /login, compared byte-for-byte
against the query-string `state` Google echoes back on /callback) rather
than server-side storage — there's nothing to look up, just a match
check, so a new stateful table would be pure overhead. See
auth/oauth.py's module docstring for why the callback doesn't
independently re-verify Google's id_token.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth.oauth import build_google_authorize_url, exchange_google_code_for_userinfo
from config import settings
from dependencies.db import get_db
from errors import UnauthorizedError
from rate_limit import rate_limit
from repositories.oauth_identity import OAuthIdentityRepository
from repositories.user import UserRepository
from routers.auth import issue_tokens
from schemas.auth import TokenResponse

router = APIRouter(prefix="/auth/google", tags=["auth"])

_STATE_COOKIE_NAME = "oauth_state"
_STATE_COOKIE_MAX_AGE_SECONDS = 600


@router.get(
    "/login",
    dependencies=[Depends(rate_limit(key_prefix="google-login", limit=10, window_seconds=300))],
)
def google_login() -> Response:
    state = secrets.token_urlsafe(32)
    response = Response(status_code=302, headers={"Location": build_google_authorize_url(state)})
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
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(key_prefix="google-callback", limit=10, window_seconds=300))],
)
async def google_callback(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> TokenResponse:
    # Best-effort: only actually reaches the client on the success path
    # below — errors.py's AppError handler builds its own JSONResponse,
    # not this one, so a failed attempt leaves the cookie in place. Not a
    # real gap in practice: it's httponly, 10 minutes, and gets
    # overwritten by the next login attempt's fresh cookie anyway.
    response.delete_cookie(_STATE_COOKIE_NAME)
    cookie_state = request.cookies.get(_STATE_COOKIE_NAME)
    if cookie_state is None or not secrets.compare_digest(cookie_state, state):
        raise UnauthorizedError("Invalid or expired sign-in attempt.")

    google_user = await exchange_google_code_for_userinfo(code)
    if not google_user.email_verified:
        # Google itself is the thing vouching for this email — without
        # that, linking or creating an account off it would be trusting
        # an unverified claim, exactly what the rest of this app's email
        # verification flow exists to prevent.
        raise UnauthorizedError("Your Google account's email is not verified.")

    identity_repo = OAuthIdentityRepository(session)
    identity = await identity_repo.get_by_provider_and_subject(
        provider="google", provider_user_id=google_user.subject
    )

    user_repo = UserRepository(session)
    if identity is not None:
        user = await user_repo.get(identity.user_id)
        if user is None:
            raise UnauthorizedError("Invalid or expired sign-in attempt.")
    else:
        # Google verified this email, so it satisfies our own
        # is_email_verified requirement too — same reasoning a verify-
        # email link would, just from a provider we trust instead of our
        # own token.
        user = await user_repo.get_by_email(google_user.email)
        if user is None:
            user = await user_repo.create(
                email=google_user.email,
                full_name=google_user.full_name,
                hashed_password=None,
                is_email_verified=True,
            )
        elif not user.is_email_verified:
            user.is_email_verified = True

        await identity_repo.create(
            user_id=user.id,
            provider="google",
            provider_user_id=google_user.subject,
            email=google_user.email,
        )

    return await issue_tokens(session, user.id, request)
