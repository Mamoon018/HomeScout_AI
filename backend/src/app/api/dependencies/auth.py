import logging
from typing import NoReturn

from fastapi import Depends, HTTPException, Request, status

from src.app.api.dependencies.supabase import get_access_token_verifier
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.login import LoginError
from src.services.auth.access_token import AccessTokenVerifier, TokenVerificationError
from src.services.auth.login import ACCESS_TOKEN_COOKIE_POLICY

logger = logging.getLogger("homescout.auth")

UNAUTHENTICATED_BODY = LoginError(error="Not authenticated").model_dump()


def _reject_unauthenticated(reason: str) -> NoReturn:
    logger.info("identity rejected reason=%s", reason)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHENTICATED_BODY,
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
    except TokenVerificationError as exc:
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
