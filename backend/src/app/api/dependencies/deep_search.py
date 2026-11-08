from fastapi import HTTPException, Request, status

from src.schemas.requirement_interpretation import RunErrorResponse
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator
from src.services.deep_search.r2_run_coordinator import R2RunCoordinator

R1_RUNS_UNAVAILABLE_BODY = RunErrorResponse(
    error="Requirement interpretation is not available"
).model_dump(exclude_none=True)

R2_RUNS_UNAVAILABLE_BODY = RunErrorResponse(error="Amenity search is not available").model_dump(
    exclude_none=True
)


def get_r1_run_coordinator(request: Request) -> R1RunCoordinator:
    """The coordinator built at startup. 503 when the app started without the service-role key."""
    coordinator = getattr(request.app.state, "r1_run_coordinator", None)
    if coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=R1_RUNS_UNAVAILABLE_BODY,
        )
    return coordinator


def get_r2_run_coordinator(request: Request) -> R2RunCoordinator:
    """The R2 coordinator built at startup. 503 when the app started without the service-role key."""
    coordinator = getattr(request.app.state, "r2_run_coordinator", None)
    if coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=R2_RUNS_UNAVAILABLE_BODY,
        )
    return coordinator
