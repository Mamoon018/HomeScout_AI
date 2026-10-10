import json
import logging
from datetime import datetime, timezone

from src.clients.llm_provider import (
    StructuredLLMCaller,
    create_structured_llm_caller,
)
from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.services.deep_search.amenity_search import (
    AmenitySearch,
    create_amenity_search,
)
from src.services.deep_search.feature_schemas.schemas import (
    RequirementInterpretationState,
)
from src.services.deep_search.requirement_interpretation import (
    UserRequirementsInterpretation,
    create_requirement_interpretation,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

FEATURE_RUN_STARTED_EVENT = "feature.run_started"
FEATURE_INTERPRETATION_COMPLETED_EVENT = "feature.interpretation_completed"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeepSearch:
    """The Deep Search feature: it owns the one shared LLM caller and sequences R1 then R2.

    D6 is realized here. The caller is built once at the composition root and injected into
    both `UserRequirementsInterpretation` (R1) and `AmenitySearch` (R2) with `owns_caller`
    False, so this feature is the single owner that closes it once.
    """

    def __init__(
        self,
        *,
        interpretation: UserRequirementsInterpretation,
        amenity_search: AmenitySearch,
        llm_caller: StructuredLLMCaller,
    ) -> None:
        self._interpretation = interpretation
        self._amenity_search = amenity_search
        self._llm_caller = llm_caller

    async def interpret(self, raw_input: str) -> RequirementInterpretationState:
        """Run Responsibility 1 (requirement interpretation) on the raw customer text."""
        return await self._interpretation.interpret(raw_input)

    async def run(self, raw_input: str) -> RequirementInterpretationState:
        """Sequence the responsibilities in order: R1 first, then R2.

        R1 turns the raw text into the per-category specification. R2's metric-resolution
        stages run next, over the same injected caller's tool turn; that step and the R1 to R2
        data handoff are attached here as later sub-components build them, so this method does
        not yet invoke R2. It returns R1's state.
        """
        logger.info(
            json.dumps(
                {
                    "event": FEATURE_RUN_STARTED_EVENT,
                    "timestamp": _timestamp(),
                    "input_length": len(raw_input),
                }
            )
        )
        state = await self._interpretation.interpret(raw_input)
        logger.info(
            json.dumps(
                {
                    "event": FEATURE_INTERPRETATION_COMPLETED_EVENT,
                    "timestamp": _timestamp(),
                }
            )
        )
        return state

    async def aclose(self) -> None:
        """Close R1 and R2 owned resources, then the shared caller once."""
        await self._interpretation.aclose()
        await self._amenity_search.aclose()
        await self._llm_caller.aclose()


def create_deep_search(settings: Settings) -> DeepSearch:
    """Composition root: build the shared caller once, inject it into R1 and R2, then wire the feature.

    The factories run in dependency order: the shared caller first, then the two
    responsibilities with that caller injected (so neither owns it), then the feature that
    owns and closes it.
    """
    llm_caller = create_structured_llm_caller(settings)
    interpretation = create_requirement_interpretation(settings, llm_caller=llm_caller)
    amenity_search = create_amenity_search(settings, llm_caller=llm_caller)
    return DeepSearch(
        interpretation=interpretation,
        amenity_search=amenity_search,
        llm_caller=llm_caller,
    )
