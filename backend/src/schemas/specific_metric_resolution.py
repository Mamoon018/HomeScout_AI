from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StartSpecificMetricResolutionRequest(BaseModel):
    """Start R3 from a finished R2 run of the signed-in user."""

    model_config = ConfigDict(extra="forbid")

    r2_run_id: UUID


class ResolutionResultEntry(BaseModel):
    """One amenity's resolution record: the metric entries kept, the unresolved labels with their
    reason, and the evidence they were judged from (`value` is the record as plain JSON)."""

    category_id: int
    place_id: str
    value: dict[str, Any]


class SpecificMetricResolutionRunResponse(BaseModel):
    """An R3 run as the page sees it. `completed_step` is `discovery_batch` once the websites are
    found ("resolving metrics"); `result` (one row per amenity) once finished; `retryable` when
    failed (Retry when true, Start again when false)."""

    run_id: str
    status: Literal["running", "finished", "failed"]
    completed_step: Literal["discovery_batch"] | None = None
    result: list[ResolutionResultEntry] | None = None
    retryable: bool | None = None
