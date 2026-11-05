import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.app.api.routes.auth import router as auth_router
from src.app.api.routes.health_check import router as health_check_router
from src.app.api.routes.requirement_interpretation import (
    router as requirement_interpretation_router,
)
from src.app.api.routes.welcome import router as welcome_router
from src.app.request_logging import log_requests
from src.clients.llm_provider import create_structured_llm_caller
from src.clients.supabase import create_supabase_client, create_supabase_db_client
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.services.auth.access_token import create_access_token_verifier
from src.services.deep_search.r1_run_coordinator import create_r1_run_coordinator
from src.services.deep_search.r1_run_store import R1RunStore
from src.services.deep_search.requirement_interpretation import (
    create_requirement_interpretation,
)

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Composition root: auth clients, then the shared LLM caller, R1, the run store and the
    coordinator, each built once and closed on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.supabase = create_supabase_client(settings)
    app.state.access_token_verifier = create_access_token_verifier(settings)

    llm_caller = None
    db_client = None
    app.state.r1_run_coordinator = None
    if settings.supabase_service_role_key:
        llm_caller = create_structured_llm_caller(settings)
        interpretation = create_requirement_interpretation(settings, llm_caller=llm_caller)
        db_client = await create_supabase_db_client(settings)
        app.state.r1_run_coordinator = create_r1_run_coordinator(
            interpretation, R1RunStore(db_client)
        )
    else:
        logging.getLogger(DEEP_SEARCH_LOGGER_NAME).warning(
            json.dumps(
                {
                    "event": "r1_runs.disabled",
                    "reason": "SUPABASE_SERVICE_ROLE_KEY is not set",
                }
            )
        )
    try:
        yield
    finally:
        if llm_caller is not None:
            await llm_caller.aclose()
        if db_client is not None:
            await db_client.postgrest.aclose()


# Swagger groups endpoints by tag, in the order listed here.
OPENAPI_TAGS = [
    {"name": "Health", "description": "Service liveness check."},
    {"name": "Auth", "description": "Login and token refresh."},
    {"name": "User", "description": "Endpoints for the signed-in user."},
    {
        "name": "Requirement Interpretation (R1)",
        "description": "Start, answer clarifications for, retry and fetch R1 runs.",
    },
]

app = FastAPI(title="HomeScout Auth", lifespan=lifespan, openapi_tags=OPENAPI_TAGS)
app.middleware("http")(log_requests)
app.include_router(health_check_router, tags=["Health"])
app.include_router(auth_router, tags=["Auth"])
app.include_router(welcome_router, tags=["User"])
app.include_router(
    requirement_interpretation_router, tags=["Requirement Interpretation (R1)"]
)


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
