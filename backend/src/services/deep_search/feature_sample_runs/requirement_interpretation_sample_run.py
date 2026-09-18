"""Manual, stage-by-stage run of Mechanism 1 against one real LLM call.

Not a test: it asserts nothing and writes nothing to disk. It calls the four stage methods
in sequence rather than `parse_unstructured_input`, so every intermediate object can be
printed without the workflow method returning debug data it has no other reason to expose.

From `backend/`:
    python -m src.services.deep_search.requirement_interpretation_sample_run
    python -m src.services.deep_search.requirement_interpretation_sample_run \
        --input-file path/to/requirements.txt
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import RequirementExtractionError
from src.services.deep_search.feature_prompts.extraction_instruction import build_few_shot_examples
from src.services.deep_search.requirement_interpretation import (
    PROVIDER_ATTEMPT_EVENT,
    RAW_BODY_EVENT,
    create_requirement_interpretation,
)
from src.services.deep_search.feature_schemas.schemas import (
    RequirementInterpretationState,
    extraction_json_schema,
)

# Over 100 words, so the default run clears intake. Carries stated categories with and
# without characteristics, a vague quality, a negation, and a conditional.
SAMPLE_CUSTOMER_INPUT = (
    "We're moving to Frankfurt in April with our two kids, aged four and nine, and we've "
    "narrowed things down to a few apartments in the north of the city. My wife and I both "
    "work hybrid, so we're each in the office two or three days a week and at home the "
    "rest of the time. The younger one starts kindergarten in the autumn, so a daycare "
    "within a short walk is the thing we care about most, and the older one needs a "
    "primary school we'd be happy with. I run early in the mornings and would like green "
    "space I can actually loop around rather than a small square with a bench."
    "\n\n"
    "We do a big weekly shop, so a proper supermarket rather than a corner shop matters, "
    "ideally one we can reach without the car since we only have one between us. A decent "
    "gym would be a bonus, nothing fancy, just something open before seven. We're not "
    "particularly interested in nightlife. If we end up getting a dog, which we have been "
    "discussing, somewhere to walk it would suddenly matter a lot more than it does today."
)

_RULE = "=" * 78


class _RecordCollector(logging.Handler):
    """Keeps the service's structured records so this script can print stage 4's trail.

    Stage 4 drops the raw provider body once the typed contract exists, so the log line it
    emits is the only place the body is still readable from outside the stage.
    """

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


async def run_sample_extraction(raw_input: str) -> RequirementInterpretationState:
    """Run stages 1, 2, 3, 4, and 5 in order, printing what each one returned."""
    settings = get_settings()
    configure_logging(settings.log_level)

    # The sections below include DEBUG-only records, so the service logger is opened to
    # DEBUG for this run. The stderr handler still honours LOG_LEVEL.
    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    interpretation = create_requirement_interpretation(settings)
    try:
        _section("INPUT")
        print(raw_input)
        print(f"\ncharacters: {len(raw_input)}   words: {len(raw_input.split())}")

        payload = interpretation.intake_and_assemble_payload(raw_input)
        _section("STAGE 1 - PAYLOAD")
        print(json.dumps(asdict(payload), indent=2, ensure_ascii=False))
        print("\nnormalized text in full:")
        print(payload.normalized_text)
        print(
            f"\nraw length: {len(payload.raw_text)}   "
            f"normalized length: {len(payload.normalized_text)}"
        )

        json_schema = extraction_json_schema()
        _section("STAGE 2 - SCHEMA")
        print(json.dumps(json_schema, indent=2))
        print(f"\nroot additionalProperties: {json_schema.get('additionalProperties')}")
        print(f"root required: {json_schema.get('required')}")
        for name, definition in json_schema.get("$defs", {}).items():
            print(
                f"{name} additionalProperties: {definition.get('additionalProperties')}   "
                f"required: {definition.get('required')}"
            )

        instruction = interpretation.build_extraction_instruction(json_schema)
        _section("STAGE 3 - INSTRUCTION")
        print(instruction)
        print(
            f"\ncharacters: {len(instruction)}   "
            f"few-shot pairs: {len(build_few_shot_examples())}"
        )

        extracted = await interpretation.execute_and_validate(payload, instruction)
        _section("STAGE 4 - PROVIDER ATTEMPTS")
        for attempt in collector.events(PROVIDER_ATTEMPT_EVENT):
            line = f"{attempt['provider']} ({attempt['model']}): {attempt['outcome']}"
            detail = attempt.get("detail")
            print(f"{line} - {detail}" if detail else line)
        for answer in collector.events(RAW_BODY_EVENT):
            print(f"\nraw decoded body from {answer['provider']}:")
            print(json.dumps(answer["body"], indent=2, ensure_ascii=False))

        _section("STAGE 4 - VALIDATED")
        print(extracted.model_dump_json(indent=2))

        state = interpretation.assemble_handoff(payload, extracted)
        _section("STAGE 5 - HANDOFF")
        print(
            json.dumps(
                {"payload": asdict(state.payload), "extracted": state.extracted.model_dump()},
                indent=2,
                ensure_ascii=False,
            )
        )
        print(
            f"\nexplicit_categories: {len(state.extracted.explicit_categories)}   "
            f"ambiguity_flags: {len(state.extracted.ambiguity_flags)}   "
            f"persona_facts: {len(state.extracted.persona_facts)}"
        )
        return state
    finally:
        await interpretation.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Deep Search mechanism 1 stage by stage against one real LLM call.",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="UTF-8 text file to use instead of the built-in sample input.",
    )
    args = parser.parse_args()

    raw_input = (
        args.input_file.read_text(encoding="utf-8")
        if args.input_file
        else SAMPLE_CUSTOMER_INPUT
    )

    try:
        asyncio.run(run_sample_extraction(raw_input))
    except RequirementExtractionError as exc:
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
