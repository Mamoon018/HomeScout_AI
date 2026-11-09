"""What happens when an R3 run endpoint is called: call the coordinator, build the HTTP response.

The run rules (status, fence, claim, retryable) live in the coordinator; these functions only
translate its views and typed errors into status codes and bodies. Run failures happen after the
202, in the background task, so they are reported by the status endpoint, not here.
"""

from uuid import UUID

from fastapi import status
from fastapi.responses import JSONResponse

from src.exceptions.deep_search import RunConflictError, RunNotFoundError, RunStoreError
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.requirement_interpretation import RunErrorResponse
from src.schemas.specific_metric_resolution import (
    SpecificMetricResolutionRunResponse,
    StartSpecificMetricResolutionRequest,
)
from src.services.deep_search.feature_schemas.schemas import R3RunView
from src.services.deep_search.r3_run_coordinator import R3RunCoordinator

_R2_NOT_FOUND = "Finished amenity search run not found"
_RUN_NOT_FOUND = "Run not found"


async def start_run(
    body: StartSpecificMetricResolutionRequest,
    user: AuthenticatedUser,
    coordinator: R3RunCoordinator,
) -> JSONResponse:
    """202 with the new run_id; the run continues in the background."""
    try:
        view = await coordinator.start_run(user.user_id, str(body.r2_run_id))
    except Exception as exc:
        return _error_response(exc, not_found=_R2_NOT_FOUND)
    return _run_response(view, status.HTTP_202_ACCEPTED)


async def retry_run(
    run_id: UUID,
    user: AuthenticatedUser,
    coordinator: R3RunCoordinator,
) -> JSONResponse:
    """202 with `completed_step`; the resumed run continues in the background."""
    try:
        view = await coordinator.retry_run(user.user_id, str(run_id))
    except Exception as exc:
        return _error_response(exc, not_found=_RUN_NOT_FOUND)
    return _run_response(view, status.HTTP_202_ACCEPTED)


async def get_run(
    run_id: UUID,
    user: AuthenticatedUser,
    coordinator: R3RunCoordinator,
) -> JSONResponse:
    """200 with the run's status and its result or retryable flag."""
    try:
        view = await coordinator.get_run(user.user_id, str(run_id))
    except Exception as exc:
        return _error_response(exc, not_found=_RUN_NOT_FOUND)
    return _run_response(view, status.HTTP_200_OK)


def _run_response(view: R3RunView, status_code: int) -> JSONResponse:
    # `view.result` is already plain JSON (the store codec wrote it), so it is validated into the
    # response model as data, never re-encoded from R3's objects.
    body = SpecificMetricResolutionRunResponse(
        run_id=view.run_id,
        status=view.status,
        completed_step=view.completed_step,
        result=view.result,
        retryable=view.retryable,
    )
    content = body.model_dump(mode="json", exclude_none=True)
    # `retryable` is part of every failed body even when false.
    if view.status == "failed":
        content["retryable"] = bool(view.retryable)
    return JSONResponse(status_code=status_code, content=content)


def _error_response(exc: Exception, *, not_found: str) -> JSONResponse:
    """Typed coordinator error -> status code and body. Anything else is re-raised (500)."""
    if isinstance(exc, RunNotFoundError):
        return _json(status.HTTP_404_NOT_FOUND, RunErrorResponse(error=not_found))
    if isinstance(exc, RunConflictError):
        return _json(
            status.HTTP_409_CONFLICT,
            RunErrorResponse(
                error=str(exc), run_id=exc.run_id, status=exc.status, retryable=exc.retryable
            ),
        )
    if isinstance(exc, RunStoreError):
        return _json(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            RunErrorResponse(error="Run storage is unavailable"),
        )
    raise exc


def _json(status_code: int, body: RunErrorResponse) -> JSONResponse:
    content = body.model_dump(exclude_none=True)
    if body.status == "failed":
        content["retryable"] = bool(body.retryable)
    return JSONResponse(status_code=status_code, content=content)
