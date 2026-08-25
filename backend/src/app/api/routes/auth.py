import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from supabase import Client

from src.app.api.dependencies.supabase import get_supabase_client
from src.schemas.login import LoginError, LoginRequest, LoginResponse
from src.services.auth.login import (
    ACCESS_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_MAX_AGE,
    IssuedIdentity,
    LoginOutcome,
    authenticate,
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
    result = authenticate(
        supabase,
        request.email,
        request.password,
        request.captcha_token,
    )

    if result.outcome == LoginOutcome.SUCCESS and result.identity is not None:
        identity = result.identity
        response = JSONResponse(
            content=LoginResponse(
                message=result.message or "",
                user_id=identity.user_id,
                user_name=identity.user_name,
            ).model_dump(),
            status_code=200,
        )
        _apply_session_cookies(response, identity)
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
