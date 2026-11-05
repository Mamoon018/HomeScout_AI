"""Offline fixtures for R3.M1.3 — website-URL discovery (Stage 0 gate + Stage 1 search/selection).

No live calls. The deterministic gate is tested directly; the Stage-1 code paths and the STEP-3
batch orchestration run against a fake `ToolGateway` and a real `StructuredLLMCaller` wrapping a
hand-written fake provider. These prove the rules the live sample runner cannot prove
deterministically (gate verdicts, id-indirection, the two retries, degrade-to-`none`, RC7/RC8).
"""

import json

from src.clients.llm_provider import AssistantTurn, StructuredLLMCaller, ToolCall
from src.clients.mcp_tools import (
    RawToolDefinition,
    SearchExcerpt,
    ToolFailure,
    WebSearchResult,
)
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.official_url_gate import compact, official_url_gate
from src.services.deep_search.specific_metric_resolution import (
    SpecificMetricResolution,
    _index_candidates,
    _resolve_verdict,
)
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    PredefinedMetricsRecord,
)

# --------------------------------------------------------------------------------------------------
# Fakes and builders.
# --------------------------------------------------------------------------------------------------

_WEB_SEARCH_DEF = RawToolDefinition(
    name="web_search",
    description="Search the web.",
    input_schema={
        "type": "object",
        "properties": {
            "objective": {"type": "string"},
            "search_queries": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["objective", "search_queries"],
    },
)
RAW_DEFS = {"parallel": {"web_search": _WEB_SEARCH_DEF}}


class FakeProvider:
    """Duck-types StructuredLLMProvider; pops queued turns/bodies or raises LLMProviderError."""

    def __init__(self, name="openai", *, turns=None, bodies=None) -> None:
        self.name = name
        self.model = f"{name}-model"
        self._turns = list(turns or [])
        self._bodies = list(bodies or [])
        self.close_count = 0

    async def generate_turn(self, *, messages, tools, tool_choice):
        if not self._turns:
            raise LLMProviderError(f"{self.name}: no recorded turn left")
        item = self._turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def generate_structured(self, *, instruction, user_content, json_schema, schema_name):
        if not self._bodies:
            raise LLMProviderError(f"{self.name}: no recorded body left")
        item = self._bodies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self) -> None:
        self.close_count += 1


class FakeGateway:
    """Duck-types ToolGateway for discovery; serves raw defs + queued search outcomes."""

    def __init__(self, *, search_outcomes=None, search_raises=None) -> None:
        self._outcomes = list(search_outcomes or [])
        self._search_raises = search_raises
        self.opened = False
        self.closed = False
        self.search_calls: list[tuple] = []

    async def open(self) -> None:
        self.opened = True

    def get_tool_definitions(self):
        return RAW_DEFS

    async def search_web(self, objective, search_queries):
        self.search_calls.append((objective, tuple(search_queries)))
        if self._search_raises is not None:
            raise self._search_raises
        return self._outcomes.pop(0)

    async def map_site(self, url):  # pragma: no cover - unused in R3.M1.3
        raise NotImplementedError

    async def scrape_page(self, url):  # pragma: no cover - unused in R3.M1.3
        raise NotImplementedError

    async def scrape_pages(self, urls, *, formats=("markdown",)):  # pragma: no cover
        raise NotImplementedError

    async def crawl_site(self, url, limit, depth):  # pragma: no cover - unused in R3.M1.3
        raise NotImplementedError

    async def aclose(self) -> None:
        self.closed = True


def _caller(*, turns=None, bodies=None) -> StructuredLLMCaller:
    return StructuredLLMCaller([FakeProvider(turns=turns, bodies=bodies)])


def _discovery_turn() -> AssistantTurn:
    """A well-formed assistant turn that calls web_search with valid arguments."""
    call = ToolCall(
        id="t1",
        name="web_search",
        arguments=json.dumps(
            {"objective": "official website", "search_queries": ["green valley dental 90210"]}
        ),
    )
    return AssistantTurn(
        provider="openai",
        finish_reason="tool_calls",
        content=None,
        tool_calls=(call,),
        message={"role": "assistant", "content": None},
    )


def _search_with(urls) -> WebSearchResult:
    excerpts = tuple(
        SearchExcerpt(url=u, title=f"title {i}", text=f"snippet {i}") for i, u in enumerate(urls)
    )
    return WebSearchResult("official website", ("green valley dental 90210",), excerpts, "now")


