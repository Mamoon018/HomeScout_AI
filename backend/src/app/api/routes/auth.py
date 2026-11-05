"""Auth endpoints. Declarations only: each one maps to its controller function.

`response_model` and `responses` only document the bodies for Swagger; the controllers build
the actual responses (and set the session cookies) themselves.
"""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from supabase import Client

from src.app.api.controllers import auth as controllers
from src.app.api.dependencies.supabase import get_supabase_client
from src.schemas.login import LoginError, LoginRequest, LoginResponse
from src.schemas.refresh import RefreshResponse

router = APIRouter()

_SESSION_COOKIES_NOTE = (
    "Also sets two HttpOnly, Secure, SameSite=Strict cookies: `access_token` (path `/`) and "
    "`refresh_token` (path `/auth/refresh`)."
)


@router.post(
    "/api/auth/login",
    response_model=LoginResponse,
    response_description=f"Signed in. {_SESSION_COOKIES_NOTE} `user_name` is null when the "
    "account has no full name.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": LoginError,
            "description": "Wrong email or password, any other sign-in error from Supabase, "
            "or a missing or failed captcha when captcha is enabled. No cookies are set.",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_credentials": {"value": {"error": "Invalid email or password"}},
                        "captcha_required": {
                            "value": {
                                "error": "Please complete the captcha challenge and try again."
                            }
                        },
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": LoginError,
            "description": "Five failed attempts for this email. The count resets on a "
            "successful login or a server restart.",
            "content": {
                "application/json": {
                    "example": {"error": "Too many login attempts. Please try again later."}
                }
            },
        },
    },
)
async def login(
    request: LoginRequest,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    return await controllers.login(request, supabase)


@router.post(
    "/auth/refresh",
    response_model=RefreshResponse,
    response_description=f"Session refreshed. {_SESSION_COOKIES_NOTE} Both are rotated.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": LoginError,
            "description": "The `refresh_token` cookie is missing, invalid or expired. Both "
            "session cookies are cleared, so the page should send the user to login.",
            "content": {"application/json": {"example": {"error": "Not authenticated"}}},
        },
    },
)
async def refresh(
    request: Request,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    """Exchange the path-scoped refresh cookie for rotated session cookies."""
    return await controllers.refresh(request, supabase)
