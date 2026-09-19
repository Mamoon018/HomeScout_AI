"""Manual, stage-by-stage run of Mechanism 5 against one real LLM call.

Not a test: it asserts nothing and writes nothing to disk. It seeds a Mechanism-4-style
`RequirementInterpretationState` (`state.resolved` set, `inferred_categories` already
written, every `depth` is None) so Mechanisms 1–4 are not re-called. It then calls the
Mechanism 5 stage methods in sequence rather than `run_per_category_depth_calibration`, so
every intermediate object can be printed. The raw provider body is dropped inside execute,
so a collecting log handler reads the attempt trail and the raw body back off
DEEP_SEARCH_LOGGER_NAME, the same technique the earlier runners use.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.depth_assignment_sample_run
"""

import asyncio
import json
import logging
import sys
from dataclasses import asdict

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import DepthAssignmentError
from src.services.deep_search.feature_prompts.depth_assignment_instruction import (
    build_depth_assignment_few_shot_examples,
)
from src.services.deep_search.feature_schemas.schemas import (
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    InferredCategory,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
    depth_assignment_json_schema,
)
from src.services.deep_search.requirement_interpretation import (
    CATEGORY_RESOLUTION_ATTEMPT_EVENT,
    CATEGORY_RESOLUTION_RAW_BODY_EVENT,
    _render_depth_assignment_user_content,
    create_requirement_interpretation,
)

_RULE = "=" * 78

_EXECUTE_STAGE = "execute_depth_assignment"

# Seeded as after Mechanism 4. Deliberately disjoint from the depth few-shots
# (those use gym, supermarket, daycare, pharmacy, park, cafe).
_SAMPLE_PAYLOAD = PayloadRecord(
    normalized_text=(
        "We're looking at a flat near the canal. I climb indoors most weeknights and need "
        "a gym with beginner classes and auto-belay so I can go after a night shift without "
        "finding a partner. We shop the outdoor farmers market on Sunday mornings. We "
        "adopted a rescue cat last month that still needs its first round of vaccinations, "
        "and I work nights as a nurse so weekday daytime errands are hard."
    ),
    raw_text="(seeded Mechanism-4 state for the Mechanism 5 sample run)",
)

_SAMPLE_EXTRACTED = ExtractedRequirements(
    explicit_categories=[
        ExtractedCategory(
            category_id=0,
            name="a climbing gym with beginner classes and auto-belay",
            characteristics=["beginner classes", "auto-belay"],
        ),
        ExtractedCategory(
            category_id=1,
            name="the outdoor farmers market",
            characteristics=[],
        ),
    ],
    ambiguity_flags=[
        AmbiguityFlag(
            phrase="auto-belay",
            target="characteristic",
            category="a climbing gym with beginner classes and auto-belay",
            characteristic="auto-belay",
            category_id=None,
        ),
    ],
    persona_facts=[
        "works night shifts as a nurse",
        "adopted a rescue cat last month that still needs vaccinations",
        "shops outdoor markets on Sunday mornings",
    ],
)


def _build_sample_state() -> RequirementInterpretationState:
    resolved = ResolvedRequirements(
        payload=_SAMPLE_PAYLOAD,
        resolved_explicit_categories=[
            ResolvedCategory(
                category_id=0,
                taxonomy_node="climbing_gym",
                raw_name="a climbing gym with beginner classes and auto-belay",
                characteristics=["beginner classes", "auto-belay"],
                provenance="confident",
            ),
            ResolvedCategory(
                category_id=1,
                taxonomy_node="farmers_market",
                raw_name="the outdoor farmers market",
                characteristics=[],
                provenance="confident",
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
                taxonomy_node="veterinary_clinic",
                category_id=2,
                reasoning=(
                    "The persona fact that they adopted a rescue cat last month that "
                    "still needs its first round of vaccinations supports a veterinary "
                    "clinic as a distinct need from climbing_gym and farmers_market."
                ),
            )
        ],
    )


