"""Manual, stage-by-stage run of Mechanism 4 against one real LLM call.

Not a test: it asserts nothing and writes nothing to disk. It seeds a Mechanism-2-style
`RequirementInterpretationState` (`state.resolved` already set) so Mechanism 1 and Mechanism 2
are not re-called. It then calls the Mechanism 4 stage methods in sequence rather than
`run_persona_driven_category_inference`, so every intermediate object can be printed. The raw
provider body is dropped inside execute, so a collecting log handler reads the attempt trail
and the raw body back off DEEP_SEARCH_LOGGER_NAME, the same technique the earlier runners use.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.category_inference_sample_run
"""

import asyncio
import json
import logging
import sys
from dataclasses import asdict

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import InferenceError
from src.services.deep_search.feature_prompts.inference_instruction import (
    build_inference_few_shot_examples,
)
from src.services.deep_search.feature_schemas.amenity_taxonomy import AMENITY_TAXONOMY_NODES
from src.services.deep_search.feature_schemas.schemas import (
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
    inferred_categories_json_schema,
)
from src.services.deep_search.requirement_interpretation import (
    LLM_PROVIDER_ATTEMPT_EVENT,
    LLM_PROVIDER_RAW_BODY_EVENT,
    _render_inference_user_content,
    _resolved_requirements_dict,
    create_requirement_interpretation,
)

_RULE = "=" * 78

_EXECUTE_STAGE = "execute_category_inference"

# Seeded as after Mechanism 2. Deliberately disjoint from the inference few-shots
# (those use gym/supermarket, child_care_agency, pharmacy, nightlife, fitness_center).
# Explicit nodes are a lane pool and an independent bookstore. Persona can support
# a dog-walking need and a prenatal clinic need; restaurants are negated.
_SAMPLE_PAYLOAD = PayloadRecord(
    normalized_text=(
        "We're looking at a flat near the river. I do lane swimming most weekdays before "
        "work, so a pool I can actually use for lengths matters, and my partner wants an "
        "independent bookstore she can walk to on Saturday mornings. We adopted a rescue "
        "dog last month and take it out twice a day. My partner is in the third trimester, "
        "so somewhere she can be seen quickly if something feels off would suddenly matter "
        "a lot more than it did six months ago. We cook at home and are not looking for "
        "restaurants."
    ),
    raw_text="(seeded Mechanism-2 state for the Mechanism 4 sample run)",
)

_SAMPLE_EXTRACTED = ExtractedRequirements(
    explicit_categories=[
        ExtractedCategory(
            category_id=0,
            name="a pool I can use for lengths",
            characteristics=["lane swimming", "before work"],
        ),
        ExtractedCategory(
            category_id=1,
            name="an independent bookstore",
            characteristics=["within a walk", "Saturday mornings"],
        ),
    ],
    ambiguity_flags=[
        AmbiguityFlag(
            phrase="independent",
            target="characteristic",
            category="an independent bookstore",
            characteristic="independent",
            category_id=None,
        ),
    ],
    persona_facts=[
        "adopted a rescue dog last month and walks it twice a day",
        "partner is in the third trimester",
        "cooks at home and is not looking for restaurants",
    ],
)


def _build_sample_state() -> RequirementInterpretationState:
    resolved = ResolvedRequirements(
        payload=_SAMPLE_PAYLOAD,
        resolved_explicit_categories=[
            ResolvedCategory(
                category_id=0,
                taxonomy_node="swimming_pool",
                raw_name="a pool I can use for lengths",
                characteristics=["lane swimming", "before work"],
                provenance="confident",
            ),
            ResolvedCategory(
                category_id=1,
                taxonomy_node="book_store",
                raw_name="an independent bookstore",
                characteristics=["within a walk", "Saturday mornings"],
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
    )


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


async def run_sample_inference() -> RequirementInterpretationState:
    """Run Mechanism 4 stages in order, printing what each one produced."""
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
        resolved_snapshot = _resolved_requirements_dict(resolved)

        _section("INPUT STATE")
        print(
            json.dumps(
                {
                    "payload": asdict(state.payload),
                    "extracted": state.extracted.model_dump(),
                    "resolved": resolved_snapshot,
                    "inferred_categories": [asdict(entry) for entry in state.inferred_categories],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(
            f"\nexplicit taxonomy nodes: "
            f"{[category.taxonomy_node for category in resolved.resolved_explicit_categories]}"
        )
        print(f"persona_facts: {len(resolved.persona_facts)}")
        print(f"inferred_categories (before): {len(state.inferred_categories)}")
        print("Mechanism 1 and Mechanism 2 were not called. This state is seeded after Mechanism 2.")

        json_schema = inferred_categories_json_schema()
        _section("STAGE 2 - SCHEMA")
        print(json.dumps(json_schema, indent=2))
        print(f"\nroot additionalProperties: {json_schema.get('additionalProperties')}")
        print(f"root required: {json_schema.get('required')}")
        inferred_prop = json_schema.get("properties", {}).get("inferred_categories", {})
        print(f"inferred_categories maxItems: {inferred_prop.get('maxItems')}")
        print(f"category_id in schema: {'category_id' in json.dumps(json_schema)}")

        instruction = interpretation.build_inference_instruction(json_schema)
        _section("STAGE 2 - INSTRUCTION")
        print(instruction)
        print(
            f"\ncharacters: {len(instruction)}   "
            f"taxonomy nodes: {len(AMENITY_TAXONOMY_NODES)}   "
            f"few-shot pairs: {len(build_inference_few_shot_examples())}"
        )

        _section("STAGE 3 - USER CONTENT")
        print(_render_inference_user_content(state))

        body = await interpretation.execute_category_inference(state, instruction)
        _section("STAGE 3 - PROVIDER ATTEMPTS")
        _print_attempts(collector)

        _section("STAGE 3 - VALIDATED")
        print(body.model_dump_json(indent=2))
        print(f"\ninferred_categories on wire: {len(body.inferred_categories)}")

        interpretation.write_inferred_categories(state, body)
        _section("STAGE 4 - INFERRED CATEGORIES")
        print(
            json.dumps(
                [asdict(entry) for entry in state.inferred_categories],
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"\nstored inferred_categories: {len(state.inferred_categories)}")
        print(
            f"category_ids: {[entry.category_id for entry in state.inferred_categories]}"
        )

        _section("STAGE 4 - RESOLVED UNCHANGED")
        print(json.dumps(_resolved_requirements_dict(resolved), indent=2, ensure_ascii=False))
        print(
            "\nresolved.* after write matches the pre-inference snapshot: "
            f"{_resolved_requirements_dict(resolved) == resolved_snapshot}"
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
        asyncio.run(run_sample_inference())
    except InferenceError as exc:
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
