import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from supabase import Client

from src.app.api.dependencies.supabase import get_supabase_client
from src.core.config import get_settings
from src.schemas.login import LoginError, LoginRequest, LoginResponse
from src.schemas.refresh import RefreshResponse
from src.services.auth.login import LoginOutcome, authenticate
from src.services.auth.refresh import RefreshOutcome, refresh_session
from src.services.auth.session_cookies import (
    REFRESH_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_MAX_AGE,
    apply_session_cookies,
    clear_session_cookies,
)

router = APIRouter()
logger = logging.getLogger("homescout.auth")


@router.post("/api/auth/login")
async def login(
    request: LoginRequest,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    settings = get_settings()
    result = authenticate(
        supabase,
        request.email,
        request.password,
        request.captcha_token,
        captcha_required=settings.captcha_enabled,
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
        apply_session_cookies(response, identity)
        logger.info(
            "login succeeded user_id=%s jwt_expires_in=%s access_cookie_max_age=%s",
            identity.user_id,
            identity.expires_in,
            REFRESH_TOKEN_MAX_AGE,
        )
        return response

    if result.outcome == LoginOutcome.RATE_LIMITED:
        return JSONResponse(
            content=LoginError(error=result.error or "").model_dump(exclude_none=True),
            status_code=429,
        )

    return JSONResponse(
        content=LoginError(error=result.error or "").model_dump(exclude_none=True),
        status_code=401,
    )


@router.post("/auth/refresh")
async def refresh(
    request: Request,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    """Exchange the path-scoped refresh cookie for rotated session cookies."""
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE_POLICY.name)
    result = refresh_session(supabase, refresh_token)

    if result.outcome == RefreshOutcome.SUCCESS and result.identity is not None:
        response = JSONResponse(
            content=RefreshResponse(message="Session refreshed").model_dump(),
            status_code=200,
        )
        apply_session_cookies(response, result.identity)
        return response

    response = JSONResponse(
        content=LoginError(error=result.error or "Not authenticated").model_dump(exclude_none=True),
        status_code=401,
    )
    clear_session_cookies(response)
    return response
