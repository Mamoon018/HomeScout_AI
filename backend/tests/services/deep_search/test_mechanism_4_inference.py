"""Assembled-path checks for Mechanism 4 persona-driven category inference.

No live provider calls. The fake StructuredLLMProvider returns recorded dicts. State is
seeded as after Mechanism 2 (`resolved` set) unless a test says otherwise.
"""

from __future__ import annotations

import copy
import logging

import pytest

from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import InferenceValidationError
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_schemas.schemas import (
    INFERRED_CATEGORIES_SCHEMA_NAME,
    ExtractedCategory,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
)
from src.services.deep_search.requirement_interpretation import UserRequirementsInterpretation

_DAYCARE_ENTRY = {
    "taxonomy_node": "daycare",
    "reasoning": (
        "The persona fact that they have a four-year-old who needs care during the "
        "workday supports daycare as a distinct need from the explicit gym."
    ),
}
_PHARMACY_ENTRY = {
    "taxonomy_node": "pharmacy",
    "reasoning": (
        "The persona fact that they take weekly prescription medication supports "
        "pharmacy as a distinct need from gym and daycare."
    ),
}
_PARK_ENTRY = {
    "taxonomy_node": "park",
    "reasoning": (
        "The persona fact that they run early mornings supports park as a distinct "
        "need from the explicit supermarket."
    ),
}
_GYM_COLLISION_ENTRY = {
    "taxonomy_node": "gym",
    "reasoning": "The persona trains every morning, which would restate the explicit gym.",
}
_SUPERMARKET_COLLISION_ENTRY = {
    "taxonomy_node": "supermarket",
    "reasoning": "The persona cooks most nights, which would restate the explicit supermarket.",
}
_FITNESS_CENTER_ENTRY = {
    "taxonomy_node": "fitness_center",
    "reasoning": (
        "The persona works out several times a week; this body already omits a Step 2 "
        "overlap by not pairing fitness_center with an explicit gym in the stored list."
    ),
}


class FakeStructuredProvider:
    """Returns recorded bodies, optionally queued per schema name."""

    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        *,
        bodies: list[dict] | None = None,
        bodies_by_schema: dict[str, list[dict]] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.last_user_content: str | None = None
        self._queue = [copy.deepcopy(body) for body in (bodies or [])]
        self._by_schema = {
            schema_name: [copy.deepcopy(body) for body in queue]
            for schema_name, queue in (bodies_by_schema or {}).items()
        }

    def generate_structured(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
    ) -> dict:
        self.calls.append(schema_name)
        self.last_user_content = user_content
        queue = self._by_schema.get(schema_name)
        if queue is not None:
            if not queue:
                raise LLMProviderError("no recorded body left for this schema")
            return queue.pop(0)
        if not self._queue:
            raise LLMProviderError("no recorded body left")
        return self._queue.pop(0)


def _payload() -> PayloadRecord:
    return PayloadRecord(
        normalized_text=(
            "A well-equipped gym that opens before 7am, a large grocery store, and we "
            "have a four-year-old who needs care during the workday."
        ),
        raw_text="seeded after Mechanism 2",
    )


def _extracted(
    *,
    explicit_categories: list[ExtractedCategory] | None = None,
    persona_facts: list[str] | None = None,
) -> ExtractedRequirements:
    if explicit_categories is None:
        explicit_categories = [
            ExtractedCategory(
                category_id=0,
                name="well-equipped gym",
                characteristics=["open before 7am"],
            ),
            ExtractedCategory(
                category_id=1,
                name="large grocery store",
                characteristics=["not a corner shop"],
            ),
        ]
    return ExtractedRequirements(
        explicit_categories=explicit_categories,
        ambiguity_flags=[],
        persona_facts=(
            list(persona_facts)
            if persona_facts is not None
            else ["cooks most nights", "has a four-year-old who needs care during the workday"]
        ),
    )


def _resolved_categories() -> list[ResolvedCategory]:
    return [
        ResolvedCategory(
            category_id=0,
            taxonomy_node="gym",
            raw_name="well-equipped gym",
            characteristics=["open before 7am"],
            provenance="confident",
        ),
        ResolvedCategory(
            category_id=1,
            taxonomy_node="supermarket",
            raw_name="large grocery store",
            characteristics=["not a corner shop"],
            provenance="confident",
        ),
    ]


def _state_after_mechanism_2(
    *,
    persona_facts: list[str] | None = None,
    explicit_categories: list[ExtractedCategory] | None = None,
    resolved_explicit_categories: list[ResolvedCategory] | None = None,
) -> RequirementInterpretationState:
    payload = _payload()
    extracted = _extracted(
        explicit_categories=explicit_categories,
        persona_facts=persona_facts,
    )
    if resolved_explicit_categories is None:
        resolved_explicit_categories = _resolved_categories()
    resolved = ResolvedRequirements(
        payload=payload,
        resolved_explicit_categories=resolved_explicit_categories,
        ambiguity_flags=[],
        persona_facts=list(extracted.persona_facts),
    )
    return RequirementInterpretationState(
        payload=payload,
        extracted=extracted,
        resolved=resolved,
    )


def _interpretation(provider: FakeStructuredProvider) -> UserRequirementsInterpretation:
    return UserRequirementsInterpretation([provider])


def _body(*entries: dict) -> dict:
    return {"inferred_categories": [copy.deepcopy(entry) for entry in entries]}