def _rec(category_id, place_id, name, website, address="12 High St, Townsville 90210") -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=category_id,
        taxonomy_node="dentist",
        depth="specific_attributes",
        place_id=place_id,
        name=name,
        category=None,
        address=address,
        website=website,
        google_maps_uri=None,
        coordinates=None,
        opening_hours=None,
        contact_phone=None,
        rating=None,
        review_volume=None,
        price_level=None,
        reviews=None,
        routing={},
        transit=None,
    )


def _service(gateway, caller) -> SpecificMetricResolution:
    return SpecificMetricResolution(tool_gateway=gateway, llm_caller=caller, owns_caller=False)


# --------------------------------------------------------------------------------------------------
# Stage 0 — the official-URL gate (pure, deterministic).
# --------------------------------------------------------------------------------------------------
def test_gate_official_on_sld_match_including_buried_site():
    assert official_url_gate("https://www.greenvalleydental.co.uk", "Green Valley Dental").verdict == "official"
    buried = official_url_gate(
        "https://clinic.reseller.greenvalleydental.co.uk", "Green Valley Dental Clinic"
    )
    assert buried.verdict == "official"
    assert buried.reason_code == "sld_match"
    assert buried.sld == "greenvalleydental"


def test_gate_discovery_on_foreign_sld():
    out = official_url_gate("https://brand.evil.com", "Green Valley Dental")
    assert out.verdict == "discovery"
    assert out.reason_code == "sld_no_match"
    assert out.sld == "evil"


def test_gate_discovery_on_empty_website():
    out = official_url_gate("", "Green Valley Dental")
    assert out.verdict == "discovery"
    assert out.reason_code == "presence_empty"


def test_gate_discovery_on_ip_and_localhost():
    assert official_url_gate("https://127.0.0.1/x", "Whatever").reason_code == "no_registrable_domain"
    assert official_url_gate("http://localhost:8000", "Whatever").reason_code == "no_registrable_domain"


def test_gate_denylist_is_fast_reject():
    out = official_url_gate("https://www.yelp.com/biz/green-valley", "Green Valley Dental")
    assert out.verdict == "discovery"
    assert out.reason_code == "denylist_hit"
    assert out.registered_domain == "yelp.com"


def test_gate_private_domain_resolves_to_brand_sld():
    out = official_url_gate("https://greenvalley.wixsite.com/site", "Greenvalley")
    assert out.sld == "greenvalley"
    assert out.verdict == "official"


def test_gate_min_len_blocks_short_acronym():
    # nyu (3 chars) is below MIN_LEN and is not a substring of the compacted brand → discovery.
    out = official_url_gate("https://nyu.edu", "New York University")
    assert out.verdict == "discovery"
    assert out.reason_code == "sld_no_match"


def test_compact_folds_accents():
    assert compact("Café México") == "cafemexico"


# --------------------------------------------------------------------------------------------------
# Stage 1 — candidate indexing (pure).
# --------------------------------------------------------------------------------------------------
def test_index_candidates_drops_url_none_and_reindexes():
    result = _search_with(["https://a.com", None, "https://c.com"])
    candidates, id_url_map = _index_candidates(result)
    assert [c.id for c in candidates] == ["c1", "c2"]
    assert id_url_map == {"c1": "https://a.com", "c2": "https://c.com"}


def test_resolve_verdict():
    assert _resolve_verdict("c2", {"c1": "a", "c2": "b"}) == _resolve_verdict("c2", {"c2": "b"})
    discovered = _resolve_verdict("c1", {"c1": "https://a.com"})
    assert discovered.website_url == "https://a.com" and discovered.website_origin == "discovered"
    none = _resolve_verdict(None, {"c1": "https://a.com"})
    assert none.website_url is None and none.website_origin == "none"


# --------------------------------------------------------------------------------------------------
# Stage 1 — the per-item discovery coroutine.
# --------------------------------------------------------------------------------------------------
async def _discover(service, rec):
    from src.services.deep_search.specific_metric_resolution import _DiscoveryWorkItem

    wi = _DiscoveryWorkItem(rec.category_id, rec.place_id, "dentist", "specific_attributes", [object()])
    return await service._discover_website_url(wi, rec, RAW_DEFS, "batch")


async def test_discovery_selected_id_resolves_discovered():
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com", "https://x.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_url == "https://gv.com"
    assert verdict.website_origin == "discovered"
    assert telemetry is not None and telemetry.selected_id == "c1"
    assert telemetry.resolved_url == "https://gv.com"


