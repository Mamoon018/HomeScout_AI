"""Manual, stage-by-stage run of Mechanism 6 against one real LLM call.

Not a test: it asserts nothing and writes nothing to disk. It seeds a Mechanism-5-style
`RequirementInterpretationState` (`state.resolved` set, `inferred_categories` written, every
`depth` stamped, `category_metrics` empty) so Mechanisms 1-5 are not re-called. It then calls
the Mechanism 6 stage methods in sequence rather than `run_per_category_metric_definition`,
so every intermediate object can be printed. The raw provider body is dropped inside execute,
so a collecting log handler reads the attempt trail and the raw body back off
DEEP_SEARCH_LOGGER_NAME, the same technique the earlier runners use.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.metric_definition_sample_run
"""

import asyncio
import json
import logging
import sys
from dataclasses import asdict

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import MetricDefinitionError
from src.services.deep_search.feature_prompts.metric_definition_instruction import (
    build_metric_definition_few_shot_examples,
)
from src.services.deep_search.feature_schemas.schemas import (
    FIXED_DIMENSIONS_BY_DEPTH,
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    InferredCategory,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
    metric_definition_json_schema,
)
from src.services.deep_search.requirement_interpretation import (
    LLM_PROVIDER_ATTEMPT_EVENT,
    LLM_PROVIDER_RAW_BODY_EVENT,
    _render_metric_definition_user_content,
    create_requirement_interpretation,
)

_RULE = "=" * 78

_EXECUTE_STAGE = "execute_metric_definition"

# Seeded as after Mechanism 5. Deliberately disjoint from the metric few-shots
# (those use restaurant, gym, dentist, hair_salon).
_SAMPLE_PAYLOAD = PayloadRecord(
    normalized_text=(
        "We're moving into a flat near the river. I swim laps most mornings, so I need a "
        "pool with lap lanes open before 6am and water that is not too warm, and I would "
        "like it not too crowded. I buy bread from a bakery on the way home from the pool. "
        "We adopted a puppy last month that needs off-leash time and somewhere to burn "
        "energy, and our teenage daughter studies in the evenings and would like somewhere "
        "quiet to work."
    ),
    raw_text="(seeded Mechanism-5 state for the Mechanism 6 sample run)",
)

_SAMPLE_EXTRACTED = ExtractedRequirements(
    explicit_categories=[
        ExtractedCategory(
            category_id=0,
            name="a swimming pool with lap lanes open before 6am and cool water",
            characteristics=["lap lanes open before 6am", "water not too warm"],
        ),
        ExtractedCategory(
            category_id=1,
            name="a bakery on the way home from the pool",
            characteristics=[],
        ),
    ],
    ambiguity_flags=[
        AmbiguityFlag(
            phrase="not too crowded",
            target="characteristic",
            category="a swimming pool with lap lanes open before 6am and cool water",
            characteristic="not too crowded",
            category_id=None,
        ),
    ],
    persona_facts=[
        "swims laps most mornings",
        "adopted a puppy last month that needs off-leash time",
        "has a teenage daughter who studies in the evenings",
    ],
)


def _build_sample_state() -> RequirementInterpretationState:
    resolved = ResolvedRequirements(
        payload=_SAMPLE_PAYLOAD,
        resolved_explicit_categories=[
            ResolvedCategory(
                category_id=0,
                taxonomy_node="swimming_pool",
                raw_name="a swimming pool with lap lanes open before 6am and cool water",
                characteristics=["lap lanes open before 6am", "water not too warm"],
                provenance="confident",
                depth="specific_attributes",
            ),
            ResolvedCategory(
                category_id=1,
                taxonomy_node="bakery",
                raw_name="a bakery on the way home from the pool",
                characteristics=[],
                provenance="confident",
                depth="operating_details",
            ),
        ],
        ambiguity_flags=list(_SAMPLE_EXTRACTED.ambiguity_flags),
        persona_facts=list(_SAMPLE_EXTRACTED.persona_facts),
    )
    return RequirementInterpretationState(
        payload=_SAMPLE_PAYLOAD,
        extracted=_SAMPLE_EXTRACTED,
        resolved=resolved,
        inferred_categories=[
            InferredCategory(
                taxonomy_node="dog_park",
                category_id=2,
                reasoning=(
                    "The persona fact that they adopted a puppy last month that needs "
                    "off-leash time and somewhere to burn energy supports a dog park as a "
                    "distinct need from swimming_pool and bakery."
                ),
                depth="operating_details",
            ),
            InferredCategory(
                taxonomy_node="library",
                category_id=3,
                reasoning=(
                    "The persona fact that their teenage daughter studies in the evenings "
                    "and would like somewhere quiet to work supports a library as a "
                    "distinct need from swimming_pool and bakery."
                ),
                depth="basic_profile",
            ),
        ],
    )


def _unchanged_fields_snapshot(state: RequirementInterpretationState) -> dict:
    resolved = state.resolved
    assert resolved is not None
    return {
        "explicit": [asdict(category) for category in resolved.resolved_explicit_categories],
        "inferred": [asdict(category) for category in state.inferred_categories],
        "persona_facts": list(resolved.persona_facts),
        "ambiguity_flags": [flag.model_dump() for flag in resolved.ambiguity_flags],
        "payload": asdict(state.payload),
    }


