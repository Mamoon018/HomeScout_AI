from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.services.deep_search.feature_schemas.amenity_taxonomy import (
    AMENITY_TAXONOMY_NODES,
)

# The schema name the provider echoes back with the constrained body.
EXTRACTION_SCHEMA_NAME = "extracted_requirements"

# Component 2A's two constrained operations echo these schema names back with their bodies.
TAXONOMY_MAPPING_SCHEMA_NAME = "taxonomy_mapping_result"
FLAG_RESOLUTION_SCHEMA_NAME = "flag_resolution_result"

# Component 2B's constrained question-generation call echoes this schema name back.
CLARIFICATION_QUESTIONS_SCHEMA_NAME = "clarification_questions"

# Mechanism 4's constrained inference call echoes this schema name back with the body.
INFERRED_CATEGORIES_SCHEMA_NAME = "inferred_categories_schema"

# Mechanism 5's constrained depth-assignment call echoes this schema name back with the body.
DEPTH_ASSIGNMENT_SCHEMA_NAME = "depth_assignment_schema"

# Three-level information band stamped onto each remaining category by Mechanism 5.
DepthLevel = Literal["basic_profile", "operating_details", "specific_attributes"]

# Mechanism 6's constrained metric-definition call echoes this schema name back with the body.
METRIC_DEFINITION_SCHEMA_NAME = "metric_definition_schema"

# Value sets a metric may carry. `number_with_unit`, `enum`, and `date_time` map to the
# contract's number+unit, enum[fixed set], and date/time value types.
MetricValueType = Literal["number_with_unit", "boolean", "enum", "date_time"]
NullPolicy = Literal["null", "unknown"]
ResolutionTool = Literal["google_maps", "parallel_web_search", "firecrawl"]
# The two dynamic depth bands the model defines metrics for; basic_profile is fixed.
MetricBand = Literal["operating_details", "specific_attributes"]
# The bands a pre-defined (code-owned, Google-Maps-resolved) metric belongs to. Includes
# basic_profile, which dynamic metrics never use; excludes specific_attributes, which has no
# fixed dimensions of its own.
PredefinedBand = Literal["basic_profile", "operating_details"]

# Upper bound on surviving metrics per band per category; code drops the extras.
MAX_METRICS_PER_BAND = 4

_BASIC_PROFILE_DIMENSIONS: tuple[str, ...] = (
    "name",
    "category",
    "address",
    "website",
    "place_id",
    "coordinates",
    "travel distance per mode (walk, drive, cycle)",
    "travel duration per mode (walk, drive, cycle)",
    "transit_details",
    "google_maps_uri",
)
_OPERATING_DETAILS_DIMENSIONS: tuple[str, ...] = _BASIC_PROFILE_DIMENSIONS + (
    "opening hours",
    "contact phone",
    "rating",
    "review volume",
    "price level",
    "reviews",
)

# Fixed dimensions later stages fetch for a depth, cumulative by band. Not model output and
# not stored on the state; the metric instruction lists them as "do not propose these".
FIXED_DIMENSIONS_BY_DEPTH: dict[str, tuple[str, ...]] = {
    "basic_profile": _BASIC_PROFILE_DIMENSIONS,
    "operating_details": _OPERATING_DETAILS_DIMENSIONS,
    "specific_attributes": _OPERATING_DETAILS_DIMENSIONS,
}

# Router destination after each inspect of a fresh 2A output.
CategoryResolutionRoute = Literal["component_2b", "mechanism_3"]

# Provenance values a resolved category can carry: a confident mapping, or a nearest-node
# fallback applied only in Operation 2 once a user response exists.
Provenance = Literal["confident", "nearest_node"]


