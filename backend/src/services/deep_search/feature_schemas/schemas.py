from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.services.deep_search.feature_schemas.amenity_taxonomy import (
    AMENITY_TAXONOMY_NODES,
)

# The schema name the provider echoes back with the constrained body.
EXTRACTION_SCHEMA_NAME = "extracted_requirements"

# Component 2A's two constrained operations echo these schema names back with their bodies.
TAXONOMY_MAPPING_SCHEMA_NAME = "taxonomy_mapping_result"
FLAG_RESOLUTION_SCHEMA_NAME = "flag_resolution_result"

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


@dataclass
class ResolvedRequirements:
    """Component 2A's output object; Operation 2 appends resolved categories in place."""

    payload: PayloadRecord
    resolved_explicit_categories: list[ResolvedCategory]
    ambiguity_flags: list[AmbiguityFlag]
    persona_facts: list[str]


@dataclass
class RequirementInterpretationState:
    """Handoff object for Component 2A, which appends its results to this same object."""

    payload: PayloadRecord
    extracted: ExtractedRequirements
    user_responses: dict[int, UserResponse] = field(default_factory=dict)
    resolved: ResolvedRequirements | None = None
