"""Auth endpoints. Declarations only: each one maps to its controller function."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from supabase import Client

from src.app.api.controllers import auth as controllers
from src.app.api.dependencies.supabase import get_supabase_client
from src.schemas.login import LoginRequest

router = APIRouter()


@router.post("/api/auth/login")
async def login(
    request: LoginRequest,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    return await controllers.login(request, supabase)


@router.post("/auth/refresh")
async def refresh(
    request: Request,
    supabase: Client = Depends(get_supabase_client),
) -> JSONResponse:
    """Exchange the path-scoped refresh cookie for rotated session cookies."""
    return await controllers.refresh(request, supabase)
