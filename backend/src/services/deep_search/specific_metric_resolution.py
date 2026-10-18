import logging

from src.clients.llm_provider import (
    StructuredLLMCaller,
    create_structured_llm_caller,
)
from src.clients.mcp_tools import (
    ToolGateway,
    create_mcp_tool_gateway,
)
from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.services.deep_search.feature_schemas.schemas import AmenitySearchState

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)


class SpecificMetricResolution:
    """Responsibility 3: resolve each LLM-defined `specific_metric` to a committed factual value.

    Promoted from "R2 Mechanism 3". R3 owns the MCP tool gateway (its session lifecycle lives
    inside `run_specific_metric_resolution`) and uses the shared `StructuredLLMCaller` for its
    tool turns. The two mechanisms (R3.M1 Evidence Acquisition, R3.M2 Resolution) and their stage
    methods are specified in `feature_context/R3_Specific_Metric_Resolution_spec.md` and land
    sub-component by sub-component; this class is the promotion skeleton.

    The gateway and caller follow the same ownership contract `AmenitySearch` used while it held
    them: the gateway is injected and never opened at construction, and the shared caller is owned
    by the `DeepSearch` feature (so `owns_caller` is False) — standalone construction owns its own.
    """

    def __init__(
        self,
        *,
        tool_gateway: ToolGateway,
        llm_caller: StructuredLLMCaller | None = None,
        owns_caller: bool = True,
    ) -> None:
        # Injected here (R3.M1 / C3.1.1). It is the locked test seam, so the service never sees MCP
        # types. No session is opened at construction; `run_specific_metric_resolution` will
        # `open()` it first and `aclose()` it last once its workflow lands.
        self._tool_gateway = tool_gateway
        # Shared caller for the R3.M1 tool turn and R3.M2 structured turns (C3.1.2). When the
        # DeepSearch feature injects a shared caller, `owns_caller` is False and the feature closes
        # it; standalone construction owns and closes its own.
        self._llm_caller = llm_caller
        self._owns_caller = owns_caller
        # Concurrency bounds (per-server gateway semaphores, the LLM-call bound, the amenity-
        # pipeline cap, and the per-amenity scrape ceiling) are added with the R3.M1.5 workflow,
        # whose finalized values they must match; the skeleton builds none of them yet.

    async def run_specific_metric_resolution(
        self, state: AmenitySearchState
    ) -> AmenitySearchState:
        """R3 entry point (promotion skeleton — not yet implemented).

        When built, this opens the gateway sessions, runs the R3.M1 discovery batch and amenity
        pipelines, then the R3.M2 resolution and the R3.M2.5 combine into `state.amenity_records`,
        and closes the sessions. The entry signature is fixed now so `DeepSearch` can wire it.
        """
        raise NotImplementedError(
            "R3 workflow not yet implemented; see "
            "feature_context/R3_Specific_Metric_Resolution_spec.md"
        )

    async def aclose(self) -> None:
        """Close the MCP gateway, and the shared caller only when this instance owns it."""
        # The gateway closes any leaked session even if `run_specific_metric_resolution` already
        # did. It is None only in contexts that never build or open it.
        if self._tool_gateway is not None:
            await self._tool_gateway.aclose()
        # Close the shared caller only when this instance owns it; the DeepSearch feature closes an
        # injected caller itself. It is None when no LLM work is wired.
        if self._owns_caller and self._llm_caller is not None:
            await self._llm_caller.aclose()


def create_specific_metric_resolution(
    settings: Settings,
    *,
    llm_caller: StructuredLLMCaller | None = None,
) -> SpecificMetricResolution:
    """Composition root for R3: build the MCP gateway and resolve caller ownership.

    The gateway opens no session here (no I/O at construction); `run_specific_metric_resolution`
    opens and closes it. Standalone (no `llm_caller`) builds its own caller and owns it; the
    DeepSearch feature injects a shared caller it closes itself.
    """
    if llm_caller is None:
        caller = create_structured_llm_caller(settings)
        owns_caller = True
    else:
        caller = llm_caller
        owns_caller = False
    return SpecificMetricResolution(
        tool_gateway=create_mcp_tool_gateway(settings),
        llm_caller=caller,
        owns_caller=owns_caller,
    )
