"""Manual, stage-by-stage run of Mechanism 2 Component 2A against real LLM calls.

Not a test: it asserts nothing and writes nothing to disk. It seeds a Mechanism-1-style
`RequirementInterpretationState` (so no re-parse is needed) and calls the Component 2A stage
methods in sequence rather than `resolve_explicit_categories`, so every intermediate object
can be printed. The raw provider body is dropped inside the execute stages, so a collecting
log handler reads the attempt trail and the raw body back off DEEP_SEARCH_LOGGER_NAME, the
same technique the Mechanism 1 runner uses.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run
    python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run \
        --with-responses
"""

import argparse
import json
import logging
import sys

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import CategoryResolutionError
from src.services.deep_search.feature_prompts.category_resolution_instruction import (
    build_mapping_few_shot_examples,
    build_resolution_few_shot_examples,
)
from src.services.deep_search.feature_schemas.amenity_taxonomy import AMENITY_TAXONOMY_NODES
from src.services.deep_search.feature_schemas.schemas import (
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
    UserResponse,
    flag_resolution_json_schema,
    taxonomy_mapping_json_schema,
)
from src.services.deep_search.requirement_interpretation import (
    CATEGORY_RESOLUTION_ATTEMPT_EVENT,
    CATEGORY_RESOLUTION_RAW_BODY_EVENT,
    _resolved_requirements_dict,
    create_requirement_interpretation,
)

_RULE = "=" * 78

# A Mechanism-1-style extraction seeded by hand: named categories that map cleanly, plus two
# vague categories that also carry category flags (resolved only in the second pass).
_SAMPLE_EXTRACTED = ExtractedRequirements(
    explicit_categories=[
        ExtractedCategory(
            name="well-equipped gym",
            characteristics=["open before 7am", "within walking distance"],
        ),
        ExtractedCategory(
            name="large grocery store",
            characteristics=["not a corner shop", "reachable without a car"],
        ),
        ExtractedCategory(name="daycare", characteristics=["within a short walk"]),
        ExtractedCategory(
            name="a place to get my shopping done",
            characteristics=["without a long trip"],
        ),
        ExtractedCategory(
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
        ),
        AmbiguityFlag(
            phrase="a place to play",
            target="category",
            category=None,
            characteristic=None,
        ),
    ],
    persona_facts=[
        "works hybrid, two or three days in the office",
        "runs early in the mornings",
        "I like sports",
        "has one car shared between two people",
        "not particularly interested in nightlife",
    ],
)

_SAMPLE_PAYLOAD = PayloadRecord(
    normalized_text=(
        "A well-equipped gym open before 7am within walking distance, a large grocery store "
        "reachable without a car, a daycare within a short walk, and a place to play without a long trip because I  like sports"
    ),
    raw_text="(seeded Mechanism-1 payload for the Component 2A sample run)",
)

# Clarification answers Component 2B would have written, keyed by the flag phrase.
# Shopping is specific (Op2 should resolve confidently). Play is still vague (nearest-node).
_SAMPLE_USER_RESPONSES = {
    "a place to get my shopping done": UserResponse(
        question=(
            "When you say a place to get your shopping done, do you mean a full supermarket, "
            "a convenience store, or a shopping mall?"
        ),
        response="A full supermarket where I can do a big weekly shop.",
    ),
    "a place to play": UserResponse(
        question=(
            "When you say a place to play, do you mean a park, a playground, a sports "
            "complex, or something else?"
        ),
        response="Not sure, just somewhere outdoors I can play sports sometimes.",
    ),
}


