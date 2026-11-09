"""What happens when an R1 run endpoint is called: call the coordinator, build the HTTP response.

The run rules (status, failure, retry) live in the coordinator; these functions only translate
its views and typed errors into status codes and bodies. Every failed body carries `retryable`.
"""

from uuid import UUID

from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.exceptions.deep_search import (
    ClarificationAnswerError,
    InputTooShortError,
    R1RunFailedError,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    UnsupportedLanguageError,
)
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.requirement_interpretation import (
    ClarificationAnswersRequest,
    RunErrorResponse,
    RunResponse,
    StartRunRequest,
)
from src.services.deep_search.feature_schemas.schemas import R1RunView
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator


async def start_run(
    body: StartRunRequest,
    user: AuthenticatedUser,
    coordinator: R1RunCoordinator,
) -> JSONResponse:
    """201 with questions (needs_answers) or result (finished)."""
    try:
        view = await coordinator.start_run(user.user_id, body.requirements)
    except Exception as exc:
        return _error_response(exc)
    return _run_response(view, status.HTTP_201_CREATED)


async def submit_answers(
    run_id: UUID,
    body: ClarificationAnswersRequest,
    user: AuthenticatedUser,
    coordinator: R1RunCoordinator,
) -> JSONResponse:
    """200 with result once R1 finishes from the saved state."""
    try:
        view = await coordinator.submit_answers(user.user_id, str(run_id), body.answers)
    except Exception as exc:
        return _error_response(exc)
    return _run_response(view, status.HTTP_200_OK)


async def retry_run(
    run_id: UUID,
    user: AuthenticatedUser,
    coordinator: R1RunCoordinator,
) -> JSONResponse:
    """200 with result; same shape as the clarification-answers endpoint."""
    try:
        view = await coordinator.retry_run(user.user_id, str(run_id))
    except Exception as exc:
        return _error_response(exc)
    return _run_response(view, status.HTTP_200_OK)


async def get_run(
    run_id: UUID,
    user: AuthenticatedUser,
    coordinator: R1RunCoordinator,
) -> JSONResponse:
    """200 with the run's status and its questions, result, or retryable flag."""
    try:
        view = await coordinator.get_run(user.user_id, str(run_id))
    except Exception as exc:
        return _error_response(exc)
    return _run_response(view, status.HTTP_200_OK)


def _run_response(view: R1RunView, status_code: int) -> JSONResponse:
    body = RunResponse(
        run_id=view.run_id,
        status=view.status,
        questions=view.questions,
        result=view.result,
        retryable=view.retryable,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body.model_dump(mode="json", exclude_none=True)),
    )


def _error_response(exc: Exception) -> JSONResponse:
    """Typed coordinator error -> status code and body. Anything else is re-raised (500)."""
    if isinstance(exc, (InputTooShortError, UnsupportedLanguageError, ClarificationAnswerError)):
        return _json(status.HTTP_422_UNPROCESSABLE_CONTENT, RunErrorResponse(error=str(exc)))
    if isinstance(exc, RunNotFoundError):
        return _json(status.HTTP_404_NOT_FOUND, RunErrorResponse(error="Run not found"))
    if isinstance(exc, RunConflictError):
        return _json(
            status.HTTP_409_CONFLICT,
            RunErrorResponse(
                error=str(exc), run_id=exc.run_id, status=exc.status, retryable=exc.retryable
            ),
        )
    if isinstance(exc, R1RunFailedError):
        if exc.unexpected:
            code = status.HTTP_500_INTERNAL_SERVER_ERROR
        elif exc.provider_unavailable:
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            code = status.HTTP_502_BAD_GATEWAY
        return _json(
            code,
            RunErrorResponse(
                error="Requirement interpretation failed",
                run_id=exc.run_id,
                status="failed",
                retryable=exc.retryable,
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
    # `retryable` is part of every failed body even when false.
    if body.status == "failed":
        content["retryable"] = bool(body.retryable)
    return JSONResponse(status_code=status_code, content=content)