async def test_discovery_null_sentinel_is_terminal_none_no_retry():
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com"])])
    provider = FakeProvider(turns=[_discovery_turn()], bodies=[{"selected_id": None}, {"selected_id": "c1"}])
    verdict, telemetry = await _discover(
        _service(gateway, StructuredLLMCaller([provider])), _rec(1, "p", "Green Valley", "https://x")
    )
    assert verdict.website_origin == "none"
    # The second body must remain unconsumed: a null sentinel is terminal, not retried.
    assert provider._bodies == [{"selected_id": "c1"}]


async def test_discovery_invalid_id_retries_then_resolves():
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c9"}, {"selected_id": "c1"}])
    verdict, _ = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "discovered"
    assert verdict.website_url == "https://gv.com"


async def test_discovery_invalid_id_twice_degrades_to_none():
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c9"}, {"selected_id": "c8"}])
    verdict, _ = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"


async def test_discovery_search_failure_retries_then_none():
    gateway = FakeGateway(
        search_outcomes=[ToolFailure("web_search", "timeout", "x"), ToolFailure("web_search", "timeout", "x")]
    )
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"
    assert telemetry is None
    assert len(gateway.search_calls) == 2  # one call + one retry


async def test_discovery_search_failure_then_success():
    gateway = FakeGateway(
        search_outcomes=[ToolFailure("web_search", "timeout", "x"), _search_with(["https://gv.com"])]
    )
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    verdict, _ = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "discovered"


async def test_discovery_provider_exhaustion_on_turn_is_none():
    gateway = FakeGateway(search_outcomes=[])
    caller = _caller(turns=[], bodies=[])  # call_turn exhausts → MetricResolutionProviderError
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"
    assert telemetry is None
    assert gateway.search_calls == []  # never reached the gateway


async def test_discovery_empty_search_yields_none_with_telemetry():
    gateway = FakeGateway(search_outcomes=[_search_with([None, None])])  # all url=None → no candidates
    caller = _caller(turns=[_discovery_turn()], bodies=[])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"
    assert telemetry is not None and telemetry.candidates == ()


# --------------------------------------------------------------------------------------------------
# STEP 3 orchestration (pre-pass + fan-out), RC7 / RC8.
# --------------------------------------------------------------------------------------------------
def _state_for_batch() -> AmenitySearchState:
    eligible = CategoryMetricPlan(1, "dentist", "specific_attributes", [], [object()])
    basic = CategoryMetricPlan(2, "park", "basic_profile", [], [])  # RC7: no work item
    cp = CanonicalPlace("x", {})
    return AmenitySearchState(
        origin=GeoPoint(0.0, 0.0),
        radius_km=2.0,
        category_metric_plans=[eligible, basic],
        discovered_places={1: {"pA": cp, "pB": cp, "pD": cp}, 2: {"pC": cp}},
        predefined_records={
            1: {
                "pA": _rec(1, "pA", "Green Valley Dental", "https://greenvalleydental.com"),
                "pB": _rec(1, "pB", "Green Valley Dental", "https://www.yelp.com/biz/gv"),
                # "pD" deliberately absent → missing_record path.
            }
        },
    )


async def test_run_discovery_batch_orchestration():
    gateway = FakeGateway(search_outcomes=[_search_with(["https://found.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    service = _service(gateway, caller)
    state = _state_for_batch()
    out = await service.run_specific_metric_resolution(state)

    assert gateway.opened and gateway.closed
    assert out.amenity_records is None  # STEP 4-6 not built

    wsr = out.website_search_results
    # RC8: every work item (pA, pB, pD) has a verdict; the ineligible category's place has none.
    assert set(wsr) == {(1, "pA"), (1, "pB"), (1, "pD")}
    assert wsr[(1, "pA")].website_origin == "google"
    assert wsr[(1, "pB")].website_origin == "discovered"
    assert wsr[(1, "pB")].website_url == "https://found.com"
    assert wsr[(1, "pD")].website_origin == "none"
    assert (2, "pC") not in wsr  # RC7: basic_profile category produced no work item

    # Stage-0 telemetry covers ALL work items; Stage-1 telemetry only the searched (declined) one.
    assert set(out.official_gate_results) == {(1, "pA"), (1, "pB"), (1, "pD")}
    assert out.official_gate_results[(1, "pA")].reason_code == "sld_match"
    assert out.official_gate_results[(1, "pB")].reason_code == "denylist_hit"
    assert out.official_gate_results[(1, "pD")].reason_code == "missing_record"
    assert set(out.discovery_search_results) == {(1, "pB")}

    # The gate-official item never searched (zero-cost path); only the declined one did.
    assert len(gateway.search_calls) == 1
