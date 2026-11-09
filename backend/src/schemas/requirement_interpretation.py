from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.services.deep_search.feature_schemas.schemas import (
    CategoryMetricPlan,
    ClarificationAnswer,
    ClarificationQuestion,
)


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: str


class ClarificationAnswersRequest(BaseModel):
    """One answer per question: the option number (1-5), plus a description for 'other'."""

    model_config = ConfigDict(extra="forbid")

    answers: list[ClarificationAnswer]


class RunResponse(BaseModel):
    """The run as the page sees it. `questions` while paused, `result` once finished,
    `retryable` when failed (Retry when true, Start again when false)."""

    run_id: str
    status: Literal["running", "needs_answers", "finished", "failed"]
    questions: list[ClarificationQuestion] | None = None
    result: list[CategoryMetricPlan] | None = None
    retryable: bool | None = None


class RunErrorResponse(BaseModel):
    """A run endpoint's error body. `run_id`, `status` and `retryable` are present when the error
    belongs to a known run; `retryable` is always present when `status` is `failed`."""

    error: str
    run_id: str | None = None
    status: Literal["running", "needs_answers", "finished", "failed"] | None = None
    retryable: bool | None = None


class RequestValidationErrorItem(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class RequestValidationErrorResponse(BaseModel):
    """FastAPI's body for a request that fails schema validation (wrong or missing fields)."""

    detail: list[RequestValidationErrorItem]