def _unchanged_fields_snapshot(state: RequirementInterpretationState) -> dict:
    resolved = state.resolved
    assert resolved is not None
    return {
        "explicit": [
            {
                "category_id": category.category_id,
                "taxonomy_node": category.taxonomy_node,
                "raw_name": category.raw_name,
                "characteristics": list(category.characteristics),
                "provenance": category.provenance,
            }
            for category in resolved.resolved_explicit_categories
        ],
        "inferred": [
            {
                "category_id": category.category_id,
                "taxonomy_node": category.taxonomy_node,
                "reasoning": category.reasoning,
            }
            for category in state.inferred_categories
        ],
        "persona_facts": list(resolved.persona_facts),
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


async def run_sample_depth_assignment() -> RequirementInterpretationState:
    """Run Mechanism 5 stages in order, printing what each one produced."""
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
                    "extracted": state.extracted.model_dump(),
                    "resolved_explicit_categories": [
                        asdict(category)
                        for category in resolved.resolved_explicit_categories
                    ],
                    "inferred_categories": [
                        asdict(entry) for entry in state.inferred_categories
                    ],
                    "persona_facts": list(resolved.persona_facts),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(
            f"\nexplicit depths before: "
            f"{[category.depth for category in resolved.resolved_explicit_categories]}"
        )
        print(
            f"inferred depths before: "
            f"{[entry.depth for entry in state.inferred_categories]}"
        )
        print(
            "Mechanism 1 through Mechanism 4 were not called. "
            "This state is seeded after Mechanism 4."
        )

        json_schema = depth_assignment_json_schema()
        _section("STAGE - SCHEMA")
        print(json.dumps(json_schema, indent=2))
        print(f"\nroot additionalProperties: {json_schema.get('additionalProperties')}")
        print(f"root required: {json_schema.get('required')}")
        schema_text = json.dumps(json_schema)
        print(f"depth enum present: {'basic_profile' in schema_text}")
        print(f"metric fields in schema: {'label' in schema_text and 'value_type' in schema_text}")

        instruction = interpretation.build_depth_assignment_instruction(json_schema)
        _section("STAGE - INSTRUCTION")
        print(instruction)
        print(
            f"\ncharacters: {len(instruction)}   "
            f"few-shot pairs: {len(build_depth_assignment_few_shot_examples())}"
        )

        _section("STAGE - USER CONTENT")
        print(_render_depth_assignment_user_content(state))

        body = await interpretation.execute_depth_assignment(state, instruction)
        _section("STAGE - PROVIDER ATTEMPTS")
        _print_attempts(collector)

        _section("STAGE - VALIDATED")
        print(body.model_dump_json(indent=2))
        print(f"\nassignments on wire: {len(body.assignments)}")

        interpretation.stamp_category_depths(state, body)
        _section("STAGE - STAMPED DEPTHS")
        print(
            json.dumps(
                {
                    "explicit": [
                        {
                            "category_id": category.category_id,
                            "taxonomy_node": category.taxonomy_node,
                            "depth": category.depth,
                        }
                        for category in resolved.resolved_explicit_categories
                    ],
                    "inferred": [
                        {
                            "category_id": entry.category_id,
                            "taxonomy_node": entry.taxonomy_node,
                            "depth": entry.depth,
                        }
                        for entry in state.inferred_categories
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        _section("STAGE - UNCHANGED FIELDS")
        after = _unchanged_fields_snapshot(state)
        print(json.dumps(after, indent=2, ensure_ascii=False))
        print(
            "\ntaxonomy_node / characteristics / reasoning / persona_facts / payload "
            f"match the pre-stamp snapshot: {after == unchanged_snapshot}"
        )
        return state
    finally:
        await interpretation.aclose()


def _print_attempts(collector: _RecordCollector) -> None:
    for attempt in collector.events(CATEGORY_RESOLUTION_ATTEMPT_EVENT):
        if attempt.get("stage") != _EXECUTE_STAGE:
            continue
        line = f"{attempt['provider']} ({attempt['model']}): {attempt['outcome']}"
        detail = attempt.get("detail")
        print(f"{line} - {detail}" if detail else line)
    for answer in collector.events(CATEGORY_RESOLUTION_RAW_BODY_EVENT):
        if answer.get("stage") != _EXECUTE_STAGE:
            continue
        print(f"\nraw decoded body from {answer['provider']}:")
        print(json.dumps(answer["body"], indent=2, ensure_ascii=False))


def main() -> int:
    try:
        asyncio.run(run_sample_depth_assignment())
    except DepthAssignmentError as exc:
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