class ExtractedCategory(BaseModel):
    """One amenity category the customer stated, with the traits stated for it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description=(
            "The amenity category exactly as the customer worded it. Do not translate it "
            "into any predefined category list and do not rename it."
        )
    )
    characteristics: list[str] = Field(
        description=(
            "The qualities the customer stated for this category, in the customer's own "
            "wording. Empty list when the category was named with no qualities attached."
        )
    )
    # Assigned in code by list position after the extraction call. Excluded from the
    # provider schema so the model never emits or invents it.
    category_id: int | None = Field(
        default=None,
        description=(
            "Stable identity of this explicit category, assigned programmatically by list "
            "position when extraction is assembled. Not produced by the extraction model."
        ),
    )


class AmbiguityFlag(BaseModel):
    """One phrase that has two or more reasonable readings."""

    model_config = ConfigDict(extra="forbid")

    phrase: str = Field(
        description="The exact phrase from the input that carries the competing readings."
    )
    target: Literal["category", "characteristic", "persona"] = Field(
        description=(
            "What the ambiguous phrase is about: 'category' when the amenity category "
            "itself is unclear, 'characteristic' when a stated quality is unclear, "
            "'persona' when a situation or lifestyle statement is unclear."
        )
    )
    category: str | None = Field(
        default=None,
        description=(
            "The explicit category this flag belongs to, in the customer's own wording, "
            "when the flag is about a quality of a named category. Null when the category "
            "itself is what is ambiguous, or when the flag is about a persona fact."
        ),
    )
    characteristic: str | None = Field(
        default=None,
        description=(
            "The specific quality that is ambiguous, when the flag targets a "
            "characteristic. Null for category and persona flags."
        ),
    )
    # Stamped in the same extraction-assembly pass as ExtractedCategory.category_id.
    # Excluded from the extraction provider schema; required on every target=category flag.
    category_id: int | None = Field(
        default=None,
        description=(
            "The category_id of the backing explicit_categories entry, when this flag "
            "targets a category. Null for characteristic and persona flags."
        ),
    )


class ExtractedRequirements(BaseModel):
    """The four separated buckets of one extraction pass."""

    model_config = ConfigDict(extra="forbid")

    explicit_categories: list[ExtractedCategory] = Field(
        description=(
            "Categories the customer directly named or clearly referred to as wanted, "
            "preferred, needed, avoided, or considered, each with its stated "
            "characteristics nested underneath. Empty list when none were stated."
        )
    )
    ambiguity_flags: list[AmbiguityFlag] = Field(
        description=(
            "Phrases with two or more reasonable readings that would lead to different "
            "categories, characteristics, or scopes, where the input gives no confident "
            "basis to pick one. Empty list when nothing was ambiguous."
        )
    )
    persona_facts: list[str] = Field(
        description=(
            "Facts about who the customer is, their situation, and their lifestyle, "
            "including negations and conditional statements. Empty list when none were "
            "stated."
        )
    )


def extraction_json_schema() -> dict:
    """Strict provider schema derived from the wire model.

    `category_id` is stamped in code after the call, so it is stripped before the schema
    is closed. The extraction model returns categories in order and flags without ids.
    """
    schema = ExtractedRequirements.model_json_schema()
    _strip_programmatic_identity_fields(schema)
    _apply_strict_object_rules(schema)
    return schema


_PROGRAMMATIC_IDENTITY_FIELDS = frozenset({"category_id"})


def _strip_programmatic_identity_fields(node: Any) -> None:
    """Remove fields the extraction model must not emit from a JSON-schema tree."""
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            for field_name in _PROGRAMMATIC_IDENTITY_FIELDS:
                properties.pop(field_name, None)
        for value in node.values():
            _strip_programmatic_identity_fields(value)
    elif isinstance(node, list):
        for value in node:
            _strip_programmatic_identity_fields(value)


def _apply_strict_object_rules(node: Any) -> None:
    """Close every object in the schema tree: no extra keys, every property required."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            properties = node.get("properties", {})
            node["additionalProperties"] = False
            node["required"] = list(properties)
        for value in node.values():
            _apply_strict_object_rules(value)
    elif isinstance(node, list):
        for value in node:
            _apply_strict_object_rules(value)


class MappedCategory(BaseModel):
    """One confident Operation 1 mapping of a labeled explicit category onto a taxonomy node."""

    model_config = ConfigDict(extra="forbid")

    taxonomy_node: str = Field(
        description=(
            "The single taxonomy node this category maps to. Must be one of the nodes "
            "in the provided taxonomy exactly; do not invent, rename, or return a node "
            "outside the list."
        )
    )
    category_id: int = Field(
        description=(
            "The category_id of the explicit category being mapped, echoed from the input. "
            "Do not invent an id or copy a name; echo only the id you were handed."
        )
    )


class TaxonomyMappingResult(BaseModel):
    """Operation 1 output: confident mappings plus ids for what could not be mapped."""

    model_config = ConfigDict(extra="forbid")

    resolved_categories: list[MappedCategory] = Field(
        description=(
            "Every explicit category that maps confidently to exactly one taxonomy node. "
            "Empty list when none mapped confidently."
        )
    )
    unmapped_category_ids: list[int] = Field(
        description=(
            "The category_id of every explicit category that cannot be confidently mapped "
            "to a single taxonomy node. Empty list when every category mapped."
        )
    )


