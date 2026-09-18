"""Manual, stage-by-stage run of Mechanism 2 against real LLM calls.

Not a test: it asserts nothing and writes nothing to disk. It seeds a Mechanism-1-style
`RequirementInterpretationState` (so no re-parse is needed) and calls the 2A, router, and 2B
stage methods in sequence rather than `run_explicit_category_resolution`, so every
intermediate object can be printed. The raw provider body is dropped inside the execute
stages, so a collecting log handler reads the attempt trail and the raw body back off
DEEP_SEARCH_LOGGER_NAME, the same technique the Mechanism 1 runner uses.

Default path is the full Mechanism 2 loop: 2A pass 1, router, live 2B (generate + CLI), 2A
pass 2 (Operation 2 only), router again. `--with-responses` skips live 2B and injects the
hand-supplied answers so Operation 2 can be exercised without the CLI.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run
    python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run \
        --with-responses
"""

import argparse
import asyncio
import json
import logging
import sys

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import CategoryResolutionError, ClarificationError
from src.services.deep_search.feature_prompts.category_resolution_instruction import (
    build_mapping_few_shot_examples,
    build_resolution_few_shot_examples,
)
from src.services.deep_search.feature_prompts.clarification_instruction import (
    build_clarification_few_shot_examples,
)
from src.services.deep_search.feature_schemas.amenity_taxonomy import AMENITY_TAXONOMY_NODES
from src.services.deep_search.feature_schemas.schemas import (
    AmbiguityFlag,
    ExtractedCategory,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
    UserResponse,
    clarification_questions_json_schema,
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
            category_id=0,
            name="well-equipped gym",
            characteristics=["open before 7am", "within walking distance"],
        ),
        ExtractedCategory(
            category_id=1,
            name="large grocery store",
            characteristics=["not a corner shop", "reachable without a car"],
        ),
        ExtractedCategory(
            category_id=2,
            name="daycare",
            characteristics=["within a short walk"],
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
    raw_text="(seeded Mechanism-1 payload for the Mechanism 2 sample run)",
)

# Clarification answers used only by --with-responses, keyed by category_id.
# Shopping is specific (Op2 should resolve confidently). Play is still vague (nearest-node).
_SAMPLE_USER_RESPONSES = {
    3: UserResponse(
        question=(
            "When you say a place to get your shopping done, do you mean a full supermarket, "
            "a convenience store, or a shopping mall?"
        ),
        options=["full supermarket", "convenience store", "shopping mall"],
        response="A full supermarket where I can do a big weekly shop.",
    ),
    4: UserResponse(
        question=(
            "When you say a place to play, do you mean a park, a playground, a sports "
            "complex, or something else?"
        ),
        options=["park", "playground", "sports complex", "something else"],
        response="Not sure, just somewhere outdoors I can play sports sometimes.",
    ),
}


