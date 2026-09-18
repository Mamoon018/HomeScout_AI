"""Assembled-path checks for Mechanism 5 per-category depth calibration.

No live provider calls. The fake StructuredLLMProvider returns recorded dicts. State is
seeded as after Mechanism 4 (`resolved` set, `inferred_categories` written, `depth=None`)
unless a test says otherwise.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import asdict

import pytest

from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import DepthAssignmentValidationError
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_schemas.schemas import (
    DEPTH_ASSIGNMENT_SCHEMA_NAME,
    ExtractedCategory,
    ExtractedRequirements,
    InferredCategory,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
)
from src.services.deep_search.requirement_interpretation import UserRequirementsInterpretation

_GYM_OPERATING = {"category_id": 0, "depth": "operating_details"}
_GYM_SPECIFIC = {"category_id": 0, "depth": "specific_attributes"}
_GYM_BASIC = {"category_id": 0, "depth": "basic_profile"}
_SUPERMARKET_OPERATING = {"category_id": 1, "depth": "operating_details"}
_DAYCARE_BASIC = {"category_id": 2, "depth": "basic_profile"}
_PARK_SPECIFIC = {"category_id": 2, "depth": "specific_attributes"}


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

    async def generate_structured(
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

    async def aclose(self) -> None:
        return None


def _payload() -> PayloadRecord:
    return PayloadRecord(
        normalized_text=(
            "A well-equipped gym that opens before 7am, a large grocery store, and we "
            "have a four-year-old who needs care during the workday."
        ),
        raw_text="seeded after Mechanism 4",
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


def _inferred_daycare() -> InferredCategory:
    return InferredCategory(
        taxonomy_node="daycare",
        category_id=2,
        reasoning=(
            "The persona fact that they have a four-year-old who needs care during the "
            "workday supports daycare as a distinct need from gym and supermarket."
        ),
    )


def _state_after_mechanism_4(
    *,
    persona_facts: list[str] | None = None,
    resolved_explicit_categories: list[ResolvedCategory] | None = None,
    inferred_categories: list[InferredCategory] | None = None,
    explicit_categories: list[ExtractedCategory] | None = None,
) -> RequirementInterpretationState:
    payload = _payload()
    extracted = _extracted(
        explicit_categories=explicit_categories,
        persona_facts=persona_facts,
    )
    if resolved_explicit_categories is None:
        resolved_explicit_categories = _resolved_categories()
    if inferred_categories is None:
        inferred_categories = [_inferred_daycare()]
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
        inferred_categories=list(inferred_categories),
    )


def _interpretation(provider: FakeStructuredProvider) -> UserRequirementsInterpretation:
    return UserRequirementsInterpretation([provider])


def _body(*assignments: dict) -> dict:
    return {"assignments": [copy.deepcopy(item) for item in assignments]}


def _depths(state: RequirementInterpretationState) -> dict[int, str | None]:
    resolved = state.resolved
    assert resolved is not None
    values: dict[int, str | None] = {
        category.category_id: category.depth
        for category in resolved.resolved_explicit_categories
    }
    for entry in state.inferred_categories:
        values[entry.category_id] = entry.depth
    return values


def _identity_snapshot(state: RequirementInterpretationState) -> dict:
    resolved = state.resolved
    assert resolved is not None
    return {
        "explicit": [
            (
                category.category_id,
                category.taxonomy_node,
                tuple(category.characteristics),
                category.raw_name,
                category.provenance,
            )
            for category in resolved.resolved_explicit_categories
        ],
        "inferred": [
            (entry.category_id, entry.taxonomy_node, entry.reasoning)
            for entry in state.inferred_categories
        ],
        "persona_facts": list(resolved.persona_facts),
        "payload": asdict(state.payload),
    }


async def test_both_lists_empty_skips_provider_and_does_not_fail() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_GYM_OPERATING)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4(
        resolved_explicit_categories=[],
        inferred_categories=[],
        explicit_categories=[],
        persona_facts=[],
    )

    result = await interpretation.run_per_category_depth_calibration(state)

    assert result.resolved is not None
    assert result.resolved.resolved_explicit_categories == []
    assert result.inferred_categories == []
    assert provider.calls == []


async def test_explicit_only_stamps_legal_depths() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_SPECIFIC, _SUPERMARKET_OPERATING)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4(inferred_categories=[])

    await interpretation.run_per_category_depth_calibration(state)

    assert state.inferred_categories == []
    assert _depths(state) == {0: "specific_attributes", 1: "operating_details"}
    assert provider.calls == [DEPTH_ASSIGNMENT_SCHEMA_NAME]


async def test_inferred_only_stamps_basic_profile() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_DAYCARE_BASIC)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4(
        resolved_explicit_categories=[],
        explicit_categories=[],
    )

    await interpretation.run_per_category_depth_calibration(state)

    assert state.resolved is not None
    assert state.resolved.resolved_explicit_categories == []
    assert len(state.inferred_categories) == 1
    assert state.inferred_categories[0].depth == "basic_profile"
    assert provider.calls == [DEPTH_ASSIGNMENT_SCHEMA_NAME]


async def test_mixed_batch_stamps_floors_and_one_escalation_without_rewriting_other_fields() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_SPECIFIC, _SUPERMARKET_OPERATING, _DAYCARE_BASIC)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4()
    before = _identity_snapshot(state)

    await interpretation.run_per_category_depth_calibration(state)

    assert _depths(state) == {
        0: "specific_attributes",
        1: "operating_details",
        2: "basic_profile",
    }
    assert _identity_snapshot(state) == before


async def test_explicit_basic_profile_rejects_body_and_leaves_depths_unset() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_BASIC, _SUPERMARKET_OPERATING, _DAYCARE_BASIC)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4()

    with pytest.raises(DepthAssignmentValidationError) as exc_info:
        await interpretation.run_per_category_depth_calibration(state)

    assert exc_info.value.stage == "execute_depth_assignment"
    assert _depths(state) == {0: None, 1: None, 2: None}


async def test_missing_id_rejects_without_stamping() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_GYM_OPERATING, _DAYCARE_BASIC)])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4()

    with pytest.raises(DepthAssignmentValidationError) as exc_info:
        await interpretation.run_per_category_depth_calibration(state)

    assert exc_info.value.stage == "execute_depth_assignment"
    assert _depths(state) == {0: None, 1: None, 2: None}


async def test_extra_id_rejects_without_stamping() -> None:
    extra = {"category_id": 9, "depth": "operating_details"}
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_OPERATING, _SUPERMARKET_OPERATING, _DAYCARE_BASIC, extra)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4()

    with pytest.raises(DepthAssignmentValidationError) as exc_info:
        await interpretation.run_per_category_depth_calibration(state)

    assert exc_info.value.stage == "execute_depth_assignment"
    assert _depths(state) == {0: None, 1: None, 2: None}


async def test_duplicate_id_rejects_without_stamping() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_OPERATING, _SUPERMARKET_OPERATING, _GYM_SPECIFIC)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4(inferred_categories=[])

    with pytest.raises(DepthAssignmentValidationError) as exc_info:
        await interpretation.run_per_category_depth_calibration(state)

    assert exc_info.value.stage == "execute_depth_assignment"
    assert _depths(state) == {0: None, 1: None}


async def test_illegal_depth_string_rejects_without_stamping() -> None:
    provider = FakeStructuredProvider(
        bodies=[
            _body(
                {"category_id": 0, "depth": "deep_dive"},
                _SUPERMARKET_OPERATING,
                _DAYCARE_BASIC,
            )
        ]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4()

    with pytest.raises(DepthAssignmentValidationError) as exc_info:
        await interpretation.run_per_category_depth_calibration(state)

    assert exc_info.value.stage == "execute_depth_assignment"
    assert _depths(state) == {0: None, 1: None, 2: None}


async def test_empty_signals_still_call_and_stamp_floors() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_OPERATING, _SUPERMARKET_OPERATING)]
    )
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4(
        persona_facts=[],
        inferred_categories=[],
    )
    assert state.resolved is not None
    for category in state.resolved.resolved_explicit_categories:
        category.characteristics = []

    await interpretation.run_per_category_depth_calibration(state)

    assert provider.calls == [DEPTH_ASSIGNMENT_SCHEMA_NAME]
    assert _depths(state) == {0: "operating_details", 1: "operating_details"}


async def test_instruction_only_escalation_is_not_rewritten_by_code() -> None:
    """Dummy body already encodes a valid inferred escalation; code must not clamp it down."""
    provider = FakeStructuredProvider(
        bodies=[_body(_GYM_OPERATING, _SUPERMARKET_OPERATING, _PARK_SPECIFIC)]
    )
    interpretation = _interpretation(provider)
    inferred = InferredCategory(
        taxonomy_node="park",
        category_id=2,
        reasoning=(
            "The persona has a reactive dog that can only go off-leash in a fenced area."
        ),
    )
    state = _state_after_mechanism_4(inferred_categories=[inferred])

    await interpretation.run_per_category_depth_calibration(state)

    assert state.inferred_categories[0].depth == "specific_attributes"
    assert state.inferred_categories[0].taxonomy_node == "park"


async def test_skip_is_logged_when_both_lists_are_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = FakeStructuredProvider(bodies=[])
    interpretation = _interpretation(provider)
    state = _state_after_mechanism_4(
        resolved_explicit_categories=[],
        inferred_categories=[],
        explicit_categories=[],
    )

    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        await interpretation.run_per_category_depth_calibration(state)

    assert "depth_assignment.skipped" in caplog.text
    assert "no_categories" in caplog.text
    assert provider.calls == []
