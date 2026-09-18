"""Assembled-path checks for Mechanism 2's router and Component 2B.

No live provider calls. The fake StructuredLLMProvider returns recorded dicts; stdin is a
queued monkeypatch of input. State is seeded as after 2A pass 1 unless a test says otherwise.
"""

from __future__ import annotations

import copy

import pytest

from src.exceptions.deep_search import ClarificationValidationError
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_schemas.schemas import (
    CLARIFICATION_QUESTIONS_SCHEMA_NAME,
    FLAG_RESOLUTION_SCHEMA_NAME,
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
    UserResponse,
)
from src.services.deep_search.requirement_interpretation import (
    UserRequirementsInterpretation,
    _resolved_requirements_dict,
)

_SHOPPING_OPTIONS = [
    "a full supermarket for a weekly shop",
    "a small convenience store or corner shop",
    "a shopping mall with several stores",
    "a farmers market or specialist food shop",
    "other",
]
_PLAY_OPTIONS = [
    "a park with space to run or play sports",
    "a playground for children",
    "a sports complex or recreation centre",
    "an indoor play centre",
    "other",
]

_SHOPPING_QUESTION = {
    "category_id": 3,
    "category": "a place to get my shopping done",
    "question": (
        "When you say a place to get your shopping done, which of these is closest to "
        "what you meant?"
    ),
    "options": list(_SHOPPING_OPTIONS),
}
_PLAY_QUESTION = {
    "category_id": 4,
    "category": "a place to play",
    "question": "When you say a place to play, which of these is closest to what you meant?",
    "options": list(_PLAY_OPTIONS),
}

_CLARIFICATION_BODY = {"questions": [_SHOPPING_QUESTION, _PLAY_QUESTION]}
_INCOMPLETE_CLARIFICATION_BODY = {"questions": [_SHOPPING_QUESTION]}
_FLAG_RESOLUTION_BODY = {
    "resolved_categories": [
        {"taxonomy_node": "supermarket", "category_id": 3, "provenance": "confident"},
        {"taxonomy_node": "park", "category_id": 4, "provenance": "nearest_node"},
    ]
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
            "A well-equipped gym, a large grocery store, a place to get my shopping done, "
            "and a place to play."
        ),
        raw_text="seeded after 2A pass 1",
    )


def _extracted() -> ExtractedRequirements:
    return ExtractedRequirements(
        explicit_categories=[
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
            ExtractedCategory(
                category_id=3,
                name="a place to get my shopping done",
                characteristics=["without a long trip"],
            ),
            ExtractedCategory(
                category_id=4,
                name="a place to play",
                characteristics=["without a long trip"],
            ),
        ],
        ambiguity_flags=[
            AmbiguityFlag(
                phrase="a place to get my shopping done",
                target="category",
                category=None,
                characteristic=None,
                category_id=3,
            ),
            AmbiguityFlag(
                phrase="a place to play",
                target="category",
                category=None,
                characteristic=None,
                category_id=4,
            ),
            AmbiguityFlag(
                phrase="well-equipped",
                target="characteristic",
                category="well-equipped gym",
                characteristic="well-equipped",
                category_id=None,
            ),
        ],
        persona_facts=["cooks most nights", "likes sports"],
    )


def _state_after_pass_1(
    *,
    category_flags: bool = True,
    characteristic_only: bool = False,
    passes: int = 0,
) -> RequirementInterpretationState:
    payload = _payload()
    extracted = _extracted()
    flags: list[AmbiguityFlag]
    if characteristic_only:
        flags = [
            AmbiguityFlag(
                phrase="well-equipped",
                target="characteristic",
                category="well-equipped gym",
                characteristic="well-equipped",
                category_id=None,
            ),
            AmbiguityFlag(
                phrase="hybrid work",
                target="persona",
                category=None,
                characteristic=None,
                category_id=None,
            ),
        ]
    elif category_flags:
        flags = list(extracted.ambiguity_flags)
    else:
        flags = [
            flag for flag in extracted.ambiguity_flags if flag.target != "category"
        ]

    resolved = ResolvedRequirements(
        payload=payload,
        resolved_explicit_categories=[
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
        ],
        ambiguity_flags=flags,
        persona_facts=list(extracted.persona_facts),
    )
    return RequirementInterpretationState(
        payload=payload,
        extracted=extracted,
        resolved=resolved,
        category_resolution_passes=passes,
    )


def _interpretation(provider: FakeStructuredProvider) -> UserRequirementsInterpretation:
    return UserRequirementsInterpretation([provider])


def _queue_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(remaining))


