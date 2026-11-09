"""R3 (Specific Metric Resolution) run endpoints. Declarations only: each maps to its controller.

Start and retry answer 202 at once; the run continues in a background task (it takes minutes) and
the page polls the status endpoint. `responses` lists only the statuses each controller path can
produce.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.app.api.controllers import specific_metric_resolution as controllers
from src.app.api.dependencies.auth import get_authenticated_user
from src.app.api.dependencies.deep_search import get_r3_run_coordinator
from src.app.api.routes.requirement_interpretation import _STORE_UNAVAILABLE, _UNAUTHENTICATED
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.requirement_interpretation import (
    RequestValidationErrorResponse,
    RunErrorResponse,
)
from src.schemas.specific_metric_resolution import (
    SpecificMetricResolutionRunResponse,
    StartSpecificMetricResolutionRequest,
)
from src.services.deep_search.r3_run_coordinator import R3RunCoordinator

_EXAMPLE_RUN_ID = "3e8a1f50-0000-4000-8000-000000000000"

_STORE_DOWN = {status.HTTP_503_SERVICE_UNAVAILABLE: _STORE_UNAVAILABLE}


def _not_found(description: str, error: str) -> dict[int | str, dict[str, Any]]:
    return {
        status.HTTP_404_NOT_FOUND: {
            "model": RunErrorResponse,
            "description": description,
            "content": {"application/json": {"example": {"error": error}}},
        },
    }


router = APIRouter(
    prefix="/api/specific-metric-resolution/runs",
    dependencies=[Depends(get_authenticated_user)],
    responses=_UNAUTHENTICATED,
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SpecificMetricResolutionRunResponse,
    description="Starts R3 for a finished R2 run. Replies 202 with `run_id` and `status: running` "
    "at once; poll `GET /{run_id}` every few seconds until it is `finished` or `failed` (a run "
    "takes minutes).",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": RequestValidationErrorResponse,
            "description": "`r2_run_id` is not a UUID, or the body carries other fields. No run "
            "is created.",
        },
        **_not_found(
            "No finished R2 run with this ID for the signed-in user (missing, another user's, not "
            "finished, or saved by another version). Run amenity search again.",
            "Finished amenity search run not found",
        ),
        **_STORE_DOWN,
    },
)
async def start_run_route(
    body: StartSpecificMetricResolutionRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R3RunCoordinator = Depends(get_r3_run_coordinator),
) -> JSONResponse:
    return await controllers.start_run(body, user, coordinator)


@router.post(
    "/{run_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SpecificMetricResolutionRunResponse,
    description="Resumes a failed (retryable) run, or a crashed run left `running` for over "
    "30 minutes, after its last saved step: once website discovery (STEP 3) is saved it is not "
    "run again. Replies 202 with `completed_step`; poll the status endpoint for the outcome. One "
    "retry per run.",
    responses={
        **_not_found("No run with this ID for the signed-in user.", "Run not found"),
        status.HTTP_409_CONFLICT: {
            "model": RunErrorResponse,
            "description": "The run has finished, cannot be retried (`retryable` false or its one "
            "retry is used), is still running, another retry already started, its step record "
            "changed, or it was saved by another version (start again). The body carries the "
            "run's `status`, and `retryable` when that status is `failed`.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "The run cannot be retried",
                        "run_id": _EXAMPLE_RUN_ID,
                        "status": "failed",
                        "retryable": False,
                    }
                }
            },
        },
        **_STORE_DOWN,
    },
)
async def retry_run_route(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R3RunCoordinator = Depends(get_r3_run_coordinator),
) -> JSONResponse:
    return await controllers.retry_run(run_id, user, coordinator)


@router.get(
    "/{run_id}",
    response_model=SpecificMetricResolutionRunResponse,
    description="Read-only. `running` while the run works (answered from memory while its task "
    "is live; `completed_step` becomes `discovery_batch` once the websites are found), "
    "`finished` with `result` (one row per amenity), or `failed` with `retryable`. A run saved "
    "by another version reads as `failed`, not retryable.",
    responses={
        **_not_found("No run with this ID for the signed-in user.", "Run not found"),
        **_STORE_DOWN,
    },
)
async def get_run_route(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R3RunCoordinator = Depends(get_r3_run_coordinator),
) -> JSONResponse:
    return await controllers.get_run(run_id, user, coordinator)
