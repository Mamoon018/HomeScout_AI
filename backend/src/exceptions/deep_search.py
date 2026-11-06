from typing import ClassVar, Literal

# Why an M3 LLM step failed (C3.1.2 "Typed error"). `availability`: every provider in the chain
# failed to serve the request; `content`: at least one provider answered unusably; `circuit_open`:
# the run's breaker was open, so no call was made. Only `availability` moves the breaker counter.
ProviderFailureCause = Literal["availability", "content", "circuit_open"]


class RequirementExtractionError(Exception):
    """Base failure surface of the requirement interpretation responsibility."""

    # Named so a caller can report which stage exited without inspecting a traceback.
    stage: ClassVar[str] = "unknown"


class InputTooShortError(RequirementExtractionError):
    """Raised when the input is empty, whitespace-only, or under the word bound."""

    stage: ClassVar[str] = "intake_and_assemble_payload"


class UnsupportedLanguageError(RequirementExtractionError):
    """Raised when the input is not written in English."""

    stage: ClassVar[str] = "intake_and_assemble_payload"


class ExtractionProviderError(RequirementExtractionError):
    """Raised when no provider in the bound order returned a body."""

    stage: ClassVar[str] = "execute_and_validate"


class ExtractionValidationError(RequirementExtractionError):
    """Raised when a returned body failed validation against the wire contract."""

    stage: ClassVar[str] = "execute_and_validate"


class CategoryResolutionError(Exception):
    """Base failure surface of Mechanism 2 Component 2A (category scope resolution)."""

    # Named so a caller can report which operation exited without reading a traceback.
    # Operation 1 and Operation 2 share these classes, so the raiser may override the
    # default with the concrete stage via the constructor.
    stage: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class CategoryMappingProviderError(CategoryResolutionError):
    """Raised when no provider in the bound order returned a mapping/resolution body."""

    stage: ClassVar[str] = "execute_taxonomy_mapping"


class CategoryMappingValidationError(CategoryResolutionError):
    """Raised when a returned body failed the mapping/resolution wire contract."""

    stage: ClassVar[str] = "execute_taxonomy_mapping"


class ClarificationError(Exception):
    """Base failure surface of Mechanism 2 Component 2B (category clarification)."""

    # Named so a caller can tell provider-vs-validation without reading a traceback.
    stage: ClassVar[str] = "execute_clarification_questions"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class ClarificationProviderError(ClarificationError):
    """Raised when no provider in the bound order returned a clarification body."""

    stage: ClassVar[str] = "execute_clarification_questions"


class ClarificationValidationError(ClarificationError):
    """Raised when a returned body failed the clarification wire contract or coverage."""

    stage: ClassVar[str] = "execute_clarification_questions"


class InferenceError(Exception):
    """Base failure surface of Mechanism 4 (persona-driven category inference)."""

    # Named so a caller can tell provider-vs-validation without reading a traceback.
    stage: ClassVar[str] = "execute_category_inference"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class InferenceProviderError(InferenceError):
    """Raised when no provider in the bound order returned an inference body."""

    stage: ClassVar[str] = "execute_category_inference"


class InferenceValidationError(InferenceError):
    """Raised when a returned body failed the inference wire contract or taxonomy set."""

    stage: ClassVar[str] = "execute_category_inference"


class DepthAssignmentError(Exception):
    """Base failure surface of Mechanism 5 (per-category depth calibration)."""

    # Named so a caller can tell provider-vs-validation without reading a traceback.
    stage: ClassVar[str] = "execute_depth_assignment"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class DepthAssignmentProviderError(DepthAssignmentError):
    """Raised when no provider in the bound order returned a depth-assignment body."""

    stage: ClassVar[str] = "execute_depth_assignment"


class DepthAssignmentValidationError(DepthAssignmentError):
    """Raised when a returned body failed schema, id coverage, or the explicit floor."""

    stage: ClassVar[str] = "execute_depth_assignment"


class MetricDefinitionError(Exception):
    """Base failure surface of Mechanism 6 (per-category metric definition)."""

    # Named so a caller can tell provider-vs-validation without reading a traceback.
    stage: ClassVar[str] = "execute_metric_definition"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class MetricDefinitionProviderError(MetricDefinitionError):
    """Raised when no provider in the bound order returned a metric-definition body."""

    stage: ClassVar[str] = "execute_metric_definition"


class MetricDefinitionValidationError(MetricDefinitionError):
    """Raised when a returned body failed the metric-definition schema or id coverage."""

    stage: ClassVar[str] = "execute_metric_definition"


class PlaceDiscoveryError(Exception):
    """Base failure surface of Responsibility 2 Mechanism 1 Component M1.1 (place discovery)."""

    # Named so a caller can report which stage exited without reading a traceback.
    stage: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class PlaceDiscoveryRequestError(PlaceDiscoveryError):
    """Raised when the origin, radius, node, or field set cannot build a valid request."""

    stage: ClassVar[str] = "build_discovery_request"


class PlaceDiscoveryCallError(PlaceDiscoveryError):
    """Raised when the searchNearby discovery call failed after its retries."""

    stage: ClassVar[str] = "execute_discovery"


class AccessibilityEnrichmentError(Exception):
    """Base failure surface of Responsibility 2 Mechanism 1 Component M1.2 (accessibility enrichment)."""

    # Named so a caller can report which stage exited without reading a traceback.
    stage: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class RoutingRetrievalError(AccessibilityEnrichmentError):
    """Raised when a per-mode routing re-search failed after its retries."""

    stage: ClassVar[str] = "retrieve_mode_routing"


