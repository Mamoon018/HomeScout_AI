from typing import ClassVar


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
    """Raised when no provider in the bound order returned a metric-resolution tool turn."""

    stage: ClassVar[str] = "run_llm_metric_resolution"


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
