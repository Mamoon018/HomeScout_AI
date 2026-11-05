"""R1 run endpoints. Declarations only: each one maps to its controller function."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.app.api.controllers import requirement_interpretation as controllers
from src.app.api.dependencies.auth import get_authenticated_user
from src.app.api.dependencies.deep_search import get_r1_run_coordinator
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.requirement_interpretation import (
    ClarificationAnswersRequest,
    RunResponse,
    StartRunRequest,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator

router = APIRouter(
    prefix="/api/requirement-interpretation/runs",
    dependencies=[Depends(get_authenticated_user)],
)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RunResponse)
async def start_run_route(
    body: StartRunRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.start_run(body, user, coordinator)


@router.post("/{run_id}/clarification-answers", response_model=RunResponse)
async def submit_answers_route(
    run_id: UUID,
    body: ClarificationAnswersRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.submit_answers(run_id, body, user, coordinator)


@router.post("/{run_id}/retry", response_model=RunResponse)
async def retry_run_route(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.retry_run(run_id, user, coordinator)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_route(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    coordinator: R1RunCoordinator = Depends(get_r1_run_coordinator),
) -> JSONResponse:
    return await controllers.get_run(run_id, user, coordinator)
