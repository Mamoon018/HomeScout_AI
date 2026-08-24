import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.schemas.auth_cookie import CookieReceiveStatus, CookieSendStatus
from src.schemas.login import LoginError, LoginRequest, LoginResponse
from src.services.auth.login import (
    ACCESS_TOKEN_COOKIE_POLICY,
    LoginOutcome,
    authenticate,
    describe_cookie_send,
    inspect_received_access_token,
)

router = APIRouter()
logger = logging.getLogger("homescout.auth")


def _apply_access_token_cookie(response: Response) -> None:
    policy = ACCESS_TOKEN_COOKIE_POLICY
    response.set_cookie(
        key=policy.name,
        value=get_settings().access_token,
        httponly=policy.httponly,
        secure=policy.secure,
        samesite=policy.samesite,
        path=policy.path,
    )
    logger.info(
        "access_token cookie sent name=%s http_only=%s secure=%s same_site=%s path=%s",
        policy.name,
        policy.httponly,
        policy.secure,
        policy.samesite,
        policy.path,
    )


@router.post("/api/auth/login")
async def login(request: LoginRequest) -> JSONResponse:
    result = authenticate(request.email, request.password)

    if result.outcome == LoginOutcome.SUCCESS:
        cookie_status = CookieSendStatus.model_validate(describe_cookie_send())
        response = JSONResponse(
            content=LoginResponse(
                message=result.message or "",
                cookie=cookie_status,
            ).model_dump(),
            status_code=200,
        )
        _apply_access_token_cookie(response)
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
async def session_status(request: Request) -> CookieReceiveStatus:
    """Probe whether the HttpOnly cookie was stored and sent back on this origin."""
    receipt = inspect_received_access_token(
        request.cookies.get(ACCESS_TOKEN_COOKIE_POLICY.name)
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
