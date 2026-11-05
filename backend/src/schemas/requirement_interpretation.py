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
    status: Literal["needs_answers", "finished", "failed"]
    questions: list[ClarificationQuestion] | None = None
    result: list[CategoryMetricPlan] | None = None
    retryable: bool | None = None


class RunErrorResponse(BaseModel):
    error: str
    run_id: str | None = None
    status: Literal["needs_answers", "finished", "failed"] | None = None
    retryable: bool | None = None
