"""Coordinator-level tests for the DeepSearch feature after the R3 promotion.

These cover the wiring the promotion introduced: `create_deep_search` builds R1, R2, and the new
R3 (`SpecificMetricResolution`) against one shared caller, and `aclose()` closes all three plus the
caller exactly once (D6 single-owner).
"""

from src.core.config import Settings
from src.services.deep_search.amenity_search import AmenitySearch
from src.services.deep_search.deep_search import DeepSearch, create_deep_search
from src.services.deep_search.requirement_interpretation import (
    UserRequirementsInterpretation,
)
from src.services.deep_search.specific_metric_resolution import SpecificMetricResolution


def _settings() -> Settings:
    """A fully-populated Settings built without env/validation, so no I/O or real keys are needed.

    `model_construct` sets every field the composition-root factories read at construction time;
    none of those factories open a session or hit the network.
    """
    return Settings.model_construct(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test_key",
        supabase_jwt_audience="authenticated",
        google_maps_api="test-google-maps-api-key",
        captcha_enabled=True,
        log_level="INFO",
        openai_api_key="sk-test",
        openai_extraction_model="gpt-4o-2024-08-06",
        groq_api_key="gk-test",
        groq_extraction_model="openai/gpt-oss-120b",
        llm_provider_order="openai,groq",
        parallel_api_key=None,
        firecrawl_api_key=None,
        parallel_mcp_url="https://search.parallel.ai/mcp",
        firecrawl_mcp_url="https://mcp.firecrawl.dev/v2/mcp",
        firecrawl_probe_url="https://example.com",
    )


async def test_create_deep_search_wires_r1_r2_r3_on_one_shared_caller() -> None:
    deep_search = create_deep_search(_settings())
    try:
        assert isinstance(deep_search._interpretation, UserRequirementsInterpretation)
        assert isinstance(deep_search._amenity_search, AmenitySearch)
        assert isinstance(deep_search._specific_metric_resolution, SpecificMetricResolution)
        # R2 and R3 receive the shared caller and do NOT own it (D6: the feature is sole owner).
        assert deep_search._amenity_search._owns_caller is False
        assert deep_search._specific_metric_resolution._owns_caller is False
        assert deep_search._specific_metric_resolution._llm_caller is deep_search._llm_caller
        # R3 owns a gateway it has not opened.
        assert deep_search._specific_metric_resolution._tool_gateway is not None
    finally:
        # A never-opened gateway and never-used clients close cleanly.
        await deep_search.aclose()


async def test_aclose_closes_all_three_and_the_caller_once() -> None:
    class _Closer:
        def __init__(self) -> None:
            self.closed = 0

        async def aclose(self) -> None:
            self.closed += 1

    interpretation = _Closer()
    amenity_search = _Closer()
    specific = _Closer()
    caller = _Closer()

    deep_search = DeepSearch(
        interpretation=interpretation,
        amenity_search=amenity_search,
        specific_metric_resolution=specific,
        llm_caller=caller,
    )
    await deep_search.aclose()

    assert interpretation.closed == 1
    assert amenity_search.closed == 1
    assert specific.closed == 1
    # The shared caller is closed exactly once, by the feature — not by any responsibility.
    assert caller.closed == 1
