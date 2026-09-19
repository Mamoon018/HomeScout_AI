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
    ClarificationProviderError,
    ClarificationValidationError,
    DepthAssignmentProviderError,
    DepthAssignmentValidationError,
    ExtractionProviderError,
    ExtractionValidationError,
    InferenceProviderError,
    InferenceValidationError,
    InputTooShortError,
    MetricDefinitionProviderError,
    MetricDefinitionValidationError,
    UnsupportedLanguageError,
)
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_prompts.category_resolution_instruction import (
    build_flag_resolution_instruction as build_flag_resolution_text,
    build_mapping_few_shot_examples,
    build_resolution_few_shot_examples,
    build_taxonomy_mapping_instruction as build_taxonomy_mapping_text,
)
from src.services.deep_search.feature_prompts.clarification_instruction import (
    build_clarification_few_shot_examples,
    build_clarification_questions_instruction as build_clarification_questions_text,
)
from src.services.deep_search.feature_prompts.extraction_instruction import (
    BOUNDARY_RULES,
    BUCKET_DEFINITIONS,
    NEGATIVE_RULES,
    OUTPUT_RULES,
    TASK_STATEMENT,
    build_few_shot_examples,
)
from src.services.deep_search.feature_prompts.depth_assignment_instruction import (
    build_depth_assignment_few_shot_examples,
    build_depth_assignment_instruction as build_depth_assignment_text,
)
from src.services.deep_search.feature_prompts.inference_instruction import (
    build_inference_few_shot_examples,
    build_inference_instruction as build_inference_text,
)
from src.services.deep_search.feature_prompts.metric_definition_instruction import (
    build_metric_definition_few_shot_examples,
    build_metric_definition_instruction as build_metric_definition_text,
)
from src.services.deep_search.feature_schemas.amenity_taxonomy import (
    AMENITY_TAXONOMY_NODES,
    TAXONOMY_NODE_SET,
)
from src.services.deep_search.feature_schemas.schemas import (
    CLARIFICATION_QUESTIONS_SCHEMA_NAME,
    DEPTH_ASSIGNMENT_SCHEMA_NAME,
    EXTRACTION_SCHEMA_NAME,
    FLAG_RESOLUTION_SCHEMA_NAME,
    INFERRED_CATEGORIES_SCHEMA_NAME,
    MAX_METRICS_PER_BAND,
    METRIC_DEFINITION_SCHEMA_NAME,
    TAXONOMY_MAPPING_SCHEMA_NAME,
    AmbiguityFlag,
    CategoryMetricSet,
    CategoryResolutionRoute,
    ClarificationResult,
    DepthAssignmentResult,
    DepthLevel,
    ExtractedCategory,
    ExtractedRequirements,
    FlagResolutionResult,
    InferredCategoriesResult,
    InferredCategory,
    InferredCategoryEntry,
    MetricDefinitionResult,
    MetricEntry,
    MetricSpec,
    PayloadRecord,
    RequirementInterpretationState,
    ResolutionSource,
    ResolvedCategory,
    ResolvedRequirements,
    TaxonomyMappingResult,
    UserResponse,
    clarification_questions_json_schema,
    depth_assignment_json_schema,
    extraction_json_schema,
    flag_resolution_json_schema,
    inferred_categories_json_schema,
    metric_definition_json_schema,
    taxonomy_mapping_json_schema,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

MIN_INPUT_WORD_COUNT = 100
ENGLISH_LANGUAGE_CODE = "en"

# Log events the sample runner reads back to print stage 4's attempt trail, because the
# raw body is a local value inside the stage and is not carried on any contract.
PROVIDER_ATTEMPT_EVENT = "extraction.provider_attempt"
RAW_BODY_EVENT = "extraction.raw_body"

# `_call_providers` is shared by every mechanism's constrained call, so its attempt and raw
# body records carry no mechanism name; the `stage` field says which call they belong to.
# The runners read these records back to print the attempt trail and the raw body.
LLM_PROVIDER_ATTEMPT_EVENT = "llm_provider.attempt"
LLM_PROVIDER_RAW_BODY_EVENT = "llm_provider.raw_body"

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

    async def interpret(self, raw_input: str) -> RequirementInterpretationState:
        """Responsibility entry point; sequences the mechanisms and returns the state."""
        state = await self.parse_unstructured_input(raw_input)
        state = await self.run_explicit_category_resolution(state)
        state = await self.run_persona_driven_category_inference(state)
        state = await self.run_per_category_depth_calibration(state)
        return await self.run_per_category_metric_definition(state)

    async def parse_unstructured_input(self, raw_input: str) -> RequirementInterpretationState:
        """Mechanism 1: drive stages 1, 3, 4, and 5 of unstructured input parsing."""
        payload = self.intake_and_assemble_payload(raw_input)
        instruction = self.build_extraction_instruction(extraction_json_schema())
        extracted = await self.execute_and_validate(payload, instruction)
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

    async def execute_and_validate(
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
                body = await provider.generate_structured(
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

        try:
            extracted = _stamp_category_identities(extracted)
        except ExtractionValidationError:
            logger.info(
                json.dumps(
                    {
                        "event": "extraction.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "rejected",
                        "reason": "category_identity",
                    }
                )
            )
            raise

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
    # Mechanism 2 — Category resolution loop (2A, router, 2B)
    # ---------------------------------------------------------------------------------

    async def run_explicit_category_resolution(
        self,
        state: RequirementInterpretationState,
    ) -> RequirementInterpretationState:
        """Mechanism 2 workflow: 2A pass 1, router, maybe 2B and 2A pass 2, then return."""
        await self.resolve_explicit_categories(state)
        route = self.inspect_category_resolution(state)
        if route == "mechanism_3":
            return state

        await self.clarify_unmapped_categories(state)
        await self.resolve_category_flags(state)
        self.inspect_category_resolution(state)
        return state

    def inspect_category_resolution(
        self,
        state: RequirementInterpretationState,
    ) -> CategoryResolutionRoute:
        """Increment the pass counter, then emit 2B or Mechanism 3."""
        state.category_resolution_passes += 1

        if state.category_resolution_passes >= 2:
            route: CategoryResolutionRoute = "mechanism_3"
        elif state.resolved is None:
            route = "mechanism_3"
        elif not any(flag.target == "category" for flag in state.resolved.ambiguity_flags):
            route = "mechanism_3"
        else:
            route = "component_2b"

        logger.info(
            json.dumps(
                {
                    "event": "category_resolution.inspect",
                    "timestamp": _timestamp(),
                    "category_resolution_passes": state.category_resolution_passes,
                    "category_flag_count": (
                        _category_flag_count(state.resolved.ambiguity_flags)
                        if state.resolved is not None
                        else 0
                    ),
                    "route": route,
                }
            )
        )
        return route

    async def clarify_unmapped_categories(self, state: RequirementInterpretationState) -> None:
        """Generate questions, collect answers, persist them on the state."""
        instruction = self.build_clarification_questions_instruction(
            clarification_questions_json_schema()
        )
        result = await self.execute_clarification_questions(state, instruction)
        self.collect_clarification_responses(state, result)

    def build_clarification_questions_instruction(self, json_schema: dict) -> str:
        """2B Stage 1: assemble rules, closed schema, and two worked pairs. No taxonomy."""
        instruction = build_clarification_questions_text(json_schema)
        logger.info(
            json.dumps(
                {
                    "event": "clarification.instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "few_shot_count": len(build_clarification_few_shot_examples()),
                }
            )
        )
        logger.debug(
            json.dumps({"event": "clarification.instruction.text", "instruction": instruction})
        )
        return instruction

    async def execute_clarification_questions(
        self,
        state: RequirementInterpretationState,
        instruction: str,
    ) -> ClarificationResult:
        """2B Stage 2: one constrained call, schema then coverage, one coverage retry."""
        resolved = state.resolved
        assert resolved is not None  # the router only forwards here after 2A pass 1.

        json_schema = clarification_questions_json_schema()
        user_content = _render_clarification_user_content(state)
        submitted_ids = _submitted_category_flag_ids(resolved)

        body, answered_by = await self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=CLARIFICATION_QUESTIONS_SCHEMA_NAME,
            stage="execute_clarification_questions",
            provider_error_cls=ClarificationProviderError,
        )
        result = self._validate_clarification_schema(body, provider=answered_by)
        miss = _clarification_coverage_miss(result, submitted_ids)
        if miss is None:
            logger.info(
                json.dumps(
                    {
                        "event": "clarification.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "accepted",
                        "question_count": len(result.questions),
                    }
                )
            )
            return result

        logger.info(
            json.dumps(
                {
                    "event": "clarification.coverage_retry",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "reason": "category_id_coverage",
                    **miss,
                }
            )
        )
        body, answered_by = await self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=CLARIFICATION_QUESTIONS_SCHEMA_NAME,
            stage="execute_clarification_questions",
            provider_error_cls=ClarificationProviderError,
        )
        result = self._validate_clarification_schema(body, provider=answered_by)
        miss = _clarification_coverage_miss(result, submitted_ids)
        if miss is not None:
            logger.info(
                json.dumps(
                    {
                        "event": "clarification.rejected",
                        "timestamp": _timestamp(),
                        "stage": "execute_clarification_questions",
                        "provider": answered_by,
                        "reason": "category_id_coverage",
                        **miss,
                    }
                )
            )
            raise ClarificationValidationError(
                f"The body returned by {answered_by} did not cover the submitted category ids "
                f"(duplicates={miss['duplicates']}, unknown={miss['unknown']}, "
                f"missing={miss['missing']})",
                stage="execute_clarification_questions",
            )

        logger.info(
            json.dumps(
                {
                    "event": "clarification.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                    "question_count": len(result.questions),
                    "retried_coverage": True,
                }
            )
        )
        return result

    def collect_clarification_responses(
        self,
        state: RequirementInterpretationState,
        result: ClarificationResult,
    ) -> None:
        """2B Stage 3: numbered CLI; persist one UserResponse per category flag."""
        resolved = state.resolved
        assert resolved is not None

        questions_by_id = {question.category_id: question for question in result.questions}
        submitted_flags = [
            flag for flag in resolved.ambiguity_flags if flag.target == "category"
        ]

        for flag in submitted_flags:
            assert flag.category_id is not None
            question = questions_by_id[flag.category_id]
            selected = _prompt_clarification_option(flag.phrase, question.question, question.options)
            if selected == "other":
                response_text = _prompt_other_description()
            else:
                response_text = selected
            state.user_responses[flag.category_id] = UserResponse(
                question=question.question,
                options=list(question.options),
                response=response_text,
            )

        logger.info(
            json.dumps(
                {
                    "event": "clarification.collected",
                    "timestamp": _timestamp(),
                    "response_count": len(state.user_responses),
                    "category_ids": sorted(state.user_responses),
                }
            )
        )

    def _validate_clarification_schema(self, body: dict, *, provider: str) -> ClarificationResult:
        """Independent second check: reject a body that is not a closed ClarificationResult."""
        try:
            return ClarificationResult.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "clarification.validated",
                        "timestamp": _timestamp(),
                        "provider": provider,
                        "verdict": "rejected",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise ClarificationValidationError(
                f"The body returned by {provider} does not match the clarification contract",
                stage="execute_clarification_questions",
            ) from exc

    async def resolve_explicit_categories(
        self,
        state: RequirementInterpretationState,
    ) -> RequirementInterpretationState:
        """Component 2A: Operation 1 always, Operation 2 when the gate opens."""
        instruction = self.build_taxonomy_mapping_instruction(taxonomy_mapping_json_schema())
        mapping = await self.execute_taxonomy_mapping(state, instruction)
        self.assemble_resolved_requirements(state, mapping)
        await self.resolve_category_flags(state)
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

    async def execute_taxonomy_mapping(
        self,
        state: RequirementInterpretationState,
        instruction: str,
    ) -> TaxonomyMappingResult:
        """Op1 Stage 2: one constrained call over all raw categories, then validate."""
        json_schema = taxonomy_mapping_json_schema()
        user_content = _render_extracted(state.extracted)
        body, answered_by = await self._call_providers(
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
        self._assert_mapping_covers_extracted(
            mapping,
            state.extracted,
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
                    "unmapped_count": len(mapping.unmapped_category_ids),
                }
            )
        )
        return mapping

    def assemble_resolved_requirements(
        self,
        state: RequirementInterpretationState,
        mapping: TaxonomyMappingResult,
    ) -> ResolvedRequirements:
        """Op1 Stage 3: attach name/chars by category_id, flag unmapped ids, set state.resolved."""
        by_id = _explicit_categories_by_id(state.extracted)

        resolved_categories: list[ResolvedCategory] = []
        for entry in mapping.resolved_categories:
            source = by_id[entry.category_id]
            resolved_categories.append(
                ResolvedCategory(
                    category_id=entry.category_id,
                    taxonomy_node=entry.taxonomy_node,
                    raw_name=source.name,
                    characteristics=list(source.characteristics),
                    provenance="confident",
                )
            )

        # Characteristic and persona flags pass through. Category flags are rebuilt from
        # unmapped ids so each category_id appears at most once as a category flag.
        flags: list[AmbiguityFlag] = [
            flag for flag in state.extracted.ambiguity_flags if flag.target != "category"
        ]
        for category_id in mapping.unmapped_category_ids:
            source = by_id[category_id]
            flags.append(
                AmbiguityFlag(
                    phrase=source.name,
                    target="category",
                    category=None,
                    characteristic=None,
                    category_id=category_id,
                )
            )

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

    async def resolve_category_flags(self, state: RequirementInterpretationState) -> None:
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
            if flag.category_id is None:
                continue
            response = state.user_responses.get(flag.category_id)
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
        result = await self.execute_flag_resolution(pairs, instruction)
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

    async def execute_flag_resolution(
        self,
        pairs: list[tuple[AmbiguityFlag, UserResponse]],
        instruction: str,
    ) -> FlagResolutionResult:
        """Op2 Stage 5: one constrained call over all {flag, response} pairs, then validate."""
        json_schema = flag_resolution_json_schema()
        user_content = _render_pairs(pairs)
        body, answered_by = await self._call_providers(
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
        self._assert_resolution_covers_pairs(
            result,
            pairs,
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

        by_id = _explicit_categories_by_id(state.extracted)
        for entry in result.resolved_categories:
            source = by_id[entry.category_id]
            resolved.resolved_explicit_categories.append(
                ResolvedCategory(
                    category_id=entry.category_id,
                    taxonomy_node=entry.taxonomy_node,
                    raw_name=source.name,
                    characteristics=list(source.characteristics),
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

    # ---------------------------------------------------------------------------------
    # Mechanism 4 — Persona-driven category inference
    # ---------------------------------------------------------------------------------

    async def run_persona_driven_category_inference(
        self,
        state: RequirementInterpretationState,
    ) -> RequirementInterpretationState:
        """Mechanism 4 workflow: instruction, one constrained call, then strip and write."""
        assert state.resolved is not None  # Mechanism 2 always sets this before M4 runs.

        instruction = self.build_inference_instruction(inferred_categories_json_schema())
        body = await self.execute_category_inference(state, instruction)
        self.write_inferred_categories(state, body)
        return state

    def build_inference_instruction(self, json_schema: dict) -> str:
        """Stage 2: assemble evidence, distinctness, taxonomy, closed schema, six pairs."""
        instruction = build_inference_text(json_schema)
        logger.info(
            json.dumps(
                {
                    "event": "inference.instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "taxonomy_node_count": len(AMENITY_TAXONOMY_NODES),
                    "few_shot_count": len(build_inference_few_shot_examples()),
                }
            )
        )
        logger.debug(
            json.dumps({"event": "inference.instruction.text", "instruction": instruction})
        )
        return instruction

    async def execute_category_inference(
        self,
        state: RequirementInterpretationState,
        instruction: str,
    ) -> InferredCategoriesResult:
        """Stage 3: one constrained call, schema then taxonomy-set check. No strip."""
        json_schema = inferred_categories_json_schema()
        user_content = _render_inference_user_content(state)
        body, answered_by = await self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=INFERRED_CATEGORIES_SCHEMA_NAME,
            stage="execute_category_inference",
            provider_error_cls=InferenceProviderError,
        )

        try:
            result = InferredCategoriesResult.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "inference.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "rejected",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise InferenceValidationError(
                f"The body returned by {answered_by} does not match the inference contract",
                stage="execute_category_inference",
            ) from exc

        unknown = [
            entry.taxonomy_node
            for entry in result.inferred_categories
            if entry.taxonomy_node not in TAXONOMY_NODE_SET
        ]
        if unknown:
            logger.info(
                json.dumps(
                    {
                        "event": "inference.rejected",
                        "timestamp": _timestamp(),
                        "stage": "execute_category_inference",
                        "provider": answered_by,
                        "reason": "unknown_taxonomy_node",
                        "nodes": unknown,
                    }
                )
            )
            raise InferenceValidationError(
                f"The body returned by {answered_by} carried nodes outside the taxonomy: "
                f"{unknown}",
                stage="execute_category_inference",
            )

        logger.info(
            json.dumps(
                {
                    "event": "inference.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                    "inferred_count": len(result.inferred_categories),
                }
            )
        )
        return result

    def write_inferred_categories(
        self,
        state: RequirementInterpretationState,
        body: InferredCategoriesResult,
    ) -> None:
        """Stage 4: drop exact-node collisions, stamp ids, write the inferred list."""
        resolved = state.resolved
        assert resolved is not None

        explicit_nodes = {
            category.taxonomy_node for category in resolved.resolved_explicit_categories
        }
        kept_entries: list[InferredCategoryEntry] = []
        seen_inferred: set[str] = set()

        for entry in body.inferred_categories:
            if entry.taxonomy_node in explicit_nodes:
                logger.info(
                    json.dumps(
                        {
                            "event": "inference.stripped",
                            "timestamp": _timestamp(),
                            "taxonomy_node": entry.taxonomy_node,
                            "reason": "exact_explicit_duplicate",
                        }
                    )
                )
                continue
            if entry.taxonomy_node in seen_inferred:
                logger.info(
                    json.dumps(
                        {
                            "event": "inference.stripped",
                            "timestamp": _timestamp(),
                            "taxonomy_node": entry.taxonomy_node,
                            "reason": "duplicate_inferred_node",
                        }
                    )
                )
                continue
            seen_inferred.add(entry.taxonomy_node)
            kept_entries.append(entry)

        extracted_ids = [
            category.category_id
            for category in state.extracted.explicit_categories
            if category.category_id is not None
        ]
        next_id = max(extracted_ids) + 1 if extracted_ids else 0
        stored: list[InferredCategory] = []
        for entry in kept_entries:
            stored.append(
                InferredCategory(
                    taxonomy_node=entry.taxonomy_node,
                    category_id=next_id,
                    reasoning=entry.reasoning,
                )
            )
            next_id += 1

        state.inferred_categories = stored

        logger.info(
            json.dumps(
                {
                    "event": "inferred_categories.written",
                    "timestamp": _timestamp(),
                    "inferred_count": len(stored),
                    "category_ids": [entry.category_id for entry in stored],
                }
            )
        )

    # ---------------------------------------------------------------------------------
    # Mechanism 5 — Per-category depth calibration
    # ---------------------------------------------------------------------------------

    async def run_per_category_depth_calibration(
        self,
        state: RequirementInterpretationState,
    ) -> RequirementInterpretationState:
        """Mechanism 5 workflow: skip both-empty, else instruction, one call, then stamp."""
        assert state.resolved is not None  # Mechanism 2 always sets this before M5 runs.

        if (
            not state.resolved.resolved_explicit_categories
            and not state.inferred_categories
        ):
            logger.info(
                json.dumps(
                    {
                        "event": "depth_assignment.skipped",
                        "timestamp": _timestamp(),
                        "reason": "no_categories",
                    }
                )
            )
            return state

        instruction = self.build_depth_assignment_instruction(
            depth_assignment_json_schema()
        )
        body = await self.execute_depth_assignment(state, instruction)
        self.stamp_category_depths(state, body)
        return state

    def build_depth_assignment_instruction(self, json_schema: dict) -> str:
        """Assemble scale, floors, triggers, metric contract, closed schema, six pairs."""
        instruction = build_depth_assignment_text(json_schema)
        logger.info(
            json.dumps(
                {
                    "event": "depth_assignment.instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "few_shot_count": len(build_depth_assignment_few_shot_examples()),
                }
            )
        )
        logger.debug(
            json.dumps(
                {"event": "depth_assignment.instruction.text", "instruction": instruction}
            )
        )
        return instruction

    async def execute_depth_assignment(
        self,
        state: RequirementInterpretationState,
        instruction: str,
    ) -> DepthAssignmentResult:
        """One constrained call, then schema, id coverage, and explicit-floor checks."""
        json_schema = depth_assignment_json_schema()
        user_content = _render_depth_assignment_user_content(state)
        body, answered_by = await self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=DEPTH_ASSIGNMENT_SCHEMA_NAME,
            stage="execute_depth_assignment",
            provider_error_cls=DepthAssignmentProviderError,
        )

        try:
            result = DepthAssignmentResult.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "depth_assignment.validated",
                        "timestamp": _timestamp(),
                        "provider": answered_by,
                        "verdict": "rejected",
                        "reason": "schema",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise DepthAssignmentValidationError(
                f"The body returned by {answered_by} does not match the depth-assignment "
                "contract",
                stage="execute_depth_assignment",
            ) from exc

        submitted_ids = _submitted_depth_category_ids(state)
        returned_ids = [entry.category_id for entry in result.assignments]
        coverage_miss = _depth_id_coverage_miss(returned_ids, submitted_ids)
        if coverage_miss is not None:
            logger.info(
                json.dumps(
                    {
                        "event": "depth_assignment.rejected",
                        "timestamp": _timestamp(),
                        "stage": "execute_depth_assignment",
                        "provider": answered_by,
                        "reason": "category_id_coverage",
                        **coverage_miss,
                    }
                )
            )
            raise DepthAssignmentValidationError(
                f"The body returned by {answered_by} did not cover the submitted "
                f"category ids: {coverage_miss}",
                stage="execute_depth_assignment",
            )

        resolved = state.resolved
        assert resolved is not None
        explicit_ids = {
            category.category_id for category in resolved.resolved_explicit_categories
        }
        explicit_below_floor = [
            entry.category_id
            for entry in result.assignments
            if entry.category_id in explicit_ids and entry.depth == "basic_profile"
        ]
        if explicit_below_floor:
            logger.info(
                json.dumps(
                    {
                        "event": "depth_assignment.rejected",
                        "timestamp": _timestamp(),
                        "stage": "execute_depth_assignment",
                        "provider": answered_by,
                        "reason": "explicit_below_floor",
                        "category_ids": explicit_below_floor,
                    }
                )
            )
            raise DepthAssignmentValidationError(
                f"The body returned by {answered_by} assigned basic_profile to explicit "
                f"category ids: {explicit_below_floor}",
                stage="execute_depth_assignment",
            )

        logger.info(
            json.dumps(
                {
                    "event": "depth_assignment.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                    "assignment_count": len(result.assignments),
                }
            )
        )
        return result

    def stamp_category_depths(
        self,
        state: RequirementInterpretationState,
        body: DepthAssignmentResult,
    ) -> None:
        """Write accepted depths onto matching explicit and inferred entries by id."""
        resolved = state.resolved
        assert resolved is not None

        explicit_by_id = {
            category.category_id: category
            for category in resolved.resolved_explicit_categories
        }
        inferred_by_id = {
            category.category_id: category for category in state.inferred_categories
        }

        explicit_stamped = 0
        inferred_stamped = 0
        for assignment in body.assignments:
            explicit_entry = explicit_by_id.get(assignment.category_id)
            if explicit_entry is not None:
                explicit_entry.depth = assignment.depth
                explicit_stamped += 1
                continue
            inferred_entry = inferred_by_id[assignment.category_id]
            inferred_entry.depth = assignment.depth
            inferred_stamped += 1

        logger.info(
            json.dumps(
                {
                    "event": "depth_assignment.stamped",
                    "timestamp": _timestamp(),
                    "explicit_stamped": explicit_stamped,
                    "inferred_stamped": inferred_stamped,
                    "assignments": [
                        {"category_id": entry.category_id, "depth": entry.depth}
                        for entry in body.assignments
                    ],
                }
            )
        )

    async def run_per_category_metric_definition(
        self,
        state: RequirementInterpretationState,
    ) -> RequirementInterpretationState:
        """Mechanism 6 workflow: skip when nothing is eligible, else instruction, call, filter, write."""
        assert state.resolved is not None  # Mechanism 2 always sets this before M6 runs.

        categories = _ordered_categories(state)
        assert all(
            category.depth is not None for category in categories
        )  # Mechanism 5 stamps depth on every category before M6 runs.

        if not categories:
            logger.info(
                json.dumps(
                    {
                        "event": "metric_definition.skipped",
                        "timestamp": _timestamp(),
                        "reason": "no_categories",
                    }
                )
            )
            state.category_metrics = []
            return state

        if not any(_is_metric_eligible(category) for category in categories):
            logger.info(
                json.dumps(
                    {
                        "event": "metric_definition.skipped",
                        "timestamp": _timestamp(),
                        "reason": "no_eligible_categories",
                    }
                )
            )
            self.write_category_metrics(state, {})
            return state

        instruction = self.build_metric_definition_instruction(
            metric_definition_json_schema()
        )
        body = await self.execute_metric_definition(state, instruction)
        survivors, _ = self.apply_metric_contract(state, body)
        self.report_metric_shortfalls(state, survivors)
        self.write_category_metrics(state, survivors)
        return state

    def build_metric_definition_instruction(self, json_schema: dict) -> str:
        """Assemble bands, contract, fixed dimensions, tie rules, closed schema, worked pairs."""
        instruction = build_metric_definition_text(json_schema)
        logger.info(
            json.dumps(
                {
                    "event": "metric_definition.instruction.built",
                    "timestamp": _timestamp(),
                    "instruction_length": len(instruction),
                    "few_shot_count": len(build_metric_definition_few_shot_examples()),
                }
            )
        )
        logger.debug(
            json.dumps(
                {"event": "metric_definition.instruction.text", "instruction": instruction}
            )
        )
        return instruction

    async def execute_metric_definition(
        self,
        state: RequirementInterpretationState,
        instruction: str,
    ) -> MetricDefinitionResult:
        """One constrained call, then schema and id-set validation of the body."""
        json_schema = metric_definition_json_schema()
        user_content = _render_metric_definition_user_content(state)
        body, answered_by = await self._call_providers(
            instruction=instruction,
            user_content=user_content,
            json_schema=json_schema,
            schema_name=METRIC_DEFINITION_SCHEMA_NAME,
            stage="execute_metric_definition",
            provider_error_cls=MetricDefinitionProviderError,
        )

        try:
            result = MetricDefinitionResult.model_validate(body)
        except ValidationError as exc:
            logger.info(
                json.dumps(
                    {
                        "event": "metric_definition.rejected",
                        "timestamp": _timestamp(),
                        "stage": "execute_metric_definition",
                        "provider": answered_by,
                        "reason": "schema",
                        "error_count": exc.error_count(),
                    }
                )
            )
            raise MetricDefinitionValidationError(
                f"The body returned by {answered_by} does not match the "
                "metric-definition contract",
                stage="execute_metric_definition",
            ) from exc

        submitted_ids = [
            category.category_id
            for category in _ordered_categories(state)
            if _is_metric_eligible(category)
        ]
        returned_ids = [entry.category_id for entry in result.categories]
        coverage_miss = _depth_id_coverage_miss(returned_ids, submitted_ids)
        if coverage_miss is not None:
            logger.info(
                json.dumps(
                    {
                        "event": "metric_definition.rejected",
                        "timestamp": _timestamp(),
                        "stage": "execute_metric_definition",
                        "provider": answered_by,
                        "reason": "category_id_coverage",
                        **coverage_miss,
                    }
                )
            )
            raise MetricDefinitionValidationError(
                f"The body returned by {answered_by} did not cover the submitted "
                f"category ids: {coverage_miss}",
                stage="execute_metric_definition",
            )

        logger.info(
            json.dumps(
                {
                    "event": "metric_definition.validated",
                    "timestamp": _timestamp(),
                    "provider": answered_by,
                    "verdict": "accepted",
                    "category_count": len(result.categories),
                    "metric_count": sum(len(entry.metrics) for entry in result.categories),
                }
            )
        )
        return result

    def apply_metric_contract(
        self,
        state: RequirementInterpretationState,
        body: MetricDefinitionResult,
    ) -> tuple[dict[int, list[MetricSpec]], list[dict]]:
        """Drop each metric that fails K1 to K6; return survivors by id and the rejections."""
        depth_by_id = {
            category.category_id: category.depth for category in _ordered_categories(state)
        }
        survivors: dict[int, list[MetricSpec]] = {}
        rejections: list[dict] = []

        for entry in body.categories:
            depth = depth_by_id[entry.category_id]
            assert depth is not None
            kept: list[MetricSpec] = []
            kept_labels: set[str] = set()
            band_counts = {"operating_details": 0, "specific_attributes": 0}

            for metric in entry.metrics:
                label_key = metric.label.strip().casefold()
                rule = _metric_rule_failure(metric, depth)
                if rule is None and label_key in kept_labels:
                    rule = "duplicate_label"
                if rule is None and band_counts[metric.band] >= MAX_METRICS_PER_BAND:
                    rule = "band_cap"

                if rule is not None:
                    record = {
                        "category_id": entry.category_id,
                        "label": metric.label,
                        "rule": rule,
                    }
                    rejections.append(record)
                    logger.info(
                        json.dumps(
                            {
                                "event": "metric_definition.metric_rejected",
                                "timestamp": _timestamp(),
                                **record,
                            }
                        )
                    )
                    continue

                kept_labels.add(label_key)
                band_counts[metric.band] += 1
                kept.append(_to_metric_spec(metric))

            survivors[entry.category_id] = kept

        return survivors, rejections

    def report_metric_shortfalls(
        self,
        state: RequirementInterpretationState,
        survivors: dict[int, list[MetricSpec]],
    ) -> list[dict]:
        """Log each eligible category left without a required band; not a failure."""
        shortfalls: list[dict] = []
        for category in _ordered_categories(state):
            if not _is_metric_eligible(category):
                continue
            kept = survivors.get(category.category_id, [])
            required_bands = (
                ["operating_details"]
                if category.depth == "operating_details"
                else ["operating_details", "specific_attributes"]
            )
            empty_bands = [
                band
                for band in required_bands
                if not any(metric.band == band for metric in kept)
            ]
            if not empty_bands:
                continue
            record = {
                "category_id": category.category_id,
                "taxonomy_node": category.taxonomy_node,
                "depth": category.depth,
                "empty_bands": empty_bands,
            }
            shortfalls.append(record)
            logger.info(
                json.dumps(
                    {
                        "event": "metric_definition.category_underspecified",
                        "timestamp": _timestamp(),
                        **record,
                    }
                )
            )
        return shortfalls

    def write_category_metrics(
        self,
        state: RequirementInterpretationState,
        survivors: dict[int, list[MetricSpec]],
    ) -> None:
        """Write one CategoryMetricSet per category: survivors if eligible, else None."""
        sets = [
            CategoryMetricSet(
                category_id=category.category_id,
                taxonomy_node=category.taxonomy_node,
                metrics=(
                    survivors.get(category.category_id, [])
                    if _is_metric_eligible(category)
                    else None
                ),
            )
            for category in _ordered_categories(state)
        ]
        state.category_metrics = sets

        logger.info(
            json.dumps(
                {
                    "event": "metric_definition.written",
                    "timestamp": _timestamp(),
                    "set_count": len(sets),
                    "sets": [
                        {
                            "category_id": metric_set.category_id,
                            "metric_count": (
                                None
                                if metric_set.metrics is None
                                else len(metric_set.metrics)
                            ),
                        }
                        for metric_set in sets
                    ],
                }
            )
        )

    async def aclose(self) -> None:
        """Close each provider's HTTP session after a run."""
        for provider in self._providers:
            await provider.aclose()

    async def _call_providers(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
        stage: str,
        provider_error_cls: type[Exception] = CategoryMappingProviderError,
    ) -> tuple[dict, str]:
        """Try providers in the bound order; return the first body or a typed provider error."""
        body: dict | None = None
        answered_by: str | None = None

        for provider in self._providers:
            try:
                body = await provider.generate_structured(
                    instruction=instruction,
                    user_content=user_content,
                    json_schema=json_schema,
                    schema_name=schema_name,
                )
            except LLMProviderError as exc:
                # The adapter wraps the SDK error; the SDK's own message (for example an
                # HTTP 400 naming a rejected schema path) is only on __cause__.
                detail = str(exc)
                if exc.__cause__ is not None:
                    detail = f"{detail} | cause: {type(exc.__cause__).__name__}: {exc.__cause__}"
                logger.info(
                    json.dumps(
                        {
                            "event": LLM_PROVIDER_ATTEMPT_EVENT,
                            "timestamp": _timestamp(),
                            "stage": stage,
                            "provider": provider.name,
                            "model": provider.model,
                            "outcome": "failed",
                            "detail": detail,
                        }
                    )
                )
                continue

            answered_by = provider.name
            logger.info(
                json.dumps(
                    {
                        "event": LLM_PROVIDER_ATTEMPT_EVENT,
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
                        "event": "llm_provider.rejected",
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "reason": "no_provider_answered",
                        "attempted": [provider.name for provider in self._providers],
                    }
                )
            )
            raise provider_error_cls(
                f"No LLM provider returned a {stage} body", stage=stage
            )

        logger.debug(
            json.dumps(
                {
                    "event": LLM_PROVIDER_RAW_BODY_EVENT,
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

    def _assert_mapping_covers_extracted(
        self,
        mapping: TaxonomyMappingResult,
        extracted: ExtractedRequirements,
        *,
        provider: str,
        stage: str,
    ) -> None:
        """Every extracted category_id must appear once in mapped or unmapped, never both."""
        known_ids = {category.category_id for category in extracted.explicit_categories}
        mapped_ids = [entry.category_id for entry in mapping.resolved_categories]
        unmapped_ids = list(mapping.unmapped_category_ids)
        returned_ids = mapped_ids + unmapped_ids
        duplicates = [category_id for category_id in returned_ids if returned_ids.count(category_id) > 1]
        unique_duplicates = sorted(set(duplicates))
        unknown = sorted({category_id for category_id in returned_ids if category_id not in known_ids})
        missing = sorted(known_ids - set(returned_ids))
        if unique_duplicates or unknown or missing:
            logger.info(
                json.dumps(
                    {
                        "event": "category_resolution.rejected",
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "provider": provider,
                        "reason": "category_id_coverage",
                        "duplicates": unique_duplicates,
                        "unknown": unknown,
                        "missing": missing,
                    }
                )
            )
            raise CategoryMappingValidationError(
                f"The body returned by {provider} did not partition extracted category ids "
                f"(duplicates={unique_duplicates}, unknown={unknown}, missing={missing})",
                stage=stage,
            )

    def _assert_resolution_covers_pairs(
        self,
        result: FlagResolutionResult,
        pairs: list[tuple[AmbiguityFlag, UserResponse]],
        *,
        provider: str,
        stage: str,
    ) -> None:
        """Every submitted category flag must come back as exactly one resolved entry."""
        submitted_ids = [flag.category_id for flag, _ in pairs]
        returned_ids = [entry.category_id for entry in result.resolved_categories]
        duplicates = [category_id for category_id in returned_ids if returned_ids.count(category_id) > 1]
        unique_duplicates = sorted(set(duplicates))
        unknown = sorted(set(returned_ids) - set(submitted_ids))
        missing = sorted(set(submitted_ids) - set(returned_ids))
        if unique_duplicates or unknown or missing:
            logger.info(
                json.dumps(
                    {
                        "event": "category_resolution.rejected",
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "provider": provider,
                        "reason": "category_id_coverage",
                        "duplicates": unique_duplicates,
                        "unknown": unknown,
                        "missing": missing,
                    }
                )
            )
            raise CategoryMappingValidationError(
                f"The body returned by {provider} did not cover the submitted category ids "
                f"(duplicates={unique_duplicates}, unknown={unknown}, missing={missing})",
                stage=stage,
            )


def create_requirement_interpretation(settings: Settings) -> UserRequirementsInterpretation:
    """Composition root: bind the provider chain that LLM_PROVIDER_ORDER names."""
    return UserRequirementsInterpretation(create_llm_providers(settings))


def _stamp_category_identities(extracted: ExtractedRequirements) -> ExtractedRequirements:
    """Label each explicit category by list position and attach that id to category flags."""
    labeled_categories = [
        category.model_copy(update={"category_id": index})
        for index, category in enumerate(extracted.explicit_categories)
    ]
    by_name: dict[str, list[ExtractedCategory]] = {}
    for category in labeled_categories:
        by_name.setdefault(category.name, []).append(category)

    stamped_flags: list[AmbiguityFlag] = []
    for flag in extracted.ambiguity_flags:
        if flag.target != "category":
            stamped_flags.append(flag.model_copy(update={"category_id": None}))
            continue
        matches = by_name.get(flag.phrase, [])
        if len(matches) != 1:
            raise ExtractionValidationError(
                "Every category flag must resolve to exactly one extracted category; "
                f"{len(matches)} explicit_categories entries matched phrase {flag.phrase!r}"
            )
        stamped_flags.append(flag.model_copy(update={"category_id": matches[0].category_id}))

    return extracted.model_copy(
        update={"explicit_categories": labeled_categories, "ambiguity_flags": stamped_flags}
    )


def _explicit_categories_by_id(extracted: ExtractedRequirements) -> dict[int, ExtractedCategory]:
    return {
        category.category_id: category
        for category in extracted.explicit_categories
        if category.category_id is not None
    }


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


def _render_inference_user_content(state: RequirementInterpretationState) -> str:
    """Persona facts, explicit nodes plus characteristics, and payload as JSON."""
    resolved = state.resolved
    assert resolved is not None
    payload = {
        "persona_facts": list(resolved.persona_facts),
        "resolved_explicit_categories": [
            {
                "taxonomy_node": category.taxonomy_node,
                "characteristics": list(category.characteristics),
            }
            for category in resolved.resolved_explicit_categories
        ],
        "payload": asdict(state.payload),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _render_depth_assignment_user_content(state: RequirementInterpretationState) -> str:
    """Payload, persona facts, and origin-labeled category rows as JSON."""
    resolved = state.resolved
    assert resolved is not None
    categories: list[dict] = []
    for category in resolved.resolved_explicit_categories:
        categories.append(
            {
                "category_id": category.category_id,
                "taxonomy_node": category.taxonomy_node,
                "origin": "explicit",
                "characteristics": list(category.characteristics),
            }
        )
    for category in state.inferred_categories:
        categories.append(
            {
                "category_id": category.category_id,
                "taxonomy_node": category.taxonomy_node,
                "origin": "inferred",
                "reasoning": category.reasoning,
            }
        )
    payload = {
        "payload": {"normalized_text": state.payload.normalized_text},
        "persona_facts": list(resolved.persona_facts),
        "categories": categories,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _submitted_depth_category_ids(state: RequirementInterpretationState) -> list[int]:
    """Explicit ids then inferred ids, in list order."""
    resolved = state.resolved
    assert resolved is not None
    return [
        category.category_id for category in resolved.resolved_explicit_categories
    ] + [category.category_id for category in state.inferred_categories]


def _depth_id_coverage_miss(
    returned_ids: list[int],
    submitted_ids: list[int],
) -> dict[str, list[int]] | None:
    """None when returned ids equal submitted ids with no duplicates; else the miss."""
    duplicates = [
        category_id for category_id in returned_ids if returned_ids.count(category_id) > 1
    ]
    unique_duplicates = sorted(set(duplicates))
    unknown = sorted(set(returned_ids) - set(submitted_ids))
    missing = sorted(set(submitted_ids) - set(returned_ids))
    if unique_duplicates or unknown or missing:
        return {"duplicates": unique_duplicates, "unknown": unknown, "missing": missing}
    return None


def _ordered_categories(
    state: RequirementInterpretationState,
) -> list[ResolvedCategory | InferredCategory]:
    """Explicit entries then inferred entries, in list order."""
    resolved = state.resolved
    assert resolved is not None
    return [*resolved.resolved_explicit_categories, *state.inferred_categories]


def _is_metric_eligible(category: ResolvedCategory | InferredCategory) -> bool:
    """True when the assigned depth authorizes dynamic metrics."""
    return category.depth in ("operating_details", "specific_attributes")


def _render_metric_definition_user_content(state: RequirementInterpretationState) -> str:
    """Payload, persona facts, eligible origin-and-depth-labeled rows, and leftover flags."""
    resolved = state.resolved
    assert resolved is not None
    categories: list[dict] = []
    for category in _ordered_categories(state):
        if not _is_metric_eligible(category):
            continue
        if isinstance(category, ResolvedCategory):
            categories.append(
                {
                    "category_id": category.category_id,
                    "taxonomy_node": category.taxonomy_node,
                    "origin": "explicit",
                    "depth": category.depth,
                    "characteristics": list(category.characteristics),
                }
            )
        else:
            categories.append(
                {
                    "category_id": category.category_id,
                    "taxonomy_node": category.taxonomy_node,
                    "origin": "inferred",
                    "depth": category.depth,
                    "reasoning": category.reasoning,
                }
            )
    leftover_flags = [
        {
            "phrase": flag.phrase,
            "target": flag.target,
            "category": flag.category,
            "characteristic": flag.characteristic,
        }
        for flag in resolved.ambiguity_flags
        if flag.target in ("characteristic", "persona")
    ]
    payload = {
        "payload": {"normalized_text": state.payload.normalized_text},
        "persona_facts": list(resolved.persona_facts),
        "categories": categories,
        "leftover_flags": leftover_flags,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _metric_rule_failure(entry: MetricEntry, depth: DepthLevel) -> str | None:
    """First failed rule of K1 to K4 for one metric, or None when it passes them."""
    texts = (
        entry.label,
        entry.question,
        entry.verification,
        entry.resolution_source.target,
    )
    if any(not text.strip() for text in texts):
        return "text_completeness"

    has_unit = bool(entry.unit and entry.unit.strip())
    enum_members = [member.strip() for member in entry.enum_values if member.strip()]
    if entry.value_type == "number_with_unit":
        parameters_ok = has_unit and not entry.enum_values
    elif entry.value_type == "enum":
        parameters_ok = not has_unit and len(set(enum_members)) >= 2
    else:
        parameters_ok = not has_unit and not entry.enum_values
    if not parameters_ok:
        return "value_type_parameters"

    if entry.band == "specific_attributes" and depth != "specific_attributes":
        return "band_above_depth"
    if entry.resolution_source.tool == "firecrawl" and entry.band != "specific_attributes":
        return "tool_not_allowed_for_band"
    return None


def _to_metric_spec(entry: MetricEntry) -> MetricSpec:
    """Wire metric to stored metric, text trimmed."""
    return MetricSpec(
        label=entry.label.strip(),
        question=entry.question.strip(),
        value_type=entry.value_type,
        unit=entry.unit.strip() if entry.unit and entry.unit.strip() else None,
        enum_values=[member.strip() for member in entry.enum_values],
        resolution_source=ResolutionSource(
            tool=entry.resolution_source.tool,
            target=entry.resolution_source.target.strip(),
        ),
        verification=entry.verification.strip(),
        null_policy=entry.null_policy,
        band=entry.band,
    )


def _render_clarification_user_content(state: RequirementInterpretationState) -> str:
    """Submitted flags plus grounding, the user content of the 2B generation call."""
    resolved = state.resolved
    assert resolved is not None
    payload = {
        "submitted_flags": [
            {"category_id": flag.category_id, "category": flag.phrase}
            for flag in resolved.ambiguity_flags
            if flag.target == "category"
        ],
        "resolved_explicit_categories": [
            asdict(category) for category in resolved.resolved_explicit_categories
        ],
        "payload": asdict(resolved.payload),
        "persona_facts": list(resolved.persona_facts),
        "ambiguity_flags": [flag.model_dump() for flag in resolved.ambiguity_flags],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _submitted_category_flag_ids(resolved: ResolvedRequirements) -> list[int]:
    return [
        flag.category_id
        for flag in resolved.ambiguity_flags
        if flag.target == "category" and flag.category_id is not None
    ]


def _clarification_coverage_miss(
    result: ClarificationResult,
    submitted_ids: list[int],
) -> dict[str, list[int]] | None:
    """None when returned ids equal submitted ids with no duplicates; else the miss."""
    returned_ids = [question.category_id for question in result.questions]
    duplicates = [category_id for category_id in returned_ids if returned_ids.count(category_id) > 1]
    unique_duplicates = sorted(set(duplicates))
    unknown = sorted(set(returned_ids) - set(submitted_ids))
    missing = sorted(set(submitted_ids) - set(returned_ids))
    if unique_duplicates or unknown or missing:
        return {"duplicates": unique_duplicates, "unknown": unknown, "missing": missing}
    return None


_CLARIFICATION_PREFACE = (
    "This category could not be mapped to a known amenity type. Please pick what you "
    "meant, not a new need."
)


def _prompt_clarification_option(category: str, question: str, options: list[str]) -> str:
    """Print one question and block until the customer types a valid option index."""
    while True:
        print(_CLARIFICATION_PREFACE)
        print(f"Category: {category}")
        print(f"Question: {question}")
        for index, option in enumerate(options, start=1):
            print(f"  {index}. {option}")
        raw = input("Enter a number (1-5): ").strip()
        if not raw:
            continue
        try:
            chosen = int(raw)
        except ValueError:
            continue
        if chosen < 1 or chosen > len(options):
            continue
        return options[chosen - 1]


def _prompt_other_description() -> str:
    """Block until the customer types a non-empty description for the 'other' option."""
    while True:
        description = input("Please describe what you meant: ").strip()
        if description:
            return description


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
