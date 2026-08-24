import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from supabase import Client

from src.app.api.dependencies.supabase import get_access_token_verifier, get_supabase_client
from src.schemas.auth_cookie import CookieReceiveStatus, CookieSendStatus
from src.schemas.login import LoginError, LoginRequest, LoginResponse
from src.schemas.token_check import TokenCheckResponse
from src.services.auth.access_token import AccessTokenVerifier, TokenVerificationError
from src.services.auth.login import (
    ACCESS_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_MAX_AGE,
    IssuedIdentity,
    LoginOutcome,
    authenticate,
    describe_cookie_send,
    inspect_received_access_token,
)

router = APIRouter()
logger = logging.getLogger("homescout.auth")


def _apply_session_cookies(response: Response, identity: IssuedIdentity) -> None:
    access = ACCESS_TOKEN_COOKIE_POLICY
    refresh = REFRESH_TOKEN_COOKIE_POLICY
    response.set_cookie(
        key=access.name,
        value=identity.access_token,
        httponly=access.httponly,
        secure=access.secure,
        samesite=access.samesite,
        path=access.path,
        max_age=identity.expires_in,
    )
    response.set_cookie(
        key=refresh.name,
        value=identity.refresh_token,
        httponly=refresh.httponly,
        secure=refresh.secure,
        samesite=refresh.samesite,
        path=refresh.path,
        max_age=REFRESH_TOKEN_MAX_AGE,
    )
    logger.info(
        "session cookies sent access_name=%s refresh_name=%s http_only=%s secure=%s same_site=%s access_path=%s refresh_path=%s",
        access.name,
        refresh.name,
        access.httponly,
        access.secure,
        access.samesite,
        access.path,
        refresh.path,
    )


@router.post("/api/auth/login")
async def login(
    request: LoginRequest,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    result = authenticate(supabase, request.email, request.password)

    if result.outcome == LoginOutcome.SUCCESS and result.identity is not None:
        cookie_status = CookieSendStatus.model_validate(describe_cookie_send())
        response = JSONResponse(
            content=LoginResponse(
                message=result.message or "",
                cookie=cookie_status,
            ).model_dump(),
            status_code=200,
        )
        _apply_session_cookies(response, result.identity)
        return response

    if result.outcome == LoginOutcome.RATE_LIMITED:
        return JSONResponse(
            content=LoginError(error=result.error or "").model_dump(),
            status_code=429,
        )

    return JSONResponse(
        content=LoginError(error=result.error or "").model_dump(),
        status_code=401,
    )


@router.get("/api/auth/session")
async def session_status(
    request: Request,
    verifier: AccessTokenVerifier = Depends(get_access_token_verifier),
) -> CookieReceiveStatus:
    """Probe whether the HttpOnly cookie was stored and is locally verifiable."""
    receipt = inspect_received_access_token(
        request.cookies.get(ACCESS_TOKEN_COOKIE_POLICY.name),
        verifier,
    )
    logger.info(
        "access_token cookie received present=%s matches_expected=%s name=%s",
        receipt.present,
        receipt.matches_expected,
        receipt.name,
    )
    return CookieReceiveStatus(
        present=receipt.present,
        matches_expected=receipt.matches_expected,
        name=receipt.name,
    )


@router.get("/api/auth/token-check")
async def token_check(
    request: Request,
    verifier: AccessTokenVerifier = Depends(get_access_token_verifier),
) -> TokenCheckResponse:
    """Diagnostic: verify the access-token cookie locally. Not an auth guard."""
    token = request.cookies.get(ACCESS_TOKEN_COOKIE_POLICY.name)
    if not token:
        return TokenCheckResponse(checkable=False, audience_matched=False)

    try:
        verified = verifier.verify(token)
    except TokenVerificationError:
        return TokenCheckResponse(checkable=False, audience_matched=False)

    return TokenCheckResponse(
        checkable=True,
        algorithm=verified.algorithm,
        audience_matched=verified.audience_matched,
    )