class _RecordCollector(logging.Handler):
    """Keeps the service's structured records so this script can print the attempt trail."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass

    def events(self, *names: str) -> list[dict]:
        return [record for record in self.records if record.get("event") in names]


async def run_sample_metric_definition() -> RequirementInterpretationState:
    """Run Mechanism 6 stages in order, printing what each one produced."""
    settings = get_settings()
    configure_logging(settings.log_level)

    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    interpretation = create_requirement_interpretation(settings)
    try:
        state = _build_sample_state()
        resolved = state.resolved
        assert resolved is not None
        unchanged_snapshot = _unchanged_fields_snapshot(state)

        _section("INPUT STATE")
        print(
            json.dumps(
                {
                    "payload": asdict(state.payload),
                    "resolved_explicit_categories": [
                        asdict(category)
                        for category in resolved.resolved_explicit_categories
                    ],
                    "inferred_categories": [
                        asdict(entry) for entry in state.inferred_categories
                    ],
                    "persona_facts": list(resolved.persona_facts),
                    "leftover_flags": [
                        flag.model_dump() for flag in resolved.ambiguity_flags
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"\ncategory_metrics before: {state.category_metrics}")
        print(
            "Mechanism 1 through Mechanism 5 were not called. "
            "This state is seeded after Mechanism 5."
        )

        json_schema = metric_definition_json_schema()
        _section("STAGE - SCHEMA")
        print(json.dumps(json_schema, indent=2))
        schema_text = json.dumps(json_schema)
        print(f"\nroot additionalProperties: {json_schema.get('additionalProperties')}")
        print(f"root required: {json_schema.get('required')}")
        unsupported = [
            key
            for key in ("minLength", "maxLength", "minItems", "maxItems", "if", "oneOf")
            if f'"{key}"' in schema_text
        ]
        print(f"length / count / conditional keys present: {unsupported}")

        _section("STAGE - FIXED DIMENSIONS")
        print(json.dumps(FIXED_DIMENSIONS_BY_DEPTH, indent=2))

        instruction = interpretation.build_metric_definition_instruction(json_schema)
        _section("STAGE - INSTRUCTION")
        print(instruction)
        print(
            f"\ncharacters: {len(instruction)}   "
            f"few-shot pairs: {len(build_metric_definition_few_shot_examples())}"
        )

        _section("STAGE - USER CONTENT")
        print(_render_metric_definition_user_content(state))

        body = await interpretation.execute_metric_definition(state, instruction)
        _section("STAGE - PROVIDER ATTEMPTS")
        _print_attempts(collector)

        _section("STAGE - VALIDATED")
        print(body.model_dump_json(indent=2))
        print(
            "\nmetrics on wire per category: "
            f"{ {entry.category_id: len(entry.metrics) for entry in body.categories} }"
        )

        survivors, rejections = interpretation.apply_metric_contract(state, body)
        _section("STAGE - CONTRACT FILTER")
        print(
            json.dumps(
                {
                    "survivors": {
                        str(category_id): [asdict(metric) for metric in metrics]
                        for category_id, metrics in survivors.items()
                    },
                    "rejections": rejections,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        shortfalls = interpretation.report_metric_shortfalls(state, survivors)
        _section("STAGE - SHORTFALLS")
        print(json.dumps(shortfalls, indent=2, ensure_ascii=False))
        if not shortfalls:
            print("no eligible category is missing a required band")

        interpretation.write_category_metrics(state, survivors)
        _section("STAGE - WRITTEN METRIC SETS")
        print(
            json.dumps(
                [asdict(metric_set) for metric_set in state.category_metrics],
                indent=2,
                ensure_ascii=False,
            )
        )
        print(
            "\nmetrics per set: "
            f"{ {item.category_id: (None if item.metrics is None else len(item.metrics)) for item in state.category_metrics} }"
        )

        _section("STAGE - UNCHANGED FIELDS")
        after = _unchanged_fields_snapshot(state)
        print(json.dumps(after, indent=2, ensure_ascii=False))
        print(
            "\ncategories / persona_facts / leftover flags / payload "
            f"match the pre-write snapshot: {after == unchanged_snapshot}"
        )
        return state
    finally:
        await interpretation.aclose()


def _print_attempts(collector: _RecordCollector) -> None:
    for attempt in collector.events(LLM_PROVIDER_ATTEMPT_EVENT):
        if attempt.get("stage") != _EXECUTE_STAGE:
            continue
        line = f"{attempt['provider']} ({attempt['model']}): {attempt['outcome']}"
        detail = attempt.get("detail")
        print(f"{line} - {detail}" if detail else line)
    for answer in collector.events(LLM_PROVIDER_RAW_BODY_EVENT):
        if answer.get("stage") != _EXECUTE_STAGE:
            continue
        print(f"\nraw decoded body from {answer['provider']}:")
        print(json.dumps(answer["body"], indent=2, ensure_ascii=False))


def main() -> int:
    try:
        asyncio.run(run_sample_metric_definition())
    except MetricDefinitionError as exc:
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {exc.stage}")
        print(f"message:   {exc}")
        return 1
    return 0


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


if __name__ == "__main__":
    sys.exit(main())
