import json
import logging
import re
import unicodedata
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Sequence

from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException
from pydantic import ValidationError

from src.clients.llm_provider import StructuredLLMProvider, create_llm_providers
from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import (
    ExtractionProviderError,
    ExtractionValidationError,
    InputTooShortError,
    UnsupportedLanguageError,
)
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_prompts.extraction_instruction import (
    BOUNDARY_RULES,
    BUCKET_DEFINITIONS,
    NEGATIVE_RULES,
    OUTPUT_RULES,
    TASK_STATEMENT,
    build_few_shot_examples,
)
from src.services.deep_search.feature_schemas.schemas import (
    EXTRACTION_SCHEMA_NAME,
    ExtractedRequirements,
    PayloadRecord,
    RequirementInterpretationState,
    extraction_json_schema,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

MIN_INPUT_WORD_COUNT = 100
ENGLISH_LANGUAGE_CODE = "en"

# Log events the sample runner reads back to print stage 4's attempt trail, because the
# raw body is a local value inside the stage and is not carried on any contract.
PROVIDER_ATTEMPT_EVENT = "extraction.provider_attempt"
RAW_BODY_EVENT = "extraction.raw_body"

_INPUT_TOO_SHORT_MESSAGE = (
    f"Instructions must be of more than {MIN_INPUT_WORD_COUNT} words"
)
_UNSUPPORTED_LANGUAGE_MESSAGE = "Instructions must be written in English"

# langdetect samples randomly unless its factory is seeded, so the same input would
# otherwise be able to produce two different verdicts.
DetectorFactory.seed = 0

_LINE_ENDINGS = re.compile(r"\r\n?")
_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")


def is_english(text: str) -> bool:
    """Language gate; an undetectable input counts as not English."""
    try:
        return detect(text) == ENGLISH_LANGUAGE_CODE
    except LangDetectException:
        return False


class UserRequirementsInterpretation:
    """Responsibility 1: turn raw customer text into a per-category specification.

    Mechanism 1 is implemented here as `parse_unstructured_input` plus its stage methods.
    Mechanisms 2 through 9 add methods to this class; they read the same handoff state and
    the same provider chain.
    """

    def __init__(self, providers: Sequence[StructuredLLMProvider]) -> None:
        self._providers = tuple(providers)

    def interpret(self, raw_input: str) -> RequirementInterpretationState:
        """Responsibility entry point; sequences the mechanisms."""
        return self.parse_unstructured_input(raw_input)

    def parse_unstructured_input(self, raw_input: str) -> RequirementInterpretationState:
        """Mechanism 1: drive stages 1, 3, 4, and 5 of unstructured input parsing."""
        payload = self.intake_and_assemble_payload(raw_input)
        instruction = self.build_extraction_instruction(extraction_json_schema())
        extracted = self.execute_and_validate(payload, instruction)
        return self.assemble_handoff(payload, extracted)

    def intake_and_assemble_payload(self, raw_input: str) -> PayloadRecord:
        """Stage 1: bound and normalize the input so behavior tracks content, not layout."""
        normalized_text = _normalize_requirement_text(raw_input)
        word_count = len(normalized_text.split())

        # Empty and whitespace-only input normalize to zero words, so the word bound is
        # the single check that rejects both, with one message for all three cases.
        if word_count < MIN_INPUT_WORD_COUNT:
            logger.info(
                json.dumps(
                    {
                        "event": "intake.rejected",
                        "timestamp": _timestamp(),
                        "reason": "under_word_bound",
                        "word_count": word_count,
                        "minimum_word_count": MIN_INPUT_WORD_COUNT,
                    }
                )
            )
            raise InputTooShortError(_INPUT_TOO_SHORT_MESSAGE)

        text_is_english = is_english(normalized_text)
        logger.info(
            json.dumps(
                {
                    "event": "intake.payload",
                    "timestamp": _timestamp(),
                    "raw_length": len(raw_input),
                    "normalized_length": len(normalized_text),
                    "word_count": word_count,
                    "is_english": text_is_english,
                }
            )
        )
        logger.debug(
            json.dumps({"event": "intake.payload.text", "normalized_text": normalized_text})
        )

        if not text_is_english:
            logger.info(
                json.dumps(
                    {
                        "event": "intake.rejected",
                        "timestamp": _timestamp(),
                        "reason": "unsupported_language",
                    }
                )
            )
            raise UnsupportedLanguageError(_UNSUPPORTED_LANGUAGE_MESSAGE)

        return PayloadRecord(normalized_text=normalized_text, raw_text=raw_input)

    def build_extraction_instruction(self, json_schema: dict) -> str:
        """Stage 3: assemble the bucket rules, negative rules, schema, and worked pairs."""
        examples = build_few_shot_examples()
        instruction = "\n\n".join(
            (
                TASK_STATEMENT,
                BUCKET_DEFINITIONS,
                NEGATIVE_RULES,
                BOUNDARY_RULES,
                OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
                _render_examples(examples),
            )
        )

        logger.info(
            json.dumps(
                {
                    "event": "instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "few_shot_count": len(examples),
                    "schema_properties": list(json_schema.get("properties", {})),
                }
            )
        )
        logger.debug(json.dumps({"event": "instruction.built.text", "instruction": instruction}))
        return instruction

    def execute_and_validate(
        self,
        payload: PayloadRecord,
        instruction: str,
    ) -> ExtractedRequirements:
        """Stage 4: call providers in the bound order, then validate independently."""
        json_schema = extraction_json_schema()
        body: dict | None = None
        answered_by: str | None = None

        for provider in self._providers:
            try:
                body = provider.generate_structured(
                    instruction=instruction,
                    user_content=payload.normalized_text,
                    json_schema=json_schema,
                    schema_name=EXTRACTION_SCHEMA_NAME,
                )
            except LLMProviderError as exc:
                logger.info(
                    json.dumps(
                        {
                            "event": PROVIDER_ATTEMPT_EVENT,
                            "timestamp": _timestamp(),
                            "provider": provider.name,
                            "model": provider.model,
                            "outcome": "failed",
                            "detail": str(exc),
                        }
                    )
                )
                continue

            answered_by = provider.name
            logger.info(
                json.dumps(
                    {
                        "event": PROVIDER_ATTEMPT_EVENT,
                        "timestamp": _timestamp(),
                        "provider": provider.name,
                        "model": provider.model,
                        "outcome": "answered",
                    }
                )
            )
            break

        if body is None:
            logger.info(
                json.dumps(
                    {
                        "event": "extraction.rejected",
                        "timestamp": _timestamp(),
                        "reason": "no_provider_answered",
                        "attempted": [provider.name for provider in self._providers],
                    }
                )
            )
            raise ExtractionProviderError("No LLM provider returned an extraction body")

        logger.debug(json.dumps({"event": RAW_BODY_EVENT, "provider": answered_by, "body": body}))

        # Second, independent check: generation-time constraint still lets a wrapped or
        # otherwise out-of-contract body reach here, and acceptance is all-or-nothing.
        try:
            extracted = ExtractedRequirements.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "extraction.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "rejected",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise ExtractionValidationError(
                f"The body returned by {answered_by} does not match the extraction contract"
            ) from exc

        logger.info(
            json.dumps(
                {
                    "event": "extraction.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                }
            )
        )
        logger.debug(
            json.dumps({"event": "extraction.validated.buckets", **_bucket_counts(extracted)})
        )
        return extracted

    def assemble_handoff(
        self,
        payload: PayloadRecord,
        extracted: ExtractedRequirements,
    ) -> RequirementInterpretationState:
        """Stage 5: pair the payload with the buckets as the mutable handoff for 2A."""
        state = RequirementInterpretationState(payload=payload, extracted=extracted)

        logger.info(
            json.dumps(
                {
                    "event": "handoff.assembled",
                    "timestamp": _timestamp(),
                    **_bucket_counts(extracted),
                }
            )
        )
        logger.debug(
            json.dumps(
                {
                    "event": "handoff.assembled.state",
                    "payload": asdict(state.payload),
                    "extracted": state.extracted.model_dump(),
                }
            )
        )
        return state


def create_requirement_interpretation(settings: Settings) -> UserRequirementsInterpretation:
    """Composition root: bind the provider chain that LLM_PROVIDER_ORDER names."""
    return UserRequirementsInterpretation(create_llm_providers(settings))


def _normalize_requirement_text(raw_input: str) -> str:
    """Drop invisible characters and horizontal runs; keep the line structure intact."""
    text = _LINE_ENDINGS.sub("\n", unicodedata.normalize("NFKC", raw_input))
    # Tabs survive the control-character filter so the next step can collapse them into a
    # space rather than fusing the words they separate.
    text = "".join(
        char
        for char in text
        if char in "\n\t" or unicodedata.category(char) not in ("Cc", "Cf")
    )
    # Line breaks, bullets, and quotes stay: they carry the list structure the model reads
    # as separate statements.
    lines = (_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(lines).strip()


def _render_examples(examples: Sequence[tuple[str, str]]) -> str:
    blocks = (
        f"EXAMPLE {index}\nCUSTOMER INPUT\n{customer_input}\n\nEXPECTED OUTPUT\n{expected}"
        for index, (customer_input, expected) in enumerate(examples, start=1)
    )
    return "WORKED EXAMPLES\n\n" + "\n\n".join(blocks)


def _bucket_counts(extracted: ExtractedRequirements) -> dict[str, int]:
    return {
        "explicit_categories": len(extracted.explicit_categories),
        "ambiguity_flags": len(extracted.ambiguity_flags),
        "persona_facts": len(extracted.persona_facts),
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