class ResolvedFlagEntry(BaseModel):
    """One Operation 2 resolution of a category flag against its paired user response."""

    model_config = ConfigDict(extra="forbid")

    taxonomy_node: str = Field(
        description=(
            "The single taxonomy node this category flag resolves to. Must be one of the "
            "nodes in the provided taxonomy exactly."
        )
    )
    category_id: int = Field(
        description=(
            "The category_id of the category flag being resolved, echoed from the input. "
            "Do not invent an id or copy a name."
        )
    )
    provenance: Provenance = Field(
        description=(
            "'confident' when the paired user response gives clear evidence for the node; "
            "'nearest_node' when the response is still insufficient and the nearest "
            "most-fitting node was chosen."
        )
    )


class FlagResolutionResult(BaseModel):
    """Operation 2 output: one resolved entry per category flag that was submitted."""

    model_config = ConfigDict(extra="forbid")

    resolved_categories: list[ResolvedFlagEntry] = Field(
        description="One resolved taxonomy entry for every {flag, response} pair submitted."
    )


class UserResponse(BaseModel):
    """One clarification answer Component 2B wrote, keyed on the state by category_id."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="The clarification question that was asked.")
    options: list[str] = Field(
        description="The candidate interpretations that were shown with the question."
    )
    response: str = Field(description="The customer's answer to that question.")


class ClarificationQuestion(BaseModel):
    """One generated clarification question for a single category flag."""

    model_config = ConfigDict(extra="forbid")

    category_id: int = Field(
        description=(
            "The category_id of the category flag this question is for, echoed from the "
            "input. Do not invent an id."
        )
    )
    category: str = Field(
        description="The flagged category phrase, echoed from the input for display and grounding."
    )
    question: str = Field(
        description=(
            "The clarification question that asks which amenity type the stated category "
            "maps to, not a preference or a new need."
        )
    )
    options: list[str] = Field(
        min_length=5,
        max_length=5,
        description=(
            "Exactly five candidate interpretations to show the customer. One option must "
            "be the literal 'other' so the customer can describe a different meaning."
        ),
    )

    @field_validator("options")
    @classmethod
    def options_must_include_other(cls, value: list[str]) -> list[str]:
        if value.count("other") != 1:
            raise ValueError('options must contain the literal "other" exactly once')
        return value


class ClarificationResult(BaseModel):
    """Component 2B generation output: one question per submitted category flag."""

    model_config = ConfigDict(extra="forbid")

    questions: list[ClarificationQuestion] = Field(
        description="One clarification question for every submitted category flag."
    )


class InferredCategoryEntry(BaseModel):
    """One wire proposal from the Mechanism 4 inference call."""

    model_config = ConfigDict(extra="forbid")

    taxonomy_node: str = Field(
        description=(
            "The single taxonomy node being inferred. Must be one of the nodes in the "
            "provided taxonomy exactly; do not invent, rename, or return a node outside "
            "the list."
        )
    )
    reasoning: str = Field(
        min_length=1,
        description=(
            "Which persona facts back this inference, in enough detail that a reader can "
            "see the evidence. Not a plausibility score and not a purpose-reason for the "
            "amenity."
        ),
    )


class InferredCategoriesResult(BaseModel):
    """Mechanism 4 wire body: zero to two inferred category proposals."""

    model_config = ConfigDict(extra="forbid")

    inferred_categories: list[InferredCategoryEntry] = Field(
        max_length=2,
        description=(
            "Additional taxonomy nodes inferred from persona evidence. Empty list when "
            "none are justified. At most two entries."
        ),
    )


class DepthAssignmentEntry(BaseModel):
    """One wire assignment from the Mechanism 5 depth call."""

    model_config = ConfigDict(extra="forbid")

    category_id: int = Field(
        description=(
            "The category_id of the submitted category being assigned a depth, echoed "
            "from the input. Do not invent an id."
        )
    )
    depth: DepthLevel = Field(
        description=(
            "The information band for this category: 'basic_profile', "
            "'operating_details', or 'specific_attributes'. Start at the origin floor "
            "and escalate only on a trigger."
        )
    )


class DepthAssignmentResult(BaseModel):
    """Mechanism 5 wire body: one depth assignment per submitted category."""

    model_config = ConfigDict(extra="forbid")

    assignments: list[DepthAssignmentEntry] = Field(
        description=(
            "One depth assignment for every submitted category. Length must equal the "
            "number of submitted categories. Do not invent, drop, or duplicate ids."
        )
    )


class ResolutionSourceEntry(BaseModel):
    """Wire shape of where a later stage resolves one metric."""

    model_config = ConfigDict(extra="forbid")

    tool: ResolutionTool = Field(
        description=(
            "The tool a later stage uses: 'google_maps' for a Maps field, "
            "'parallel_web_search' for a web search, 'firecrawl' for a fetched page."
        )
    )
    target: str = Field(
        description=(
            "The concrete target: the Maps field, the shape of the search query, or the "
            "page type to fetch. Must name something specific."
        )
    )


class MetricEntry(BaseModel):
    """One wire metric proposed for a category by the Mechanism 6 call."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Human-readable metric name.")
    question: str = Field(
        description=(
            "The exact decision question this metric answers for this customer, tied to "
            "their request, a persona fact, or the category's own request or inference."
        )
    )
    value_type: MetricValueType = Field(
        description=(
            "'number_with_unit', 'boolean', 'enum', or 'date_time'. Free-form prose is "
            "not a value type."
        )
    )
    unit: str | None = Field(
        description="The unit when value_type is 'number_with_unit'. Null otherwise."
    )
    enum_values: list[str] = Field(
        description=(
            "At least two distinct members when value_type is 'enum'. Empty list otherwise."
        )
    )
    # No description here: strict provider schemas reject any keyword beside a $ref, and
    # this field is a bare reference to ResolutionSourceEntry. The model's own docstring
    # and field descriptions carry the meaning.
    resolution_source: ResolutionSourceEntry
    verification: str = Field(description="What evidence confirms the resolved value.")
    null_policy: NullPolicy = Field(
        description=(
            "What to emit if the value cannot be resolved: 'null' or 'unknown'. Never a guess."
        )
    )
    band: MetricBand = Field(
        description=(
            "The band this metric belongs to: 'operating_details' or 'specific_attributes'. "
            "Never above the category's assigned depth."
        )
    )