def _build_sample_state() -> RequirementInterpretationState:
    return RequirementInterpretationState(
        payload=_SAMPLE_PAYLOAD,
        extracted=_SAMPLE_EXTRACTED,
        user_responses={},
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


async def run_sample_resolution(with_responses: bool) -> RequirementInterpretationState:
    """Run Mechanism 2 stages in order, printing what each one produced."""
    settings = get_settings()
    configure_logging(settings.log_level)

    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    interpretation = create_requirement_interpretation(settings)
    try:
        state = _build_sample_state()

        _section("INPUT STATE")
        print(
            json.dumps(
                {
                    "payload": {"normalized_text": state.payload.normalized_text},
                    "extracted": state.extracted.model_dump(),
                    "user_responses": {},
                    "category_resolution_passes": state.category_resolution_passes,
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
        _section("2A PASS 1 - OP1 INSTRUCTION")
        print(instruction)
        print(
            f"\ntaxonomy nodes: {len(AMENITY_TAXONOMY_NODES)}   "
            f"few-shot pairs: {len(build_mapping_few_shot_examples())}"
        )

        mapping = await interpretation.execute_taxonomy_mapping(state, instruction)
        _section("2A PASS 1 - OP1 PROVIDER ATTEMPTS")
        _print_attempts(collector, "execute_taxonomy_mapping")

        _section("2A PASS 1 - OP1 RESULT")
        print(mapping.model_dump_json(indent=2))

        interpretation.assemble_resolved_requirements(state, mapping)
        _section("2A PASS 1 - RESOLVED")
        _print_resolved(state)

        route = interpretation.inspect_category_resolution(state)
        _section("ROUTER INSPECT 1")
        _print_inspect(state, route)

        if route == "mechanism_3":
            _section("HANDOFF")
            print("No category flags remain after pass 1. Mechanism 2 returns the state.")
            print("Mechanism 3 is not invoked.")
            return state

        resolved_before_2b = _resolved_requirements_dict(state.resolved)

        if with_responses:
            state.user_responses = dict(_SAMPLE_USER_RESPONSES)
            _section("2B SKIPPED - SEEDED USER RESPONSES")
            print(
                "Live question generation and CLI collect were skipped because "
                "--with-responses was set."
            )
            _print_user_responses(state)
        else:
            clarification_schema = clarification_questions_json_schema()
            clarification_instruction = interpretation.build_clarification_questions_instruction(
                clarification_schema
            )
            _section("2B - INSTRUCTION")
            print(clarification_instruction)
            print(f"\nfew-shot pairs: {len(build_clarification_few_shot_examples())}")

            clarification_result = await interpretation.execute_clarification_questions(
                state, clarification_instruction
            )
            _section("2B - PROVIDER ATTEMPTS")
            _print_attempts(collector, "execute_clarification_questions")

            _section("2B - GENERATED QUESTIONS")
            print(clarification_result.model_dump_json(indent=2))

            _section("2B - CLI COLLECT")
            print("Answer each question in this terminal. Type an option index from 1 to 5.")
            print('If you choose "other", you will then be asked to describe what you meant.')
            interpretation.collect_clarification_responses(state, clarification_result)

            _section("2B - USER RESPONSES")
            _print_user_responses(state)

            _section("2B - RESOLVED UNCHANGED")
            print(json.dumps(resolved_before_2b, indent=2, ensure_ascii=False))
            print(
                "\nresolved.* after 2B matches the pre-2B snapshot: "
                f"{_resolved_requirements_dict(state.resolved) == resolved_before_2b}"
            )
            print(f"category_resolution_passes still: {state.category_resolution_passes}")

        category_flags = [
            flag for flag in state.resolved.ambiguity_flags if flag.target == "category"
        ]
        pairs = [
            (flag, state.user_responses[flag.category_id])
            for flag in category_flags
            if flag.category_id in state.user_responses
        ]

        _section("2A PASS 2 - GATE")
        print(f"user_responses populated: {bool(state.user_responses)}")
        print(f"category flags remaining: {len(category_flags)}")
        print(f"operation 2 will run: {bool(pairs)}")

        if pairs:
            resolution_instruction = interpretation.build_flag_resolution_instruction(
                flag_resolution_json_schema()
            )
            _section("2A PASS 2 - OP2 INSTRUCTION")
            print(resolution_instruction)
            print(
                f"\ntaxonomy nodes: {len(AMENITY_TAXONOMY_NODES)}   "
                f"few-shot pairs: {len(build_resolution_few_shot_examples())}"
            )

            result = await interpretation.execute_flag_resolution(pairs, resolution_instruction)
            _section("2A PASS 2 - OP2 PROVIDER ATTEMPTS")
            _print_attempts(collector, "execute_flag_resolution")

            _section("2A PASS 2 - OP2 RESULT")
            print(result.model_dump_json(indent=2))

            interpretation.merge_resolved_flags(state, result)
            _section("2A PASS 2 - RESOLVED")
            _print_resolved(state)

        route = interpretation.inspect_category_resolution(state)
        _section("ROUTER INSPECT 2")
        _print_inspect(state, route)
        print("Mechanism 3 is not invoked. interpret would return this state.")
        return state
    finally:
        await interpretation.aclose()


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


def _print_inspect(state: RequirementInterpretationState, route: str) -> None:
    resolved = state.resolved
    category_flags = 0 if resolved is None else sum(
        1 for flag in resolved.ambiguity_flags if flag.target == "category"
    )
    print(f"category_resolution_passes: {state.category_resolution_passes}")
    print(f"category flags remaining: {category_flags}")
    print(f"route: {route}")


def _print_user_responses(state: RequirementInterpretationState) -> None:
    print(
        json.dumps(
            {
                str(category_id): response.model_dump()
                for category_id, response in state.user_responses.items()
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nuser_responses keys: {sorted(state.user_responses)}")


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
        description=(
            "Run Deep Search Mechanism 2 (2A, router, 2B) stage by stage against real LLM calls."
        ),
    )
    parser.add_argument(
        "--with-responses",
        action="store_true",
        help=(
            "Skip live 2B generation and CLI collect; inject hand-supplied user responses "
            "so Operation 2 still runs."
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_sample_resolution(args.with_responses))
    except (CategoryResolutionError, ClarificationError) as exc:
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
