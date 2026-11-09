import asyncio
import functools
import json
import logging
import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.app.api.routes.amenity_search import router as amenity_search_router
from src.app.api.routes.auth import router as auth_router
from src.app.api.routes.health_check import router as health_check_router
from src.app.api.routes.specific_metric_resolution import (
    router as specific_metric_resolution_router,
)
from src.app.api.routes.requirement_interpretation import (
    router as requirement_interpretation_router,
)
from src.app.api.routes.welcome import router as welcome_router
from src.app.request_logging import log_requests
from src.clients.google_places import create_places_async_client
from src.clients.google_routes import create_routes_async_client
from src.clients.llm_provider import create_structured_llm_caller
from src.clients.mcp_tools import create_mcp_provider_limits
from src.clients.supabase import create_supabase_client, create_supabase_db_client
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.services.auth.access_token import create_access_token_verifier
from src.services.deep_search.amenity_search import GLOBAL_PLACES_CONCURRENCY
from src.services.deep_search.r1_run_coordinator import create_r1_run_coordinator
from src.services.deep_search.r1_run_store import R1RunStore
from src.services.deep_search.r2_run_coordinator import R2RunCoordinator
from src.services.deep_search.r2_run_store import R2RunStore
from src.services.deep_search.r3_run_coordinator import R3RunCoordinator
from src.services.deep_search.r3_run_store import R3RunStore
from src.services.deep_search.requirement_interpretation import (
    create_requirement_interpretation,
)
from src.services.deep_search.specific_metric_resolution import (
    create_specific_metric_resolution,
)

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Composition root: auth clients, then the shared LLM caller, R1 and its coordinator, then
    R2's shared Google clients, global Places cap and coordinator, then R3's app-wide web-provider
    limits, per-run service factory and coordinator, each built once and closed on shutdown (live
    R2 and R3 tasks are cancelled before anything they use is closed)."""
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.supabase = create_supabase_client(settings)
    app.state.access_token_verifier = create_access_token_verifier(settings)

    llm_caller = None
    db_client = None
    places_client = None
    routes_client = None
    r2_coordinator: R2RunCoordinator | None = None
    r3_coordinator: R3RunCoordinator | None = None
    app.state.r1_run_coordinator = None
    app.state.r2_run_coordinator = None
    app.state.r2_tasks = None
    app.state.r3_run_coordinator = None
    app.state.r3_tasks = None
    if settings.supabase_service_role_key:
        llm_caller = create_structured_llm_caller(settings)
        interpretation = create_requirement_interpretation(settings, llm_caller=llm_caller)
        db_client = await create_supabase_db_client(settings)
        r1_store = R1RunStore(db_client)
        app.state.r1_run_coordinator = create_r1_run_coordinator(
            interpretation,
            r1_store,
            stale_after_seconds=settings.r1_stale_after_seconds,
        )
        # R2: the Places/Routes clients and one global Places cap are shared by every run; the
        # coordinator builds a new AmenitySearch per run from them (R2-C2 Iteration 1).
        places_client = create_places_async_client(settings)
        routes_client = create_routes_async_client(settings)
        r2_store = R2RunStore(db_client)
        r2_coordinator = R2RunCoordinator(
            r2_store,
            r1_store,
            places_client=places_client,
            routes_client=routes_client,
            global_places_semaphore=asyncio.Semaphore(GLOBAL_PLACES_CONCURRENCY),
            llm_caller=llm_caller,
            stale_after_seconds=settings.r2_stale_after_seconds,
            max_places_per_category=settings.max_places_per_category,
        )
        app.state.r2_run_coordinator = r2_coordinator
        app.state.r2_tasks = r2_coordinator.tasks
        # R3: one app-wide limit per web provider (Parallel slots, Firecrawl slots + rate), shared
        # by every run's gateway (R3-C2 Iteration 1). The coordinator calls the factory once per
        # run, so each run gets its own gateway (R3-C2) on the shared caller and limits.
        provider_limits = create_mcp_provider_limits(settings)
        r3_coordinator = R3RunCoordinator(
            R3RunStore(db_client),
            r2_store,
            service_factory=functools.partial(
                create_specific_metric_resolution,
                settings,
                llm_caller=llm_caller,
                provider_limits=provider_limits,
            ),
            stale_after_seconds=settings.r3_stale_after_seconds,
        )
        app.state.r3_run_coordinator = r3_coordinator
        app.state.r3_tasks = r3_coordinator.tasks
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
        # Live R2 and R3 tasks first: each saves itself as failed through the database and may
        # still be inside a Places, web or LLM call, so the clients, the shared caller and the
        # database close only after them. The two coordinators share no task, so they shut down
        # together.
        await asyncio.gather(
            *(
                coordinator.shutdown()
                for coordinator in (r2_coordinator, r3_coordinator)
                if coordinator is not None
            )
        )
        if places_client is not None:
            await places_client.aclose()
        if routes_client is not None:
            await routes_client.aclose()
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
    {
        "name": "Amenity Search (R2)",
        "description": "Start, retry and poll R2 runs (they run in the background; start and "
        "retry reply 202).",
    },
    {
        "name": "Specific Metric Resolution (R3)",
        "description": "Start, retry and poll R3 runs (they run in the background for minutes; "
        "start and retry reply 202).",
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
app.include_router(amenity_search_router, tags=["Amenity Search (R2)"])
app.include_router(
    specific_metric_resolution_router, tags=["Specific Metric Resolution (R3)"]
)


def _json_safe(value: object) -> object:
    """Replace NaN / infinity (which JSON cannot carry) with their text, recursively."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 body. A rejected NaN or infinite input (e.g. `1e999`) is echoed as text;
    the default handler fails to encode it and answers 500 instead of 422."""
    return JSONResponse(
        status_code=422,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
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