class CategoryMetricsEntry(BaseModel):
    """Wire metrics proposed for one submitted category."""

    model_config = ConfigDict(extra="forbid")

    category_id: int = Field(
        description=(
            "The category_id of the submitted category, echoed from the input. Do not "
            "invent an id."
        )
    )
    metrics: list[MetricEntry] = Field(
        description="The metrics for this category. Empty list when none pass the contract."
    )


class MetricDefinitionResult(BaseModel):
    """Mechanism 6 wire body: one metrics entry per submitted category."""

    model_config = ConfigDict(extra="forbid")

    categories: list[CategoryMetricsEntry] = Field(
        description=(
            "One entry for every submitted category. Do not invent, drop, or duplicate ids."
        )
    )


def taxonomy_mapping_json_schema() -> dict:
    """Strict Operation 1 schema derived from the wire model, with the taxonomy enum."""
    schema = TaxonomyMappingResult.model_json_schema()
    _apply_strict_object_rules(schema)
    _inject_taxonomy_node_enum(schema)
    return schema


def flag_resolution_json_schema() -> dict:
    """Strict Operation 2 schema derived from the wire model, with the taxonomy enum."""
    schema = FlagResolutionResult.model_json_schema()
    _apply_strict_object_rules(schema)
    _inject_taxonomy_node_enum(schema)
    return schema


def clarification_questions_json_schema() -> dict:
    """Strict 2B schema derived from the wire model. No taxonomy enum — 2B does not select a node."""
    schema = ClarificationResult.model_json_schema()
    _apply_strict_object_rules(schema)
    return schema


def inferred_categories_json_schema() -> dict:
    """Strict inference schema derived from the wire model, with the taxonomy enum and cap two."""
    schema = InferredCategoriesResult.model_json_schema()
    _apply_strict_object_rules(schema)
    _inject_taxonomy_node_enum(schema)
    return schema


def depth_assignment_json_schema() -> dict:
    """Strict depth-assignment schema derived from the wire model. No taxonomy enum."""
    schema = DepthAssignmentResult.model_json_schema()
    _apply_strict_object_rules(schema)
    return schema


def metric_definition_json_schema() -> dict:
    """Strict metric-definition schema derived from the wire model. No taxonomy enum.

    Carries closed objects, required keys, types, and closed enums only. Length, count, and
    conditional rules are checked in code because strict provider mode does not support them.
    """
    schema = MetricDefinitionResult.model_json_schema()
    _apply_strict_object_rules(schema)
    return schema