def test_inspect_pass_1_category_flag_routes_to_2b() -> None:
    interpretation = _interpretation(FakeStructuredProvider())
    state = _state_after_pass_1()

    route = interpretation.inspect_category_resolution(state)

    assert route == "component_2b"
    assert state.category_resolution_passes == 1


def test_inspect_pass_1_characteristic_and_persona_only_routes_to_mechanism_3() -> None:
    interpretation = _interpretation(FakeStructuredProvider())
    state = _state_after_pass_1(characteristic_only=True)

    route = interpretation.inspect_category_resolution(state)

    assert route == "mechanism_3"
    assert state.category_resolution_passes == 1


async def test_after_2b_user_responses_keyed_by_submitted_category_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeStructuredProvider(bodies=[_CLARIFICATION_BODY])
    interpretation = _interpretation(provider)
    state = _state_after_pass_1()
    _queue_input(monkeypatch, ["1", "2"])

    await interpretation.clarify_unmapped_categories(state)

    assert set(state.user_responses) == {3, 4}
    assert all(isinstance(value, UserResponse) for value in state.user_responses.values())
    assert state.user_responses[3].response == _SHOPPING_OPTIONS[0]
    assert state.user_responses[4].response == _PLAY_OPTIONS[1]


async def test_after_2b_resolved_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeStructuredProvider(bodies=[_CLARIFICATION_BODY])
    interpretation = _interpretation(provider)
    state = _state_after_pass_1()
    snapshot = _resolved_requirements_dict(state.resolved)
    _queue_input(monkeypatch, ["1", "2"])

    await interpretation.clarify_unmapped_categories(state)

    assert _resolved_requirements_dict(state.resolved) == snapshot
    assert state.category_resolution_passes == 0


async def test_pass_2_second_inspect_is_mechanism_3_and_generate_is_not_called_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeStructuredProvider(
        bodies_by_schema={
            CLARIFICATION_QUESTIONS_SCHEMA_NAME: [_CLARIFICATION_BODY],
            FLAG_RESOLUTION_SCHEMA_NAME: [_FLAG_RESOLUTION_BODY],
        }
    )
    interpretation = _interpretation(provider)
    state = _state_after_pass_1()
    _queue_input(monkeypatch, ["1", "2"])

    assert interpretation.inspect_category_resolution(state) == "component_2b"
    await interpretation.clarify_unmapped_categories(state)
    await interpretation.resolve_category_flags(state)
    route = interpretation.inspect_category_resolution(state)

    assert route == "mechanism_3"
    assert state.category_resolution_passes == 2
    assert provider.calls.count(CLARIFICATION_QUESTIONS_SCHEMA_NAME) == 1
    assert not any(flag.target == "category" for flag in state.resolved.ambiguity_flags)


def test_hard_cap_routes_to_mechanism_3_even_with_a_category_flag() -> None:
    interpretation = _interpretation(FakeStructuredProvider())
    state = _state_after_pass_1(passes=1)

    route = interpretation.inspect_category_resolution(state)

    assert route == "mechanism_3"
    assert state.category_resolution_passes == 2
    assert any(flag.target == "category" for flag in state.resolved.ambiguity_flags)


async def test_coverage_retry_second_miss_raises_validation_error() -> None:
    provider = FakeStructuredProvider(
        bodies=[_INCOMPLETE_CLARIFICATION_BODY, _INCOMPLETE_CLARIFICATION_BODY]
    )
    interpretation = _interpretation(provider)
    state = _state_after_pass_1()
    instruction = interpretation.build_clarification_questions_instruction(
        {"type": "object"}
    )

    with pytest.raises(ClarificationValidationError) as exc_info:
        await interpretation.execute_clarification_questions(state, instruction)

    assert exc_info.value.stage == "execute_clarification_questions"
    assert provider.calls == [
        CLARIFICATION_QUESTIONS_SCHEMA_NAME,
        CLARIFICATION_QUESTIONS_SCHEMA_NAME,
    ]


async def test_other_path_stores_free_text_not_the_other_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    single_flag_body = {"questions": [_SHOPPING_QUESTION]}
    provider = FakeStructuredProvider(bodies=[single_flag_body])
    interpretation = _interpretation(provider)
    state = _state_after_pass_1()
    state.resolved.ambiguity_flags = [
        flag for flag in state.resolved.ambiguity_flags if flag.category_id == 3
    ]
    _queue_input(monkeypatch, ["5", "a weekly farmers market near the station"])

    await interpretation.clarify_unmapped_categories(state)

    stored = state.user_responses[3]
    assert stored.response == "a weekly farmers market near the station"
    assert stored.response != "other"
    assert stored.options[-1] == "other"
