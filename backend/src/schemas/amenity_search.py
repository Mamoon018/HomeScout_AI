from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.services.deep_search.feature_schemas.schemas import (
    DEFAULT_RADIUS_KM,
    PredefinedMetricsRecord,
)


class OriginRequest(BaseModel):
    """The search origin. Both values must be finite numbers (no NaN or infinity)."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(allow_inf_nan=False)
    longitude: float = Field(allow_inf_nan=False)


class StartAmenitySearchRequest(BaseModel):
    """Start R2 from a finished R1 run. `radius_km` defaults to 2 km."""

    model_config = ConfigDict(extra="forbid")

    r1_run_id: UUID
    origin: OriginRequest
    radius_km: float = Field(default=DEFAULT_RADIUS_KM, gt=0, allow_inf_nan=False)


class AmenitySearchRunResponse(BaseModel):
    """An R2 run as the page sees it. `completed_step` shows how far it got; `result` (the
    predefined records, keyed category_id then place_id) once finished; `retryable` when failed
    (Retry when true, Start again when false)."""

    run_id: str
    status: Literal["running", "finished", "failed"]
    completed_step: Literal["discovery"] | None = None
    result: dict[int, dict[str, PredefinedMetricsRecord]] | None = None
    retryable: bool | None = None
