from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The schema name the provider echoes back with the constrained body.
EXTRACTION_SCHEMA_NAME = "extracted_requirements"


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
    """Strict provider schema derived from the wire model."""
    schema = ExtractedRequirements.model_json_schema()
    _apply_strict_object_rules(schema)
    return schema


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


@dataclass(frozen=True)
class PayloadRecord:
    """The bounded, normalized input the extraction call is made against."""

    normalized_text: str
    raw_text: str


@dataclass
class RequirementInterpretationState:
    """Handoff object for Component 2A, which appends its results to this same object."""

    payload: PayloadRecord
    extracted: ExtractedRequirements
