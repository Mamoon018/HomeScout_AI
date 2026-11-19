from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StartSpecificMetricResolutionRequest(BaseModel):
    """Start R3 from a finished R2 run of the signed-in user."""

    model_config = ConfigDict(extra="forbid")

    r2_run_id: UUID


class PlaceWebsite(BaseModel):
    """The place's official website as found by website discovery (STEP 3). Always sent:
    `url` is null and `origin` is `none` when no official site was confirmed."""

    url: str | None
    origin: Literal["google", "discovered", "none"]


class ResolutionResultEntry(BaseModel):
    """One amenity's row: its website verdict (`website`, from STEP 3) and its resolution record
    (`value`: the metric entries kept, the unresolved labels with their reason, and the evidence
    they were judged from, as plain JSON). A place under two categories is two rows."""

    category_id: int
    place_id: str
    website: PlaceWebsite
    value: dict[str, Any]


class SpecificMetricResolutionRunResponse(BaseModel):
    """An R3 run as the page sees it. `r2_run_id` is the R2 run it started from (the page reads
    that run's places by this id); `completed_step` is `discovery_batch` once the websites are
    found ("resolving metrics"); `result` (one row per amenity) once finished; `retryable` when
    failed (Retry when true, Start again when false)."""

    run_id: str
    r2_run_id: str | None = None
    status: Literal["running", "finished", "failed"]
    completed_step: Literal["discovery_batch"] | None = None
    result: list[ResolutionResultEntry] | None = None
    retryable: bool | None = None