def test_empty_persona_writes_empty_list() -> None:
    provider = FakeStructuredProvider(bodies=[_body()])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2(persona_facts=[])

    result = interpretation.run_persona_driven_category_inference(state)

    assert result.inferred_categories == []
    assert provider.calls == [INFERRED_CATEGORIES_SCHEMA_NAME]


def test_one_valid_distinct_node_stamps_id_after_extracted_max() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_DAYCARE_ENTRY)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    interpretation.run_persona_driven_category_inference(state)

    assert len(state.inferred_categories) == 1
    stored = state.inferred_categories[0]
    assert stored.taxonomy_node == "daycare"
    assert stored.category_id == 2
    assert stored.reasoning == _DAYCARE_ENTRY["reasoning"]


def test_two_valid_distinct_nodes_get_consecutive_ids() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_DAYCARE_ENTRY, _PHARMACY_ENTRY)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    interpretation.run_persona_driven_category_inference(state)

    assert [entry.taxonomy_node for entry in state.inferred_categories] == [
        "daycare",
        "pharmacy",
    ]
    assert [entry.category_id for entry in state.inferred_categories] == [2, 3]


def test_one_collision_plus_sibling_keeps_sibling_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = FakeStructuredProvider(bodies=[_body(_GYM_COLLISION_ENTRY, _DAYCARE_ENTRY)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()
    resolved_snapshot = [
        (category.taxonomy_node, category.category_id)
        for category in state.resolved.resolved_explicit_categories
    ]

    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        interpretation.run_persona_driven_category_inference(state)

    assert len(state.inferred_categories) == 1
    assert state.inferred_categories[0].taxonomy_node == "daycare"
    assert state.inferred_categories[0].category_id == 2
    assert "exact_explicit_duplicate" in caplog.text
    assert [
        (category.taxonomy_node, category.category_id)
        for category in state.resolved.resolved_explicit_categories
    ] == resolved_snapshot


def test_both_collide_writes_empty_list_without_raising() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_COLLISION_ENTRY, _SUPERMARKET_COLLISION_ENTRY)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    interpretation.run_persona_driven_category_inference(state)

    assert state.inferred_categories == []


def test_duplicate_inferred_node_keeps_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    duplicate = {
        "taxonomy_node": "daycare",
        "reasoning": "A later repeat of the same inferred node.",
    }
    provider = FakeStructuredProvider(bodies=[_body(_DAYCARE_ENTRY, duplicate)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        interpretation.run_persona_driven_category_inference(state)

    assert len(state.inferred_categories) == 1
    assert state.inferred_categories[0].taxonomy_node == "daycare"
    assert state.inferred_categories[0].reasoning == _DAYCARE_ENTRY["reasoning"]
    assert "duplicate_inferred_node" in caplog.text


def test_unknown_taxonomy_node_rejects_body_and_leaves_list_empty() -> None:
    provider = FakeStructuredProvider(
        bodies=[
            _body(
                {
                    "taxonomy_node": "not_a_real_node",
                    "reasoning": "This node is not in the maintained taxonomy.",
                }
            )
        ]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    with pytest.raises(InferenceValidationError) as exc_info:
        interpretation.run_persona_driven_category_inference(state)

    assert exc_info.value.stage == "execute_category_inference"
    assert state.inferred_categories == []


def test_more_than_two_entries_rejects_without_truncating() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_DAYCARE_ENTRY, _PHARMACY_ENTRY, _PARK_ENTRY)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    with pytest.raises(InferenceValidationError) as exc_info:
        interpretation.run_persona_driven_category_inference(state)

    assert exc_info.value.stage == "execute_category_inference"
    assert state.inferred_categories == []
    assert provider.calls == [INFERRED_CATEGORIES_SCHEMA_NAME]


def test_no_explicit_categories_numbering_starts_at_zero() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_DAYCARE_ENTRY)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2(
        explicit_categories=[],
        resolved_explicit_categories=[],
        persona_facts=["has a four-year-old who needs care during the workday"],
    )

    interpretation.run_persona_driven_category_inference(state)

    assert len(state.inferred_categories) == 1
    assert state.inferred_categories[0].category_id == 0
    assert state.inferred_categories[0].taxonomy_node == "daycare"


def test_instruction_only_step2_negation_and_thin_evidence_are_not_clamped() -> None:
    """Dummy bodies already obey instruction-only rules; stored list matches; code does not clamp."""
    cases = (
        [],
        ["no interest in nightlife", "we don't drink"],
        ["works out several times a week"],
    )
    for persona_facts in cases:
        provider = FakeStructuredProvider(bodies=[_body()])
        interpretation = _interpretation(provider)
        state = _state_after_mechanism_2(persona_facts=persona_facts)

        interpretation.run_persona_driven_category_inference(state)

        assert state.inferred_categories == []
        assert provider.calls == [INFERRED_CATEGORIES_SCHEMA_NAME]


def test_step2_overlap_different_node_is_kept_because_code_does_not_clamp() -> None:
    """fitness_center vs gym is instruction-only; exact-node strip must not drop it."""
    provider = FakeStructuredProvider(bodies=[_body(_FITNESS_CENTER_ENTRY)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_2()

    interpretation.run_persona_driven_category_inference(state)

    assert len(state.inferred_categories) == 1
    assert state.inferred_categories[0].taxonomy_node == "fitness_center"
    assert state.inferred_categories[0].category_id == 2
