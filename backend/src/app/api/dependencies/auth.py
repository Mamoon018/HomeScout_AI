import logging
from typing import NoReturn

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import InvalidTokenError

from src.app.api.dependencies.supabase import get_access_token_verifier
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.login import LoginError
from src.services.auth.access_token import (
    AccessTokenVerifier,
    TokenExpiredError,
    TokenVerificationError,
)
from src.services.auth.session_cookies import ACCESS_TOKEN_COOKIE_POLICY

logger = logging.getLogger("homescout.auth")

UNAUTHENTICATED_BODY = LoginError(error="Not authenticated").model_dump(exclude_none=True)
TOKEN_EXPIRED_BODY = LoginError(
    error="Not authenticated", code="token_expired"
).model_dump(exclude_none=True)


def _reject_unauthenticated(reason: str) -> NoReturn:
    logger.info("identity rejected reason=%s", reason)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHENTICATED_BODY,
    )


def _log_verification_failure(token: str, exc: TokenVerificationError) -> None:
    detail = str(exc)
    claims_summary = "unavailable"
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        if isinstance(claims, dict):
            claims_summary = (
                f"iss={claims.get('iss')!r} aud={claims.get('aud')!r} "
                f"sub={claims.get('sub')!r} exp={claims.get('exp')!r}"
            )
    except InvalidTokenError:
        claims_summary = "unparseable"

    logger.info(
        "token verification failed detail=%s claims=%s token_len=%s",
        detail,
        claims_summary,
        len(token),
    )


def _reject_token_expired() -> NoReturn:
    logger.info("identity rejected reason=token_expired")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=TOKEN_EXPIRED_BODY,
    )


def get_authenticated_user(
    request: Request,
    verifier: AccessTokenVerifier = Depends(get_access_token_verifier),
) -> AuthenticatedUser:
    """Extract the access-token cookie, verify it, and attach a typed identity."""
    token = request.cookies.get(ACCESS_TOKEN_COOKIE_POLICY.name)
    if not token or not token.strip():
        _reject_unauthenticated("missing_cookie")

    try:
        verified = verifier.verify(token)
    except TokenExpiredError:
        _reject_token_expired()
    except TokenVerificationError as exc:
        _log_verification_failure(token, exc)
        _reject_unauthenticated(str(exc))

    if not verified.email or not verified.user_name:
        _reject_unauthenticated("incomplete_claims")

    logger.debug(
        "token verified algorithm=%s subject=%s email=%s user_name=%s audience_matched=%s",
        verified.algorithm,
        verified.subject,
        verified.email,
        verified.user_name,
        verified.audience_matched,
    )

    return AuthenticatedUser(
        user_id=verified.subject,
        email=verified.email,
        user_name=verified.user_name,
    )
