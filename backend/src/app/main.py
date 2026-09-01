from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.app.api.routes.auth import router as auth_router
from src.app.api.routes.health_check import router as health_check_router
from src.app.api.routes.welcome import router as welcome_router
from src.clients.supabase import create_supabase_client
from src.core.config import get_settings
from src.core.logging import configure_logging
from src.services.auth.access_token import create_access_token_verifier

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.supabase = create_supabase_client(settings)
    app.state.access_token_verifier = create_access_token_verifier(settings)
    yield


app = FastAPI(title="HomeScout Auth", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(health_check_router)
app.include_router(welcome_router)


@app.exception_handler(HTTPException)
async def flatten_error_body(_request: Request, exc: HTTPException) -> JSONResponse:
    """Keep auth 401s as {"error": "..."} to match the login JSON contract."""
    content = (
        exc.detail
        if isinstance(exc.detail, dict) and "error" in exc.detail
        else {"detail": exc.detail}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=dict(exc.headers) if exc.headers else None,
    )
