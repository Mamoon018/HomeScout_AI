"""Manual, stage-by-stage run of R1's pause/resume entry points (C1) and step payloads.

Not a test: it asserts nothing and writes nothing to disk or to Supabase. It seeds a
Mechanism-1-style `RequirementInterpretationState` (so extraction is not re-run), then walks the
web path the coordinator takes: 2A pass 1 + router -> generate and store the questions (the
pause) -> save the questions step payload to JSON and load it back -> record answers ->
continue after answers.
Provider attempts and raw bodies are read back off DEEP_SEARCH_LOGGER_NAME, as in
`category_resolution_sample_run.py`.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.r1_pause_resume_sample_run
    python -m src.services.deep_search.feature_sample_runs.r1_pause_resume_sample_run \
        --answers "1:2,2:5=a quiet bench in a garden"

`--answers` is `category_id:option[=description]`, comma separated; without it the terminal
prompts ask each question.
"""

import argparse
import asyncio
import json
import logging
import sys

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import (
    R1_STAGE_ERRORS,
    ClarificationAnswerError,
    StateVersionMismatchError,
)
from src.services.deep_search.feature_schemas.schemas import (
    AmbiguityFlag,
    ClarificationAnswer,
    ExtractedCategory,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
)
from src.services.deep_search.r1_run_store import (
    STEP_SCHEMA_VERSION,
    dump_state,
    dump_step_output,
    load_step_output,
)
from src.services.deep_search.requirement_interpretation import (
    LLM_PROVIDER_ATTEMPT_EVENT,
    LLM_PROVIDER_RAW_BODY_EVENT,
    _prompt_clarification_answers,
    _resolved_requirements_dict,
    create_requirement_interpretation,
)

_RULE = "=" * 78

# A Mechanism-1-style handoff: two plainly named categories and two vague ones that carry
# category flags, for a retired couple with an older dog. Ids are stamped as M1 would stamp them.
_SAMPLE_PAYLOAD = PayloadRecord(
    normalized_text=(
        "We are a retired couple with an older spaniel and grandchildren who stay most "
        "weekends. We want a vet nearby for the dog, a library we can walk to, somewhere for "
        "the grandkids, and a spot to unwind in the afternoons. We no longer drive much."
    ),
    raw_text="seeded as after Mechanism 1",
)
_SAMPLE_EXTRACTED = ExtractedRequirements(
    explicit_categories=[
        ExtractedCategory(category_id=0, name="vet", characteristics=["nearby", "for an older dog"]),
        ExtractedCategory(category_id=1, name="library", characteristics=["walkable"]),
        ExtractedCategory(
            category_id=2, name="somewhere for the grandkids", characteristics=["weekends"]
        ),
        ExtractedCategory(
            category_id=3, name="a spot to unwind", characteristics=["afternoons", "calm"]
        ),
    ],
    ambiguity_flags=[
        AmbiguityFlag(
            phrase="somewhere for the grandkids",
            target="category",
            category=None,
            characteristic=None,
            category_id=2,
        ),
        AmbiguityFlag(
            phrase="a spot to unwind",
            target="category",
            category=None,
            characteristic=None,
            category_id=3,
        ),
    ],
    persona_facts=[
        "retired couple",
        "owns an older spaniel",
        "grandchildren stay most weekends",
        "no longer drives much",
    ],
)