def _inject_taxonomy_node_enum(node: Any) -> None:
    """Constrain every `taxonomy_node` property to the real maintained nodes by enum."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "taxonomy_node" and isinstance(value, dict):
                value["enum"] = list(AMENITY_TAXONOMY_NODES)
            else:
                _inject_taxonomy_node_enum(value)
    elif isinstance(node, list):
        for value in node:
            _inject_taxonomy_node_enum(value)


@dataclass(frozen=True)
class PayloadRecord:
    """The bounded, normalized input the extraction call is made against."""

    normalized_text: str
    raw_text: str


@dataclass
class ResolvedCategory:
    """One taxonomy-mapped category carried on the ResolvedRequirements output object."""

    category_id: int
    taxonomy_node: str
    raw_name: str
    characteristics: list[str]
    provenance: Provenance
    depth: DepthLevel | None = None


@dataclass
class InferredCategory:
    """One inferred taxonomy node stored after Mechanism 4 strip and identity stamp."""

    taxonomy_node: str
    category_id: int
    reasoning: str
    depth: DepthLevel | None = None


@dataclass
class ResolutionSource:
    """Stored tool and target of one metric."""

    tool: ResolutionTool
    target: str


@dataclass
class PredefinedMetric:
    """One code-owned metric resolved from Google Maps for a fixed dimension.

    Pre-defined metrics are not model output. Each names the depth band it belongs to and the
    Google Maps target a later retrieval stage reads. `label` matches the corresponding entry
    in FIXED_DIMENSIONS_BY_DEPTH for the same band.
    """

    label: str
    band: PredefinedBand
    resolution_source: ResolutionSource


# Google Maps target for each fixed dimension, keyed by the dimension label. Most targets are
# Places searchNearby field-mask tokens (see SEARCH_NEARBY_FIELD_MASK in
# src/clients/google_places.py). Travel distance/duration for walk/drive/cycle come from
# `routingSummaries` in that same searchNearby response (one call per mode). Transit is a
# separate predefined metric (`transit_details`) fetched from the Routes API with
# travelMode TRANSIT; bus, subway, and train are allowed in that same call (not one call
# per transit mode). Predefined metrics are fetch-only; derived metrics are not in this
# catalog. Tool stays "google_maps" for all of these. The label is the exact string used
# in FIXED_DIMENSIONS_BY_DEPTH so the two lists cannot drift.
_BASIC_PROFILE_TARGETS: dict[str, str] = {
    "name": "places.displayName",
    "category": "places.primaryType",
    "address": "places.formattedAddress",
    "website": "places.websiteUri",
    "place_id": "places.id",
    "coordinates": "places.location",
    "travel distance per mode (walk, drive, cycle)": (
        "routingSummaries.legs.distanceMeters via searchNearby for walk/drive/cycle "
        "(one call per mode)"
    ),
    "travel duration per mode (walk, drive, cycle)": (
        "routingSummaries.legs.duration via searchNearby for walk/drive/cycle "
        "(one call per mode)"
    ),
    "transit_details": (
        "Routes API, travelMode TRANSIT (bus, subway, train allowed in the same call)"
    ),
    "google_maps_uri": "places.googleMapsUri",
}
_OPERATING_DETAILS_TARGETS: dict[str, str] = {
    "opening hours": "places.regularOpeningHours",
    "contact phone": "places.internationalPhoneNumber",
    "rating": "places.rating",
    "review volume": "places.userRatingCount",
    "price level": "places.priceLevel",
    "reviews": "places.reviews",
}

# Dimensions that operating_details adds on top of basic_profile, in order.
_OPERATING_DETAILS_ONLY_DIMENSIONS: tuple[str, ...] = _OPERATING_DETAILS_DIMENSIONS[
    len(_BASIC_PROFILE_DIMENSIONS) :
]

_BASIC_PROFILE_PREDEFINED: tuple[PredefinedMetric, ...] = tuple(
    PredefinedMetric(
        label=dimension,
        band="basic_profile",
        resolution_source=ResolutionSource(
            tool="google_maps", target=_BASIC_PROFILE_TARGETS[dimension]
        ),
    )
    for dimension in _BASIC_PROFILE_DIMENSIONS
)
_OPERATING_DETAILS_PREDEFINED: tuple[PredefinedMetric, ...] = _BASIC_PROFILE_PREDEFINED + tuple(
    PredefinedMetric(
        label=dimension,
        band="operating_details",
        resolution_source=ResolutionSource(
            tool="google_maps", target=_OPERATING_DETAILS_TARGETS[dimension]
        ),
    )
    for dimension in _OPERATING_DETAILS_ONLY_DIMENSIONS
)

# Pre-defined metrics later stages resolve from Google Maps for a depth, cumulative by band and
# parallel to FIXED_DIMENSIONS_BY_DEPTH. basic_profile carries the basic set; operating_details
# and specific_attributes both carry the basic set plus the operating set.
PREDEFINED_METRICS_BY_DEPTH: dict[str, tuple[PredefinedMetric, ...]] = {
    "basic_profile": _BASIC_PROFILE_PREDEFINED,
    "operating_details": _OPERATING_DETAILS_PREDEFINED,
    "specific_attributes": _OPERATING_DETAILS_PREDEFINED,
}


@dataclass
class MetricSpec:
    """One stored metric that passed the contract rules."""

    label: str
    question: str
    value_type: MetricValueType
    unit: str | None
    enum_values: list[str]
    resolution_source: ResolutionSource
    verification: str
    null_policy: NullPolicy
    band: MetricBand


@dataclass
class CategoryMetricSet:
    """Metrics for one category, written by Mechanism 6 and keyed by category_id.

    `metrics` is None for a basic_profile category (no dynamic metrics are defined at that
    depth) and a list, possibly empty, for an eligible category.
    """

    category_id: int
    taxonomy_node: str
    metrics: list[MetricSpec] | None


@dataclass
class CategoryMetricPlan:
    """Compiled metric picture for one category, keyed by category_id.

    Holds the pre-defined metrics (code-owned, resolved from Google Maps) and the LLM-defined
    metrics (resolved from Parallel web search and Firecrawl) side by side but separate, so a
    later retrieval stage fetches each subset through its own tools. `specific_metrics` is the
    surviving set from the matching CategoryMetricSet, and is an empty list for a basic_profile
    category. `depth` is carried so retrieval does not look the category back up.
    """

    category_id: int
    taxonomy_node: str
    depth: DepthLevel
    predefined_metrics: list[PredefinedMetric]
    specific_metrics: list[MetricSpec]


@dataclass
class ResolvedRequirements:
    """Component 2A's output object; Operation 2 appends resolved categories in place."""

    payload: PayloadRecord
    resolved_explicit_categories: list[ResolvedCategory]
    ambiguity_flags: list[AmbiguityFlag]
    persona_facts: list[str]


