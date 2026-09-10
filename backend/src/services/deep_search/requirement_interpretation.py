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
    CategoryMappingProviderError,
    CategoryMappingValidationError,
    ExtractionProviderError,
    ExtractionValidationError,
    InputTooShortError,
    UnsupportedLanguageError,
)
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_prompts.category_resolution_instruction import (
    build_flag_resolution_instruction as build_flag_resolution_text,
    build_mapping_few_shot_examples,
    build_resolution_few_shot_examples,
    build_taxonomy_mapping_instruction as build_taxonomy_mapping_text,
)
from src.services.deep_search.feature_prompts.extraction_instruction import (
    BOUNDARY_RULES,
    BUCKET_DEFINITIONS,
    NEGATIVE_RULES,
    OUTPUT_RULES,
    TASK_STATEMENT,
    build_few_shot_examples,
)
from src.services.deep_search.feature_schemas.amenity_taxonomy import (
    AMENITY_TAXONOMY_NODES,
    TAXONOMY_NODE_SET,
)
from src.services.deep_search.feature_schemas.schemas import (
    EXTRACTION_SCHEMA_NAME,
    FLAG_RESOLUTION_SCHEMA_NAME,
    TAXONOMY_MAPPING_SCHEMA_NAME,
    AmbiguityFlag,
    ExtractedRequirements,
    FlagResolutionResult,
    PayloadRecord,
    RequirementInterpretationState,
    ResolvedCategory,
    ResolvedRequirements,
    TaxonomyMappingResult,
    UserResponse,
    extraction_json_schema,
    flag_resolution_json_schema,
    taxonomy_mapping_json_schema,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

MIN_INPUT_WORD_COUNT = 100
ENGLISH_LANGUAGE_CODE = "en"

# Log events the sample runner reads back to print stage 4's attempt trail, because the
# raw body is a local value inside the stage and is not carried on any contract.
PROVIDER_ATTEMPT_EVENT = "extraction.provider_attempt"
RAW_BODY_EVENT = "extraction.raw_body"

# Component 2A reuses the same read-back technique: the raw mapping/resolution body is a
# local value inside the execute stages, so the runner reads these records to print it.
CATEGORY_RESOLUTION_ATTEMPT_EVENT = "category_resolution.provider_attempt"
CATEGORY_RESOLUTION_RAW_BODY_EVENT = "category_resolution.raw_body"

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
        state = self.parse_unstructured_input(raw_input)
        return self.resolve_explicit_categories(state)

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

    # ---------------------------------------------------------------------------------
    # Mechanism 2, Component 2A — Category Scope & Ambiguity Resolution
    # ---------------------------------------------------------------------------------

    def resolve_explicit_categories(
        self,
        state: RequirementInterpretationState,
    ) -> RequirementInterpretationState:
        """Mechanism 2 workflow: Operation 1 always, Operation 2 when the gate opens."""
        instruction = self.build_taxonomy_mapping_instruction(taxonomy_mapping_json_schema())
        mapping = self.execute_taxonomy_mapping(state, instruction)
        self.assemble_resolved_requirements(state, mapping)
        self.resolve_category_flags(state)
        return state

    def build_taxonomy_mapping_instruction(self, json_schema: dict) -> str:
        """Op1 Stage 1: assemble mapping rules, negative rules, full taxonomy, worked pairs."""
        instruction = build_taxonomy_mapping_text(json_schema)
        logger.info(
            json.dumps(
                {
                    "event": "taxonomy_mapping.instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "taxonomy_node_count": len(AMENITY_TAXONOMY_NODES),
                    "few_shot_count": len(build_mapping_few_shot_examples()),
                }
            )
        )
        logger.debug(
            json.dumps({"event": "taxonomy_mapping.instruction.text", "instruction": instruction})
        )
        return instruction

    def execute_taxonomy_mapping(
        self,
        state: RequirementInterpretationState,
        instruction: str,
    ) -> TaxonomyMappingResult:
        """Op1 Stage 2: one constrained call over all raw categories, then validate."""
        json_schema = taxonomy_mapping_json_schema()
        user_content = _render_extracted(state.extracted)
        body, answered_by = self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=TAXONOMY_MAPPING_SCHEMA_NAME,
            stage="execute_taxonomy_mapping",
        )

        try:
            mapping = TaxonomyMappingResult.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "taxonomy_mapping.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "rejected",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise CategoryMappingValidationError(
                f"The body returned by {answered_by} does not match the taxonomy-mapping contract",
                stage="execute_taxonomy_mapping",
            ) from exc

        self._assert_nodes_in_taxonomy(
            [entry.taxonomy_node for entry in mapping.resolved_categories],
            provider=answered_by,
            stage="execute_taxonomy_mapping",
        )

        logger.info(
            json.dumps(
                {
                    "event": "taxonomy_mapping.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                    "resolved_count": len(mapping.resolved_categories),
                    "flag_count": len(mapping.ambiguity_flags),
                }
            )
        )
        return mapping

    def assemble_resolved_requirements(
        self,
        state: RequirementInterpretationState,
        mapping: TaxonomyMappingResult,
    ) -> ResolvedRequirements:
        """Op1 Stage 3: attach chars, convert match-fails, merge M1 flags, set state.resolved."""
        characteristics_by_name = {
            category.name: list(category.characteristics)
            for category in state.extracted.explicit_categories
        }

        resolved_categories: list[ResolvedCategory] = []
        # The model's flags come first, then any paraphrase that failed the exact match.
        flags: list[AmbiguityFlag] = list(mapping.ambiguity_flags)
        for entry in mapping.resolved_categories:
            if entry.raw_name in characteristics_by_name:
                resolved_categories.append(
                    ResolvedCategory(
                        taxonomy_node=entry.taxonomy_node,
                        raw_name=entry.raw_name,
                        characteristics=characteristics_by_name[entry.raw_name],
                        provenance="confident",
                    )
                )
            else:
                # No exact match means the model paraphrased the raw name, so it re-enters
                # as a category flag rather than being silently dropped.
                flags.append(
                    AmbiguityFlag(
                        phrase=entry.raw_name,
                        target="category",
                        category=None,
                        characteristic=None,
                    )
                )

        # Mechanism-1 flags are appended as a union: no dedup, no filtering.
        flags.extend(state.extracted.ambiguity_flags)

        resolved = ResolvedRequirements(
            payload=state.payload,
            resolved_explicit_categories=resolved_categories,
            ambiguity_flags=flags,
            persona_facts=list(state.extracted.persona_facts),
        )
        state.resolved = resolved

        logger.info(
            json.dumps(
                {
                    "event": "resolved_requirements.assembled",
                    "timestamp": _timestamp(),
                    "resolved_count": len(resolved.resolved_explicit_categories),
                    "flag_count": len(resolved.ambiguity_flags),
                    "category_flag_count": _category_flag_count(resolved.ambiguity_flags),
                }
            )
        )
        logger.debug(
            json.dumps(
                {
                    "event": "resolved_requirements.assembled.object",
                    "resolved": _resolved_requirements_dict(resolved),
                }
            )
        )
        return resolved

    def resolve_category_flags(self, state: RequirementInterpretationState) -> None:
        """Op2 gate plus orchestration: skip when no user responses, else resolve flags."""
        if not state.user_responses:
            logger.info(
                json.dumps(
                    {
                        "event": "category_resolution.gate",
                        "timestamp": _timestamp(),
                        "user_responses_present": False,
                        "operation_2_runs": False,
                    }
                )
            )
            return

        resolved = state.resolved
        assert resolved is not None  # Op1 always sets it before the gate is reached.

        pairs: list[tuple[AmbiguityFlag, UserResponse]] = []
        for flag in resolved.ambiguity_flags:
            if flag.target != "category":
                continue
            response = state.user_responses.get(flag.phrase)
            if response is not None:
                pairs.append((flag, response))

        logger.info(
            json.dumps(
                {
                    "event": "category_resolution.gate",
                    "timestamp": _timestamp(),
                    "user_responses_present": True,
                    "operation_2_runs": bool(pairs),
                    "pair_count": len(pairs),
                }
            )
        )
        if not pairs:
            return

        instruction = self.build_flag_resolution_instruction(flag_resolution_json_schema())
        result = self.execute_flag_resolution(pairs, instruction)
        self.merge_resolved_flags(state, result)

    def build_flag_resolution_instruction(self, json_schema: dict) -> str:
        """Op2 Stage 4: assemble resolution rules, nearest-node rule, full taxonomy."""
        instruction = build_flag_resolution_text(json_schema)
        logger.info(
            json.dumps(
                {
                    "event": "flag_resolution.instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "taxonomy_node_count": len(AMENITY_TAXONOMY_NODES),
                    "few_shot_count": len(build_resolution_few_shot_examples()),
                }
            )
        )
        logger.debug(
            json.dumps({"event": "flag_resolution.instruction.text", "instruction": instruction})
        )
        return instruction

    def execute_flag_resolution(
        self,
        pairs: list[tuple[AmbiguityFlag, UserResponse]],
        instruction: str,
    ) -> FlagResolutionResult:
        """Op2 Stage 5: one constrained call over all {flag, response} pairs, then validate."""
        json_schema = flag_resolution_json_schema()
        user_content = _render_pairs(pairs)
        body, answered_by = self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=FLAG_RESOLUTION_SCHEMA_NAME,
            stage="execute_flag_resolution",
        )

        try:
            result = FlagResolutionResult.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "flag_resolution.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "rejected",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise CategoryMappingValidationError(
                f"The body returned by {answered_by} does not match the flag-resolution contract",
                stage="execute_flag_resolution",
            ) from exc

        self._assert_nodes_in_taxonomy(
            [entry.taxonomy_node for entry in result.resolved_categories],
            provider=answered_by,
            stage="execute_flag_resolution",
        )

        logger.info(
            json.dumps(
                {
                    "event": "flag_resolution.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                    "resolved_count": len(result.resolved_categories),
                }
            )
        )
        return result

    def merge_resolved_flags(
        self,
        state: RequirementInterpretationState,
        result: FlagResolutionResult,
    ) -> None:
        """Op2 Stage 6: append resolved entries, drop every category flag, in place."""
        resolved = state.resolved
        assert resolved is not None

        characteristics_by_name = {
            category.name: list(category.characteristics)
            for category in state.extracted.explicit_categories
        }
        for entry in result.resolved_categories:
            resolved.resolved_explicit_categories.append(
                ResolvedCategory(
                    taxonomy_node=entry.taxonomy_node,
                    raw_name=entry.raw_name,
                    characteristics=characteristics_by_name.get(entry.raw_name, []),
                    provenance=entry.provenance,
                )
            )

        # Every category flag exits Operation 2 resolved, so none survive in the flag set.
        resolved.ambiguity_flags = [
            flag for flag in resolved.ambiguity_flags if flag.target != "category"
        ]

        logger.info(
            json.dumps(
                {
                    "event": "resolved_flags.merged",
                    "timestamp": _timestamp(),
                    "resolved_count": len(resolved.resolved_explicit_categories),
                    "flag_count": len(resolved.ambiguity_flags),
                    "category_flag_count": _category_flag_count(resolved.ambiguity_flags),
                }
            )
        )
        logger.debug(
            json.dumps(
                {
                    "event": "resolved_flags.merged.object",
                    "resolved": _resolved_requirements_dict(resolved),
                }
            )
        )

    def _call_providers(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
        stage: str,
    ) -> tuple[dict, str]:
        """Try providers in the bound order; return the first body or a typed provider error."""
        body: dict | None = None
        answered_by: str | None = None

        for provider in self._providers:
            try:
                body = provider.generate_structured(
                    instruction=instruction,
                    user_content=user_content,
                    json_schema=json_schema,
                    schema_name=schema_name,
                )
            except LLMProviderError as exc:
                logger.info(
                    json.dumps(
                        {
                            "event": CATEGORY_RESOLUTION_ATTEMPT_EVENT,
                            "timestamp": _timestamp(),
                            "stage": stage,
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
                        "event": CATEGORY_RESOLUTION_ATTEMPT_EVENT,
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "provider": provider.name,
                        "model": provider.model,
                        "outcome": "answered",
                    }
                )
            )
            break

        if body is None or answered_by is None:
            logger.info(
                json.dumps(
                    {
                        "event": "category_resolution.rejected",
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "reason": "no_provider_answered",
                        "attempted": [provider.name for provider in self._providers],
                    }
                )
            )
            raise CategoryMappingProviderError(
                f"No LLM provider returned a {stage} body", stage=stage
            )

        logger.debug(
            json.dumps(
                {
                    "event": CATEGORY_RESOLUTION_RAW_BODY_EVENT,
                    "stage": stage,
                    "provider": answered_by,
                    "body": body,
                }
            )
        )
        return body, answered_by

    def _assert_nodes_in_taxonomy(
        self,
        nodes: list[str],
        *,
        provider: str,
        stage: str,
    ) -> None:
        """Independent second check: every returned node must be a real taxonomy node."""
        unknown = [node for node in nodes if node not in TAXONOMY_NODE_SET]
        if unknown:
            logger.info(
                json.dumps(
                    {
                        "event": "category_resolution.rejected",
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "provider": provider,
                        "reason": "unknown_taxonomy_node",
                        "nodes": unknown,
                    }
                )
            )
            raise CategoryMappingValidationError(
                f"The body returned by {provider} carried nodes outside the taxonomy: {unknown}",
                stage=stage,
            )


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


def _render_extracted(extracted: ExtractedRequirements) -> str:
    """The Mechanism 1 output as JSON, the user content of the Operation 1 call."""
    return json.dumps(extracted.model_dump(), indent=2, ensure_ascii=False)


def _render_pairs(pairs: list[tuple[AmbiguityFlag, UserResponse]]) -> str:
    """The {flag, response} pairs as JSON, the user content of the Operation 2 call."""
    return json.dumps(
        [{"flag": flag.model_dump(), "response": response.model_dump()} for flag, response in pairs],
        indent=2,
        ensure_ascii=False,
    )


def _category_flag_count(flags: list[AmbiguityFlag]) -> int:
    return sum(1 for flag in flags if flag.target == "category")


def _resolved_requirements_dict(resolved: ResolvedRequirements) -> dict:
    """Serialize the mixed dataclass/Pydantic ResolvedRequirements for a log or a print."""
    return {
        "payload": asdict(resolved.payload),
        "resolved_explicit_categories": [
            asdict(category) for category in resolved.resolved_explicit_categories
        ],
        "ambiguity_flags": [flag.model_dump() for flag in resolved.ambiguity_flags],
        "persona_facts": list(resolved.persona_facts),
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
