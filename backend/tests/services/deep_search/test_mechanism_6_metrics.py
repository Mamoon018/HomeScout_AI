"""Assembled-path checks for Mechanism 6 per-category metric definition.

No live provider calls. The fake StructuredLLMProvider returns recorded dicts. State is
seeded as after Mechanism 5 (`resolved` set, `inferred_categories` written, `depth` stamped,
`category_metrics` empty) unless a test says otherwise.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict

import pytest

from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import (
    MetricDefinitionProviderError,
    MetricDefinitionValidationError,
)
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_schemas.schemas import (
    FIXED_DIMENSIONS_BY_DEPTH,
    MAX_METRICS_PER_BAND,
    METRIC_DEFINITION_SCHEMA_NAME,
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    InferredCategory,
    MetricSpec,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
    metric_definition_json_schema,
)
from src.services.deep_search.feature_prompts.metric_definition_instruction import (
    build_metric_definition_instruction,
)
from src.services.deep_search.requirement_interpretation import UserRequirementsInterpretation


class FakeStructuredProvider:
    """Returns recorded bodies in order; raises LLMProviderError when none are left."""

    name = "fake"
    model = "fake-model"

    def __init__(self, *, bodies: list[dict] | None = None) -> None:
        self.calls: list[str] = []
        self.last_user_content: str | None = None
        self._queue = [copy.deepcopy(body) for body in (bodies or [])]

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
        if not self._queue:
            raise LLMProviderError("no recorded body left")
        return self._queue.pop(0)

    async def aclose(self) -> None:
        return None


def _metric(label: str = "Service speed", **overrides) -> dict:
    metric = {
        "label": label,
        "question": (
            "The customer explicitly asked for this category: is service usually slow "
            "or fast?"
        ),
        "value_type": "enum",
        "unit": None,
        "enum_values": ["slow", "mixed", "fast"],
        "resolution_source": {
            "tool": "parallel_web_search",
            "target": "review mentions of wait time",
        },
        "verification": "dominant sentiment across at least 5 reviews mentioning wait time",
        "null_policy": "unknown",
        "band": "operating_details",
    }
    metric.update(overrides)
    return metric


def _specific_metric(label: str = "Dedicated platform present", **overrides) -> dict:
    return _metric(
        label,
        question="The customer named a platform as a requirement: does the gym have one?",
        value_type="boolean",
        enum_values=[],
        resolution_source={"tool": "firecrawl", "target": "facilities page on the official site"},
        verification="listed on the official facilities page",
        band="specific_attributes",
        **overrides,
    )


def _entry(category_id: int, *metrics: dict) -> dict:
    return {"category_id": category_id, "metrics": [copy.deepcopy(m) for m in metrics]}


def _body(*entries: dict) -> dict:
    return {"categories": [copy.deepcopy(entry) for entry in entries]}


def _payload() -> PayloadRecord:
    return PayloadRecord(
        normalized_text=(
            "A gym with a platform I can use before work, a large grocery store, and we "
            "have a four-year-old who needs care during the workday."
        ),
        raw_text="seeded after Mechanism 5",
    )


def _resolved_categories() -> list[ResolvedCategory]:
    return [
        ResolvedCategory(
            category_id=0,
            taxonomy_node="gym",
            raw_name="gym with a platform",
            characteristics=["platform"],
            provenance="confident",
            depth="specific_attributes",
        ),
        ResolvedCategory(
            category_id=1,
            taxonomy_node="supermarket",
            raw_name="large grocery store",
            characteristics=[],
            provenance="confident",
            depth="operating_details",
        ),
    ]


def _inferred(depth: str = "basic_profile", node: str = "daycare") -> InferredCategory:
    return InferredCategory(
        taxonomy_node=node,
        category_id=2,
        reasoning=(
            "The persona fact that they have a four-year-old who needs care during the "
            "workday supports this category as a distinct need."
        ),
        depth=depth,
    )


def _state_after_mechanism_5(
    *,
    resolved_explicit_categories: list[ResolvedCategory] | None = None,
    inferred_categories: list[InferredCategory] | None = None,
    ambiguity_flags: list[AmbiguityFlag] | None = None,
) -> RequirementInterpretationState:
    payload = _payload()
    if resolved_explicit_categories is None:
        resolved_explicit_categories = _resolved_categories()
    if inferred_categories is None:
        inferred_categories = [_inferred()]
    extracted = ExtractedRequirements(
        explicit_categories=[
            ExtractedCategory(
                category_id=category.category_id,
                name=category.raw_name,
                characteristics=list(category.characteristics),
            )
            for category in resolved_explicit_categories
        ],
        ambiguity_flags=[],
        persona_facts=["has a four-year-old who needs care during the workday"],
    )
    resolved = ResolvedRequirements(
        payload=payload,
        resolved_explicit_categories=resolved_explicit_categories,
        ambiguity_flags=list(ambiguity_flags or []),
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


def _metric_map(state: RequirementInterpretationState) -> dict[int, list[MetricSpec] | None]:
    return {item.category_id: item.metrics for item in state.category_metrics}


def _labels(state: RequirementInterpretationState, category_id: int) -> list[str]:
    metrics = _metric_map(state)[category_id]
    assert metrics is not None
    return [metric.label for metric in metrics]


def _snapshot(state: RequirementInterpretationState) -> dict:
    resolved = state.resolved
    assert resolved is not None
    return {
        "explicit": [asdict(category) for category in resolved.resolved_explicit_categories],
        "inferred": [asdict(entry) for entry in state.inferred_categories],
        "persona_facts": list(resolved.persona_facts),
        "ambiguity_flags": [flag.model_dump() for flag in resolved.ambiguity_flags],
        "payload": asdict(state.payload),
        "extracted": state.extracted.model_dump(),
        "user_responses": dict(state.user_responses),
        "passes": state.category_resolution_passes,
    }


async def test_both_lists_empty_skips_provider_and_leaves_no_sets() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_entry(0, _metric()))])
    state = _state_after_mechanism_5(
        resolved_explicit_categories=[], inferred_categories=[]
    )

    result = await _interpretation(provider).run_per_category_metric_definition(state)

    assert result.category_metrics == []
    assert provider.calls == []


async def test_all_basic_profile_skips_provider_and_writes_none_sets() -> None:
    provider = FakeStructuredProvider(bodies=[_body(_entry(0, _metric()))])
    explicit = _resolved_categories()
    for category in explicit:
        category.depth = "basic_profile"  # only for this seed; M5 rejects it in the real path
    state = _state_after_mechanism_5(
        resolved_explicit_categories=explicit, inferred_categories=[_inferred()]
    )

    await _interpretation(provider).run_per_category_metric_definition(state)

    assert provider.calls == []
    assert [item.category_id for item in state.category_metrics] == [0, 1, 2]
    assert all(item.metrics is None for item in state.category_metrics)


async def test_skip_is_logged_with_reason(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeStructuredProvider(bodies=[])
    empty = _state_after_mechanism_5(resolved_explicit_categories=[], inferred_categories=[])

    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        await _interpretation(provider).run_per_category_metric_definition(empty)

    assert "metric_definition.skipped" in caplog.text
    assert "no_categories" in caplog.text


async def test_valid_mixed_batch_writes_sets_by_id_in_explicit_then_inferred_order() -> None:
    provider = FakeStructuredProvider(
        bodies=[
            _body(
                _entry(0, _metric("Monthly fee", value_type="number_with_unit", unit="USD", enum_values=[]), _specific_metric()),
                _entry(1, _metric()),
                _entry(2, _metric("New-patient wait", value_type="number_with_unit", unit="days", enum_values=[])),
            )
        ]
    )
    state = _state_after_mechanism_5(inferred_categories=[_inferred("operating_details")])

    await _interpretation(provider).run_per_category_metric_definition(state)

    assert provider.calls == [METRIC_DEFINITION_SCHEMA_NAME]
    assert [(s.category_id, s.taxonomy_node) for s in state.category_metrics] == [
        (0, "gym"),
        (1, "supermarket"),
        (2, "daycare"),
    ]
    assert _labels(state, 0) == ["Monthly fee", "Dedicated platform present"]
    assert _labels(state, 1) == ["Service speed"]
    assert _labels(state, 2) == ["New-patient wait"]
    stored = _metric_map(state)[0]
    assert stored is not None
    assert stored[1].resolution_source.tool == "firecrawl"
    assert stored[1].band == "specific_attributes"


async def test_basic_profile_category_is_not_sent_and_gets_none() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric(), _specific_metric()), _entry(1, _metric()))]
    )
    state = _state_after_mechanism_5()

    await _interpretation(provider).run_per_category_metric_definition(state)

    sent = json.loads(provider.last_user_content or "{}")
    assert [row["category_id"] for row in sent["categories"]] == [0, 1]
    assert _metric_map(state)[2] is None
    assert _metric_map(state)[0] is not None


async def test_user_content_carries_origin_depth_and_leftover_flags_only() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric(), _specific_metric()), _entry(1, _metric()), _entry(2, _metric()))]
    )
    flags = [
        AmbiguityFlag(
            phrase="not too crowded",
            target="characteristic",
            category="gym with a platform",
            characteristic="not too crowded",
        ),
        AmbiguityFlag(phrase="usually busy", target="persona"),
        AmbiguityFlag(phrase="a spot to eat", target="category", category_id=9),
    ]
    state = _state_after_mechanism_5(
        inferred_categories=[_inferred("operating_details")], ambiguity_flags=flags
    )

    await _interpretation(provider).run_per_category_metric_definition(state)

    sent = json.loads(provider.last_user_content or "{}")
    rows = {row["category_id"]: row for row in sent["categories"]}
    assert rows[0]["origin"] == "explicit" and rows[0]["depth"] == "specific_attributes"
    assert rows[0]["characteristics"] == ["platform"]
    assert rows[2]["origin"] == "inferred" and rows[2]["depth"] == "operating_details"
    assert "reasoning" in rows[2]
    assert [flag["phrase"] for flag in sent["leftover_flags"]] == ["not too crowded", "usually busy"]
    assert sent["persona_facts"] == ["has a four-year-old who needs care during the workday"]


async def test_missing_field_rejects_whole_body_without_writing() -> None:
    bad = _metric()
    del bad["verification"]
    provider = FakeStructuredProvider(bodies=[_body(_entry(0, bad), _entry(1, _metric()))])
    state = _state_after_mechanism_5(inferred_categories=[])

    with pytest.raises(MetricDefinitionValidationError) as exc_info:
        await _interpretation(provider).run_per_category_metric_definition(state)

    assert exc_info.value.stage == "execute_metric_definition"
    assert state.category_metrics == []


@pytest.mark.parametrize(
    "override",
    [
        {"band": "deep_dive"},
        {"value_type": "prose"},
        {"null_policy": "guess"},
        {"resolution_source": {"tool": "diffbot", "target": "any page"}},
    ],
)
async def test_value_outside_a_closed_set_rejects_whole_body(override: dict) -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric(**override)), _entry(1, _metric()))]
    )
    state = _state_after_mechanism_5(inferred_categories=[])

    with pytest.raises(MetricDefinitionValidationError):
        await _interpretation(provider).run_per_category_metric_definition(state)

    assert state.category_metrics == []


async def test_extra_key_rejects_whole_body() -> None:
    bad = _metric(depth="operating_details")
    provider = FakeStructuredProvider(bodies=[_body(_entry(0, bad), _entry(1, _metric()))])
    state = _state_after_mechanism_5(inferred_categories=[])

    with pytest.raises(MetricDefinitionValidationError):
        await _interpretation(provider).run_per_category_metric_definition(state)


@pytest.mark.parametrize(
    "entries",
    [
        [_entry(0, _metric())],
        [_entry(0, _metric()), _entry(1, _metric()), _entry(9, _metric())],
        [_entry(0, _metric()), _entry(1, _metric()), _entry(0, _metric())],
    ],
    ids=["missing_id", "extra_id", "duplicate_id"],
)
async def test_id_set_mismatch_rejects_whole_body_without_writing(entries: list[dict]) -> None:
    provider = FakeStructuredProvider(bodies=[_body(*entries)])
    state = _state_after_mechanism_5(inferred_categories=[])

    with pytest.raises(MetricDefinitionValidationError) as exc_info:
        await _interpretation(provider).run_per_category_metric_definition(state)

    assert exc_info.value.stage == "execute_metric_definition"
    assert state.category_metrics == []


async def test_basic_profile_id_in_body_is_an_extra_id() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric()), _entry(1, _metric()), _entry(2, _metric()))]
    )
    state = _state_after_mechanism_5()  # id 2 is basic_profile, so not submitted

    with pytest.raises(MetricDefinitionValidationError):
        await _interpretation(provider).run_per_category_metric_definition(state)


async def test_no_provider_answers_raises_provider_error() -> None:
    provider = FakeStructuredProvider(bodies=[])
    state = _state_after_mechanism_5(inferred_categories=[])

    with pytest.raises(MetricDefinitionProviderError) as exc_info:
        await _interpretation(provider).run_per_category_metric_definition(state)

    assert exc_info.value.stage == "execute_metric_definition"
    assert state.category_metrics == []


@pytest.mark.parametrize(
    ("bad", "rule"),
    [
        (_metric("Blank question", question="   "), "text_completeness"),
        (
            _metric("Blank target", resolution_source={"tool": "google_maps", "target": " "}),
            "text_completeness",
        ),
        (
            _metric("No unit", value_type="number_with_unit", unit=None, enum_values=[]),
            "value_type_parameters",
        ),
        (_metric("One value", enum_values=["only"]), "value_type_parameters"),
        (
            _metric("Boolean with unit", value_type="boolean", unit="x", enum_values=[]),
            "value_type_parameters",
        ),
        (
            _metric("Fetched page for quality", resolution_source={"tool": "firecrawl", "target": "reviews page"}),
            "tool_not_allowed_for_band",
        ),
    ],
    ids=["K1_question", "K1_target", "K2_no_unit", "K2_one_enum_value", "K2_boolean_unit", "K4_firecrawl"],
)
async def test_failing_metric_is_dropped_and_neighbor_is_kept(bad: dict, rule: str) -> None:
    good = _metric("Neighbor")
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, bad, good, _specific_metric()), _entry(1, _metric()))]
    )
    state = _state_after_mechanism_5(inferred_categories=[])
    interpretation = _interpretation(provider)

    body = await interpretation.execute_metric_definition(
        state, interpretation.build_metric_definition_instruction(metric_definition_json_schema())
    )
    survivors, rejections = interpretation.apply_metric_contract(state, body)

    assert [m.label for m in survivors[0]] == ["Neighbor", "Dedicated platform present"]
    assert rejections == [{"category_id": 0, "label": bad["label"], "rule": rule}]


async def test_specific_band_on_operating_details_category_is_dropped() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric()), _entry(1, _specific_metric("Too deep"), _metric("Kept")))]
    )
    state = _state_after_mechanism_5(inferred_categories=[])

    await _interpretation(provider).run_per_category_metric_definition(state)

    assert _labels(state, 1) == ["Kept"]


async def test_duplicate_label_keeps_first_and_drops_later_case_insensitively() -> None:
    provider = FakeStructuredProvider(
        bodies=[
            _body(
                _entry(0, _metric("Service Speed"), _metric("  service speed "), _specific_metric()),
                _entry(1, _metric()),
            )
        ]
    )
    state = _state_after_mechanism_5(inferred_categories=[])
    interpretation = _interpretation(provider)

    body = await interpretation.execute_metric_definition(
        state, interpretation.build_metric_definition_instruction(metric_definition_json_schema())
    )
    survivors, rejections = interpretation.apply_metric_contract(state, body)

    assert [m.label for m in survivors[0]] == ["Service Speed", "Dedicated platform present"]
    assert [r["rule"] for r in rejections] == ["duplicate_label"]


async def test_band_cap_keeps_first_four_in_order_and_counts_bands_separately() -> None:
    operating = [_metric(f"Quality {index}") for index in range(MAX_METRICS_PER_BAND + 1)]
    specific = [_specific_metric(f"Attribute {index}") for index in range(MAX_METRICS_PER_BAND)]
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, *operating, *specific), _entry(1, _metric()))]
    )
    state = _state_after_mechanism_5(inferred_categories=[])
    interpretation = _interpretation(provider)

    body = await interpretation.execute_metric_definition(
        state, interpretation.build_metric_definition_instruction(metric_definition_json_schema())
    )
    survivors, rejections = interpretation.apply_metric_contract(state, body)

    assert [m.label for m in survivors[0]] == [
        "Quality 0", "Quality 1", "Quality 2", "Quality 3",
        "Attribute 0", "Attribute 1", "Attribute 2", "Attribute 3",
    ]
    assert rejections == [{"category_id": 0, "label": "Quality 4", "rule": "band_cap"}]


async def test_rejections_are_logged_with_rule(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric("Bad", question=" "), _specific_metric()), _entry(1, _metric()))]
    )
    state = _state_after_mechanism_5(inferred_categories=[])

    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        await _interpretation(provider).run_per_category_metric_definition(state)

    assert "metric_definition.metric_rejected" in caplog.text
    assert "text_completeness" in caplog.text


async def test_category_left_without_a_required_band_is_reported_not_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Gym is specific_attributes: only an operating metric survives, so its specific band is empty.
    # Supermarket loses its only metric, so it is left with an empty list.
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric()), _entry(1, _metric("Bad", question="")))]
    )
    state = _state_after_mechanism_5(inferred_categories=[])

    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        await _interpretation(provider).run_per_category_metric_definition(state)

    assert _metric_map(state)[1] == []
    assert _labels(state, 0) == ["Service speed"]
    assert "metric_definition.category_underspecified" in caplog.text
    assert '"empty_bands": ["specific_attributes"]' in caplog.text
    assert '"empty_bands": ["operating_details"]' in caplog.text


async def test_valid_metric_is_stored_unchanged_apart_from_trimmed_text() -> None:
    padded = _metric("  Service speed  ", verification="  five reviews agree  ")
    provider = FakeStructuredProvider(bodies=[_body(_entry(0, padded, _specific_metric()), _entry(1, _metric()))])
    state = _state_after_mechanism_5(inferred_categories=[])

    await _interpretation(provider).run_per_category_metric_definition(state)

    stored = _metric_map(state)[0]
    assert stored is not None
    assert stored[0].label == "Service speed"
    assert stored[0].verification == "five reviews agree"
    assert stored[0].enum_values == ["slow", "mixed", "fast"]
    assert stored[0].unit is None
    assert stored[0].null_policy == "unknown"


async def test_categories_and_other_state_are_unchanged() -> None:
    provider = FakeStructuredProvider(
        bodies=[_body(_entry(0, _metric(), _specific_metric()), _entry(1, _metric()), _entry(2, _metric()))]
    )
    state = _state_after_mechanism_5(inferred_categories=[_inferred("operating_details")])
    before = _snapshot(state)

    await _interpretation(provider).run_per_category_metric_definition(state)

    assert _snapshot(state) == before
    assert len(state.category_metrics) == 3


def test_schema_carries_only_closed_objects_and_enums() -> None:
    schema = metric_definition_json_schema()
    text = json.dumps(schema)

    for keyword in ("minLength", "maxLength", "minItems", "maxItems", "if", "oneOf"):
        assert f'"{keyword}"' not in text
    metric = schema["$defs"]["MetricEntry"]
    assert metric["additionalProperties"] is False
    assert set(metric["required"]) == set(metric["properties"])
    assert schema["additionalProperties"] is False


def test_instruction_lists_fixed_dimensions_cap_and_tools() -> None:
    instruction = build_metric_definition_instruction(metric_definition_json_schema())

    for dimension in FIXED_DIMENSIONS_BY_DEPTH["specific_attributes"]:
        assert dimension in instruction
    assert FIXED_DIMENSIONS_BY_DEPTH["basic_profile"][3] == "website"
    assert f"At most {MAX_METRICS_PER_BAND} metrics per band" in instruction
    assert "firecrawl" in instruction and "parallel_web_search" in instruction
    assert "diffbot" not in instruction.lower()