@dataclass
class RequirementInterpretationState:
    """Mutable handoff object later mechanisms read and write across the responsibility."""

    payload: PayloadRecord
    extracted: ExtractedRequirements
    user_responses: dict[int, UserResponse] = field(default_factory=dict)
    resolved: ResolvedRequirements | None = None
    category_resolution_passes: int = 0
    inferred_categories: list[InferredCategory] = field(default_factory=list)
    category_metrics: list[CategoryMetricSet] = field(default_factory=list)
    category_metric_plans: list[CategoryMetricPlan] = field(default_factory=list)


# ---------------------------------------------------------------------------------
# Responsibility 2 — Mechanism 1, Component M1.1 (Place Discovery) contracts.
# ---------------------------------------------------------------------------------

# Locked M1.1 caps. Configurable later; kept as module constants like MIN_INPUT_WORD_COUNT.
DISCOVERY_MAX_RESULTS = 10
DEFAULT_RADIUS_KM = 2.0


@dataclass(frozen=True)
class GeoPoint:
    """The listing origin the neighborhood radius is measured from."""

    latitude: float
    longitude: float


@dataclass(frozen=True)
class DiscoveryRequest:
    """One validated, no-routing searchNearby call spec for a single category."""

    category_id: int
    primary_type: str
    latitude: float
    longitude: float
    radius_meters: float
    field_mask: str
    max_result_count: int


@dataclass(frozen=True)
class CanonicalPlace:
    """One deduplicated place; `place` holds the returned fields with no unit conversion."""

    place_id: str
    place: dict


@dataclass
class AmenitySearchState:
    """Responsibility 2 mutable handoff; M1.1 writes `discovered_places`.

    `discovered_places` is keyed category_id then place_id, so dedup is within a category
    only (a place matching two categories is one record per category). `radius_km` defaults
    to DEFAULT_RADIUS_KM.
    """

    origin: GeoPoint
    radius_km: float
    category_metric_plans: list[CategoryMetricPlan]
    discovered_places: dict[int, dict[str, CanonicalPlace]] = field(default_factory=dict)