class TransitRetrievalError(AccessibilityEnrichmentError):
    """Raised when a computeRouteMatrix transit batch failed after its retries."""

    stage: ClassVar[str] = "retrieve_transit"


class ResultAttachmentError(Exception):
    """Base failure surface of Responsibility 2 Mechanism 1 Component M1.3 (result attachment)."""

    # Named so a caller can report which stage exited without reading a traceback.
    stage: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class ResultAssemblyError(ResultAttachmentError):
    """Raised when a discovered category_id has no matching CategoryMetricPlan to join against."""

    stage: ClassVar[str] = "assemble_amenity_records"


class MetricResolutionError(Exception):
    """Base failure surface of Responsibility 2 Mechanism 3 (LLM-driven metric resolution)."""

    # Named so a caller can report which stage exited without reading a traceback.
    stage: ClassVar[str] = "run_llm_metric_resolution"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class MetricResolutionProviderError(MetricResolutionError):
    """Raised when an M3 LLM step got no usable answer, or the run's circuit breaker was open.

    `cause` is required (C3.1.2 "Typed error"): the shared caller derives it from the chain's
    per-provider failure classes, and the breaker check raises it as `circuit_open`.
    `carries_cause` tells the client-layer caller to pass `cause` without importing this class.
    """

    stage: ClassVar[str] = "run_llm_metric_resolution"
    carries_cause: ClassVar[bool] = True

    def __init__(
        self, message: str, *, stage: str | None = None, cause: ProviderFailureCause
    ) -> None:
        super().__init__(message, stage=stage)
        self.cause: ProviderFailureCause = cause


class MetricResolutionValidationError(MetricResolutionError):
    """Raised by R3.M1.1 tool-catalog construction (the non-strict tool path).

    This is the one raising path of R3.M1.1. `build_tool_catalog` raises it *before* any LLM
    call when the controlled catalog cannot be built: the context-selected server or tool is
    missing from the raw definitions, the raw schema conflicts with expectations (for example
    `search_queries` absent or type-incompatible), or a retained `$ref` cannot be resolved
    against the `$defs` carried with it. The run cannot proceed, so it fails fast rather than
    sending the model a schema it could not honor.

    The call guard (`guard_proposed_calls`) does NOT raise this: a rejected tool message is a
    normal, expected outcome carrying per-call metadata that downstream replay/retry steps read,
    so it is returned as a `GuardDecision`, not thrown.
    """

    stage: ClassVar[str] = "build_tool_catalog"


# ---------------------------------------------------------------------------------
# Responsibility 1 over HTTP — pause/resume failure surface (C1, C2, C3, C4).
# ---------------------------------------------------------------------------------


class ClarificationAnswerError(Exception):
    """Raised when submitted answers do not match the stored clarification questions."""

    stage: ClassVar[str] = "record_clarification_answers"


class StateVersionMismatchError(Exception):
    """Raised when a saved R1 state carries a version other than the code's current one."""

    stage: ClassVar[str] = "load_state"

    def __init__(self, found: object, expected: int) -> None:
        super().__init__(f"Saved state version {found!r} does not match current version {expected}")
        self.found = found
        self.expected = expected


class CheckpointMissingError(Exception):
    """Raised when rebuilding a run reaches a step that has no saved result.

    Rebuilding a paused or finished run never makes an LLM call, so a missing row means the
    saved rows are inconsistent. It is raised instead of paying for an unplanned call.
    """

    stage: ClassVar[str] = "replay"

    def __init__(self, step_id: str) -> None:
        super().__init__(f"Step {step_id!r} has no saved result to rebuild the run from")
        self.step_id = step_id


class RunStoreError(Exception):
    """Raised when a `r1_runs` / `r1_run_steps` read or write could not be completed."""

    stage: ClassVar[str] = "run_store"

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class RunNotFoundError(Exception):
    """Raised when no run exists for this run_id and the verified user_id."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id} was not found")
        self.run_id = run_id


class RunConflictError(Exception):
    """Raised when the run's current status does not allow the requested action."""

    def __init__(self, message: str, *, run_id: str, status: str, retryable: bool | None) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.status = status
        self.retryable = retryable


class R1RunFailedError(Exception):
    """Raised after a run was saved as failed, carrying what the page needs to show next."""

    def __init__(
        self,
        message: str,
        *,
        run_id: str,
        stage: str,
        retryable: bool,
        provider_unavailable: bool,
        unexpected: bool = False,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.stage = stage
        self.retryable = retryable
        # True when no LLM provider answered (503); False when a body failed validation (502).
        self.provider_unavailable = provider_unavailable
        # True when a non-R1 exception (a bug) failed the run (500).
        self.unexpected = unexpected


# Every typed error an R1 stage after the input check can raise. Each carries a `stage`.
R1_STAGE_ERRORS: tuple[type[Exception], ...] = (
    ExtractionProviderError,
    ExtractionValidationError,
    CategoryResolutionError,
    ClarificationError,
    InferenceError,
    DepthAssignmentError,
    MetricDefinitionError,
)

# The subset raised when no provider in the chain returned a body (mapped to 503).
R1_PROVIDER_ERRORS: tuple[type[Exception], ...] = (
    ExtractionProviderError,
    CategoryMappingProviderError,
    ClarificationProviderError,
    InferenceProviderError,
    DepthAssignmentProviderError,
    MetricDefinitionProviderError,
)