def _build_sample_state(with_responses: bool) -> RequirementInterpretationState:
    return RequirementInterpretationState(
        payload=_SAMPLE_PAYLOAD,
        extracted=_SAMPLE_EXTRACTED,
        user_responses=dict(_SAMPLE_USER_RESPONSES) if with_responses else {},
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


def run_sample_resolution(with_responses: bool) -> RequirementInterpretationState:
    """Run the Component 2A stages in order, printing what each one produced."""
    settings = get_settings()
    configure_logging(settings.log_level)

    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    interpretation = create_requirement_interpretation(settings)
    state = _build_sample_state(with_responses)

    _section("INPUT STATE")
    print(
        json.dumps(
            {
                "payload": {"normalized_text": state.payload.normalized_text},
                "extracted": state.extracted.model_dump(),
                "user_responses": {
                    phrase: response.model_dump()
                    for phrase, response in state.user_responses.items()
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(
        f"\nexplicit_categories: {len(state.extracted.explicit_categories)}   "
        f"ambiguity_flags: {len(state.extracted.ambiguity_flags)}   "
        f"persona_facts: {len(state.extracted.persona_facts)}"
    )

    instruction = interpretation.build_taxonomy_mapping_instruction(taxonomy_mapping_json_schema())
    _section("OP1 - INSTRUCTION")
    print(instruction)
    print(
        f"\ntaxonomy nodes: {len(AMENITY_TAXONOMY_NODES)}   "
        f"few-shot pairs: {len(build_mapping_few_shot_examples())}"
    )

    mapping = interpretation.execute_taxonomy_mapping(state, instruction)
    _section("OP1 - PROVIDER ATTEMPTS")
    _print_attempts(collector, "execute_taxonomy_mapping")

    _section("OP1 - RESULT")
    print(mapping.model_dump_json(indent=2))

    interpretation.assemble_resolved_requirements(state, mapping)
    _section("OP1 - RESOLVED")
    _print_resolved(state)

    _section("GATE")
    category_flags = [
        flag for flag in state.resolved.ambiguity_flags if flag.target == "category"
    ]
    print(f"user_responses populated: {bool(state.user_responses)}")
    print(f"category flags remaining: {len(category_flags)}")
    print(f"operation 2 will run: {bool(state.user_responses) and bool(category_flags)}")

    if with_responses and category_flags:
        pairs = [
            (flag, state.user_responses[flag.phrase])
            for flag in category_flags
            if flag.phrase in state.user_responses
        ]

        resolution_instruction = interpretation.build_flag_resolution_instruction(
            flag_resolution_json_schema()
        )
        _section("OP2 - INSTRUCTION")
        print(resolution_instruction)
        print(
            f"\ntaxonomy nodes: {len(AMENITY_TAXONOMY_NODES)}   "
            f"few-shot pairs: {len(build_resolution_few_shot_examples())}"
        )

        result = interpretation.execute_flag_resolution(pairs, resolution_instruction)
        _section("OP2 - PROVIDER ATTEMPTS")
        _print_attempts(collector, "execute_flag_resolution")

        _section("OP2 - RESULT")
        print(result.model_dump_json(indent=2))

        interpretation.merge_resolved_flags(state, result)
        _section("OP2 - RESOLVED")
        _print_resolved(state)

    return state


def _print_attempts(collector: _RecordCollector, stage: str) -> None:
    for attempt in collector.events(CATEGORY_RESOLUTION_ATTEMPT_EVENT):
        if attempt.get("stage") != stage:
            continue
        line = f"{attempt['provider']} ({attempt['model']}): {attempt['outcome']}"
        detail = attempt.get("detail")
        print(f"{line} - {detail}" if detail else line)
    for answer in collector.events(CATEGORY_RESOLUTION_RAW_BODY_EVENT):
        if answer.get("stage") != stage:
            continue
        print(f"\nraw decoded body from {answer['provider']}:")
        print(json.dumps(answer["body"], indent=2, ensure_ascii=False))


def _print_resolved(state: RequirementInterpretationState) -> None:
    resolved = state.resolved
    print(json.dumps(_resolved_requirements_dict(resolved), indent=2, ensure_ascii=False))
    category_flags = sum(1 for flag in resolved.ambiguity_flags if flag.target == "category")
    print(
        f"\nresolved_explicit_categories: {len(resolved.resolved_explicit_categories)}   "
        f"ambiguity_flags: {len(resolved.ambiguity_flags)}   "
        f"of which target=category: {category_flags}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Deep Search Mechanism 2 Component 2A stage by stage against real LLM calls.",
    )
    parser.add_argument(
        "--with-responses",
        action="store_true",
        help="Seed hand-supplied user responses so Operation 2 (flag resolution) runs.",
    )
    args = parser.parse_args()

    try:
        run_sample_resolution(args.with_responses)
    except CategoryResolutionError as exc:
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
