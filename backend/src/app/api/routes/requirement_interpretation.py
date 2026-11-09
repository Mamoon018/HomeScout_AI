"""R1 run endpoints. Declarations only: each one maps to its controller function.

`responses` documents the error bodies the controller can return, so Swagger shows them next to
the success model. Each route lists only the statuses its controller path can produce.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.app.api.controllers import requirement_interpretation as controllers
from src.app.api.dependencies.auth import get_authenticated_user
from src.app.api.dependencies.deep_search import get_r1_run_coordinator
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.login import LoginError
from src.schemas.requirement_interpretation import (
    ClarificationAnswersRequest,
    RequestValidationErrorResponse,
    RunErrorResponse,
    RunResponse,
    StartRunRequest,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator

_UNAUTHENTICATED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": LoginError,
        "description": "Missing, invalid or expired access-token cookie. "
        "`code` is `token_expired` when the page should call /auth/refresh.",
        "content": {
            "application/json": {
                "examples": {
                    "not_authenticated": {"value": {"error": "Not authenticated"}},
                    "token_expired": {
                        "value": {"error": "Not authenticated", "code": "token_expired"}
                    },
                }
            }
        },
    },
}

_NOT_FOUND = {
    status.HTTP_404_NOT_FOUND: {
        "model": RunErrorResponse,
        "description": "No run with this ID for the signed-in user.",
        "content": {"application/json": {"example": {"error": "Run not found"}}},
    },
}

_STORE_UNAVAILABLE = {
    "model": RunErrorResponse,
    "description": "The run database could not be reached.",
    "content": {"application/json": {"example": {"error": "Run storage is unavailable"}}},
}


_RETRY_NOTES = {
    "start": "`retryable` is true on the first failure of an LLM step: the requirements and "
    "every finished step are saved, so the page can offer Retry.",
    "answers": "`retryable` is true on the first failure of an LLM step "
    "(the page can offer Retry).",
    "retry": "`retryable` is always false here: the one allowed retry is used, so start a new run.",
}


def _run_failed(endpoint: str) -> dict[int | str, dict[str, Any]]:
    """502 / 503 / 500 when R1 itself fails. The run is saved as `failed`."""
    retry_note = _RETRY_NOTES[endpoint]
    retryable_possible = endpoint in ("start", "answers")
    example = {
        "error": "Requirement interpretation failed",
        "run_id": "3f2b8c1e-0000-4000-8000-000000000000",
        "status": "failed",
        "retryable": retryable_possible,
    }
    return {
        status.HTTP_502_BAD_GATEWAY: {
            "model": RunErrorResponse,
            "description": "R1 failed at one of its stages (for example the model returned "
            f"an unusable body). {retry_note}",
            "content": {"application/json": {"example": example}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": RunErrorResponse,
            "description": "R1's model provider is unavailable "
            f"(body as for 502; {retry_note[0].lower() + retry_note[1:]}), "
            "or the run database could not be reached (body has only `error`).",
            "content": {
                "application/json": {
                    "examples": {
                        "provider_unavailable": {"value": example},
                        "store_unavailable": {
                            "value": {"error": "Run storage is unavailable"}
                        },
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": RunErrorResponse,
            "description": "Unexpected server error during R1. The run is saved as `failed` "
            "with `retryable` false.",
            "content": {"application/json": {"example": {**example, "retryable": False}}},
        },
    }


def _conflict(description: str) -> dict[int | str, dict[str, Any]]:
    return {
        status.HTTP_409_CONFLICT: {
            "model": RunErrorResponse,
            "description": f"{description} The body carries the run's current `status`, "
            "and `retryable` when that status is `failed`.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "The run cannot be retried",
                        "run_id": "3f2b8c1e-0000-4000-8000-000000000000",
                        "status": "failed",
                        "retryable": False,
                    }
                }
            },
        },
    }


def _unprocessable(description: str) -> dict[int | str, dict[str, Any]]:
    """Our own 422 (`error`) or FastAPI's schema-validation 422 (`detail`)."""
    return {
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": RunErrorResponse | RequestValidationErrorResponse,
            "description": f"{description} A request that does not match the schema gets "
            "FastAPI's `detail` list instead.",
        },
    }


router = APIRouter(
    prefix="/api/requirement-interpretation/runs",
    dependencies=[Depends(get_authenticated_user)],
    responses=_UNAUTHENTICATED,
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RunResponse,
    responses={
        **_unprocessable("The requirements are too short or not in a supported language."),
        **_run_failed("start"),
    },
)
async def start_run_route(
    body: StartRunRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.start_run(body, user, coordinator)


@router.post(
    "/{run_id}/clarification-answers",
    response_model=RunResponse,
    responses={
        **_NOT_FOUND,
        **_conflict(
            "The run is not waiting for answers, it changed while the answers were being "
            "saved, or it was saved by an older version (start again)."
        ),
        **_unprocessable("The answers do not match the run's questions."),
        **_run_failed("answers"),
    },
)
async def submit_answers_route(
    run_id: UUID,
    body: ClarificationAnswersRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.submit_answers(run_id, body, user, coordinator)


@router.post(
    "/{run_id}/retry",
    response_model=RunResponse,
    description="Resumes a failed run at its failed step; finished steps are not called again. "
    "The reply carries `result` when the run finishes, or `questions` when the failed step was "
    "question generation (the run then waits for answers).",
    responses={
        **_NOT_FOUND,
        **_conflict(
            "The run has not failed, it cannot be retried (`retryable` false or the one "
            "retry is used), another retry already started, it was cut off while running, "
            "or it was saved by an older version (start again)."
        ),
        **_run_failed("retry"),
    },
)
async def retry_run_route(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.retry_run(run_id, user, coordinator)


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    description="Read-only. `status` is `running` while a request is still working on the run; "
    "a run left `running` for over 3 minutes (cut off) reads as `failed` with `retryable` false.",
    responses={
        **_NOT_FOUND,
        status.HTTP_503_SERVICE_UNAVAILABLE: _STORE_UNAVAILABLE,
    },
)
async def get_run_route(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.get_run(run_id, user, coordinator)
