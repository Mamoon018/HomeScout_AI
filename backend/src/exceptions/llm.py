from typing import Literal

# Why one provider failed (R3.M1.4 step 1 prerequisite). `availability`: the request could not be
# served (timeout, 429, 5xx, connection, credentials, a rejected request, any other SDK/API error).
# `content`: the provider answered but the answer is unusable (refusal, abnormal or truncated
# finish_reason, empty / non-JSON body, empty tool turn). The chain-level `cause` is derived from
# these per-provider classes; only an all-`availability` chain counts toward the circuit breaker.
LLMFailureClass = Literal["availability", "content"]


class LLMProviderError(Exception):
    """Base error for the structured-LLM provider adapters.

    `failure_class` defaults to `content` so a raise site that forgets to tag itself can never move
    the run's circuit breaker by mistake; every SDK/API exception site tags `availability` explicitly.
    """

    def __init__(self, message: str, *, failure_class: LLMFailureClass = "content") -> None:
        super().__init__(message)
        self.failure_class: LLMFailureClass = failure_class


class LLMResponseTruncatedError(LLMProviderError):
    """Raised when a provider stopped generating before the body was complete (a `content` failure)."""