_CONTINUE_STAGES = (
    "execute_flag_resolution",
    "execute_category_inference",
    "execute_depth_assignment",
    "execute_metric_definition",
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


def _parse_answers(raw: str) -> list[ClarificationAnswer]:
    answers = []
    for part in raw.split(","):
        head, _, description = part.partition("=")
        category_id, _, option = head.partition(":")
        answers.append(
            ClarificationAnswer(
                category_id=int(category_id.strip()),
                option=int(option.strip()),
                description=description.strip() or None,
            )
        )
    return answers


async def run_sample(answers_arg: str | None) -> RequirementInterpretationState:
    settings = get_settings()
    configure_logging(settings.log_level)
    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    interpretation = create_requirement_interpretation(settings)
    try:
        state = RequirementInterpretationState(payload=_SAMPLE_PAYLOAD, extracted=_SAMPLE_EXTRACTED)
        _section("SEEDED STATE (as after Mechanism 1)")
        print(json.dumps(dump_state(state), indent=2, ensure_ascii=False))

        await interpretation.resolve_explicit_categories(state)
        _section("2A PASS 1 - PROVIDER ATTEMPTS")
        _print_attempts(collector, "execute_taxonomy_mapping")
        _section("2A PASS 1 - RESOLVED")
        print(json.dumps(_resolved_requirements_dict(state.resolved), indent=2, ensure_ascii=False))

        route = interpretation.inspect_category_resolution(state)
        _section("ROUTER INSPECT 1")
        print(f"category_resolution_passes: {state.category_resolution_passes}   route: {route}")
        if route == "mechanism_3":
            print("No category flag left after pass 1: start would finish without pausing.")
            await interpretation.complete_interpretation(state)
            _print_plans(state)
            return state

        questions = await interpretation.generate_clarification_questions(state)
        _section("PAUSE - QUESTION PROVIDER ATTEMPTS")
        _print_attempts(collector, "execute_clarification_questions")
        _section("PAUSE - QUESTIONS STORED ON THE STATE")
        print(json.dumps([q.model_dump() for q in questions], indent=2, ensure_ascii=False))

        # The questions are what a paused run saves for this step (r1_run_steps row).
        saved = json.loads(
            json.dumps(dump_step_output("clarification_questions", {"questions": questions}))
        )
        reloaded = load_step_output("clarification_questions", saved)
        _section("SAVED QUESTIONS STEP PAYLOAD")
        print(f"schema_version: {saved['schema_version']} (current {STEP_SCHEMA_VERSION})")
        print(f"json size: {len(json.dumps(saved))} chars")
        print(f"reloaded questions equal the stored ones: {list(reloaded.questions) == questions}")
        loaded = state

        if answers_arg:
            answers = _parse_answers(answers_arg)
        else:
            _section("ANSWERS - TERMINAL")
            print('Type an option number from 1 to 5. Choosing "other" asks for a description.')
            answers = _prompt_clarification_answers(loaded, loaded.clarification_questions)
        _section("ANSWERS - RAW")
        print(json.dumps([a.model_dump() for a in answers], indent=2, ensure_ascii=False))

        interpretation.record_clarification_answers(loaded, answers)
        _section("ANSWERS - RECORDED USER RESPONSES")
        print(
            json.dumps(
                {str(cid): r.model_dump() for cid, r in loaded.user_responses.items()},
                indent=2,
                ensure_ascii=False,
            )
        )

        finished = await interpretation.continue_after_answers(loaded)
        for stage in _CONTINUE_STAGES:
            _section(f"CONTINUE - {stage} PROVIDER ATTEMPTS")
            _print_attempts(collector, stage)
        _section("CONTINUE - ROUTER")
        print(f"category_resolution_passes: {finished.category_resolution_passes}")
        print(
            "question calls made: "
            f"{sum(1 for a in collector.events(LLM_PROVIDER_ATTEMPT_EVENT) if a.get('stage') == 'execute_clarification_questions' and a.get('outcome') == 'answered')}"
        )
        _print_plans(finished)
        return finished
    finally:
        await interpretation.aclose()


def _print_attempts(collector: _RecordCollector, stage: str) -> None:
    for attempt in collector.events(LLM_PROVIDER_ATTEMPT_EVENT):
        if attempt.get("stage") != stage:
            continue
        line = f"{attempt['provider']} ({attempt['model']}): {attempt['outcome']}"
        detail = attempt.get("detail")
        print(f"{line} - {detail}" if detail else line)
    for answer in collector.events(LLM_PROVIDER_RAW_BODY_EVENT):
        if answer.get("stage") != stage:
            continue
        print(f"\nraw decoded body from {answer['provider']}:")
        print(json.dumps(answer["body"], indent=2, ensure_ascii=False))


def _print_plans(state: RequirementInterpretationState) -> None:
    _section("RESULT - CATEGORY METRIC PLANS (what the page and R2 receive)")
    plans = dump_state(state)["category_metric_plans"]
    print(json.dumps(plans, indent=2, ensure_ascii=False))
    print(f"\nplan count: {len(plans)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run R1's pause/resume entry points stage by stage against real LLM calls."
    )
    parser.add_argument(
        "--answers",
        help='Answers as "category_id:option[=description]", comma separated.',
    )
    args = parser.parse_args()
    try:
        asyncio.run(run_sample(args.answers))
    except (*R1_STAGE_ERRORS, ClarificationAnswerError, StateVersionMismatchError) as exc:
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {getattr(exc, 'stage', 'unknown')}")
        print(f"message:   {exc}")
        return 1
    return 0


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


if __name__ == "__main__":
    sys.exit(main())
