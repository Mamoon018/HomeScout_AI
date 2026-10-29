"""R3.M1.3 (Website-URL Discovery) — behavior suite authored with the backend-test-writer skill.

This file is an independent, skill-driven suite for the R3.M1.3 mechanism described in
`feature_context/R3_Specific_Metric_Resolution_spec.md` (lines 436–514) and built per
`feature_context/R3_M1_3_Website_URL_Discovery_Implementation_Plan.md`. It is *not* a rewrite of
`test_r3_m1_3_website_url_discovery.py`; it exists to protect the same decisions from a fresh,
plan-first angle and to carry the six-field reasoning the skill requires (see each test's docstring:
Behavior / Core / Real-vs-mock / Evidence).

Guiding principle (skill): test the *decisions* the code makes, at an observable boundary, with real
dependencies for what can actually be wrong (our gate logic, our id-indirection, our retry/degrade
rules, the real `StructuredLLMCaller`) and fakes ONLY for what is non-deterministic, costly, or
outside the system (the MCP `web_search` gateway and the LLM provider edge). Every assertion is on an
observable outcome — a verdict, a resolved URL string, a reason code, a persisted store, an
I/O-call count — never on "a mock was called" except where the *absence* of a call IS the behavior
(no-retry / no-search-on-exhaustion), which the spec mandates.

No live network/LLM calls: the gate is pure; `tldextract` runs offline against its vendored PSL.
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
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    PredefinedMetricsRecord,
)
from src.services.deep_search.official_url_gate import compact, official_url_gate
from src.services.deep_search.specific_metric_resolution import (
    _CircuitBreaker,
    SpecificMetricResolution,
    _DiscoveryWorkItem,
    _index_candidates,
    _resolve_verdict,
)

# --------------------------------------------------------------------------------------------------
# Edge fakes — ONLY the system boundaries (MCP gateway + LLM provider). Everything the gate and the
# orchestrator decide is exercised for real.
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
    """Duck-types the LLM provider edge: pops a queued turn/body, or raises LLMProviderError.

    Faked because it is the non-deterministic, costly, out-of-system dependency. The real
    `StructuredLLMCaller` that orchestrates provider calls, strict decoding, and fallback is kept
    REAL and wraps this.
    """

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
    """Duck-types the MCP `ToolGateway` edge: serves raw defs + queued `search_web` outcomes.

    Faked because real `search_web` is billed, networked, and non-deterministic. Records every call
    so a test can assert the exact number of search attempts (the retry contract is observable).
    """

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


def _service(gateway, caller) -> SpecificMetricResolution:
    return SpecificMetricResolution(tool_gateway=gateway, llm_caller=caller, owns_caller=False)


def _discovery_turn() -> AssistantTurn:
    """A well-formed assistant turn that calls `web_search` with guard-valid arguments."""
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


def _rec(category_id, place_id, name, website,
         address="12 High St, Townsville 90210") -> PredefinedMetricsRecord:
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


async def _discover(service, rec):
    wi = _DiscoveryWorkItem(
        rec.category_id, rec.place_id, "dentist", "specific_attributes", [object()]
    )
    return await service._discover_website_url(
        wi, rec, RAW_DEFS, "batch", breaker=_CircuitBreaker(threshold=3)
    )


# ==================================================================================================
# Stage 0 — official_url_gate (pure, deterministic, highest stakes: a false `official` crawls the
# wrong host, expensive & uncorrectable). Real gate + real offline tldextract; nothing mocked.
# ==================================================================================================

def test_gate_trusts_brand_matching_sld_even_when_buried():
    """Behavior: brand ⟺ SLD-label match ⇒ `official`, independent of subdomain/suffix depth.
    Core: Stage 0 trusts Google's URL only when the registrable SLD label carries the brand.
    Real-vs-mock: real gate, real PSL — the thing under test; no fakes.
    Evidence: asserts the verdict AND the resolved SLD on a deeply-buried host, so it fails if the
    rule ever matched on the full host/subdomain instead of the SLD label.
    """
    flat = official_url_gate("https://www.greenvalleydental.co.uk", "Green Valley Dental")
    assert flat.verdict == "official" and flat.reason_code == "sld_match"

    buried = official_url_gate(
        "https://clinic.reseller.greenvalleydental.co.uk", "Green Valley Dental Clinic"
    )
    assert buried.verdict == "official"
    assert buried.reason_code == "sld_match"
    assert buried.sld == "greenvalleydental"


def test_gate_declines_foreign_sld_hosting_brand_as_subdomain():
    """Behavior: brand as a *subdomain* of a foreign SLD ⇒ `discovery` (the anti-leak guarantee).
    Core: the brand must be in the SLD label, not anywhere in the host.
    Real-vs-mock: real gate; no fakes.
    Evidence: `brand.evil.com` resolves SLD `evil`; asserting `discovery`+`sld_no_match`+sld==evil
    fails the moment a substring-over-whole-host rule would wrongly trust the attacker domain.
    """
    out = official_url_gate("https://greenvalleydental.evil.com", "Green Valley Dental")
    assert out.verdict == "discovery"
    assert out.reason_code == "sld_no_match"
    assert out.sld == "evil"


def test_gate_declines_absent_website():
    """Behavior: empty or whitespace-only website ⇒ `discovery`/`presence_empty` (absent input).
    Core: no candidate URL means nothing to trust; fall to search.
    Real-vs-mock: real gate.
    Evidence: both "" and "   " yield the presence reason code — fails if whitespace slipped past
    the presence check into host parsing.
    """
    for website in ("", "   "):
        out = official_url_gate(website, "Green Valley Dental")
        assert out.verdict == "discovery"
        assert out.reason_code == "presence_empty"


def test_gate_declines_host_without_registrable_domain():
    """Behavior: IP / localhost / bare host ⇒ `discovery`/`no_registrable_domain` (invalid input).
    Core: without an SLD+public-suffix there is no brandable label to match.
    Real-vs-mock: real gate + real PSL.
    Evidence: an IPv4 URL and a localhost:port URL both yield `no_registrable_domain` — fails if
    the netloc parse ever produced a spurious SLD for these.
    """
    assert official_url_gate("https://127.0.0.1/x", "Whatever").reason_code == "no_registrable_domain"
    assert official_url_gate("http://localhost:8000", "Whatever").reason_code == "no_registrable_domain"


def test_gate_denylist_is_exact_set_membership_not_substring():
    """Behavior: DENYLIST fast-rejects an *exact* registrable domain, never a substring lookalike.
    Core: `yelp.com` is a fast `denylist_hit`; `theyelpers.com` is NOT denylisted (it only shares a
    substring) and is decided by the ordinary SLD rule.
    Real-vs-mock: real gate.
    Evidence: the denylisted host reports `denylist_hit`+registered_domain `yelp.com`; the lookalike
    reports `sld_no_match` (not `denylist_hit`). A substring-based denylist would mislabel the second
    one, so this pins the "exact set membership" decision.
    """
    hit = official_url_gate("https://www.yelp.com/biz/green-valley", "Green Valley Dental")
    assert hit.verdict == "discovery"
    assert hit.reason_code == "denylist_hit"
    assert hit.registered_domain == "yelp.com"

    lookalike = official_url_gate("https://theyelpers.com", "Green Valley Dental")
    assert lookalike.verdict == "discovery"
    assert lookalike.reason_code == "sld_no_match"
    assert lookalike.registered_domain == "theyelpers.com"


def test_gate_min_len_guard_blocks_short_spurious_match():
    """Behavior: a sub-MIN_LEN SLD label cannot win on substring (boundary, false-positive guard).
    Core: `match` requires both operands ≥ 5 chars, so `nyu` (3) does not match "New York University".
    Real-vs-mock: real gate.
    Evidence: `nyu.edu` ⇒ `discovery`/`sld_no_match` — fails if MIN_LEN were dropped and the 3-char
    label produced a spurious `official`.
    """
    out = official_url_gate("https://nyu.edu", "New York University")
    assert out.verdict == "discovery"
    assert out.reason_code == "sld_no_match"


def test_gate_recognizes_brand_owned_platform_subdomain_as_official():
    """Behavior: `include_psl_private_domains` resolves a brand-owned builder subdomain to its SLD.
    Core: `brand.wixsite.com` ⇒ SLD `brand` ⇒ `official`, while foreign apex domains stay declined.
    Real-vs-mock: real gate + real PSL private-domain list.
    Evidence: asserts sld==`greenvalley` and `official`; fails if the private-domain flag regressed
    (then the SLD would be `wixsite` and the verdict `discovery`).
    """
    out = official_url_gate("https://greenvalley.wixsite.com/site", "Greenvalley")
    assert out.sld == "greenvalley"
    assert out.verdict == "official"
    assert out.reason_code == "sld_match"


def test_compact_folds_accents_so_accented_brand_matches_ascii_domain():
    """Behavior: `compact` NFKD-folds accents (not deletes), so an accented brand matches its domain.
    Core: "Café México" → "cafemexico", which then substring-matches an ASCII SLD.
    Real-vs-mock: real `compact` + real gate.
    Evidence: the transform equals the ASCII form AND the end-to-end gate returns `official` on
    cafemexico.com — fails if NFKC/deletion dropped the accented letters entirely.
    """
    assert compact("Café México") == "cafemexico"
    out = official_url_gate("https://cafemexico.com", "Café México")
    assert out.verdict == "official"
    assert out.reason_code == "sld_match"


# ==================================================================================================
# Stage 1 — pure helpers (anti-hallucination id-indirection). Real helpers; no fakes.
# ==================================================================================================

def test_index_candidates_drops_urlless_hits_and_builds_contiguous_ids():
    """Behavior: non-selectable hits (`url is None`) are dropped and ids re-number c1..cN densely.
    Core: the LLM may only pick from hits that have a real URL; the id→url map must stay authoritative.
    Real-vs-mock: real `_index_candidates`.
    Evidence: a 3-hit result with a `None` in the middle yields ids [c1,c2] mapped to the two real
    URLs — fails if a url-less hit kept an id (which would let the LLM select an unresolvable id).
    """
    candidates, id_url_map = _index_candidates(_search_with(["https://a.com", None, "https://c.com"]))
    assert [c.id for c in candidates] == ["c1", "c2"]
    assert [c.url for c in candidates] == ["https://a.com", "https://c.com"]
    assert id_url_map == {"c1": "https://a.com", "c2": "https://c.com"}


def test_resolve_verdict_maps_id_to_verbatim_url_or_none():
    """Behavior: verdict resolution is pure id→url lookup; `None` ⇒ `none` (LLM never emits a URL).
    Core: a selected id resolves to the exact search-result URL with origin `discovered`; the null
    sentinel resolves to origin `none` with no URL.
    Real-vs-mock: real `_resolve_verdict`.
    Evidence: asserts the verbatim URL string and both origins — fails if resolution fabricated or
    rewrote the URL, or mislabelled the origin.
    """
    discovered = _resolve_verdict("c1", {"c1": "https://a.com", "c2": "https://b.com"})
    assert discovered.website_url == "https://a.com"
    assert discovered.website_origin == "discovered"

    none = _resolve_verdict(None, {"c1": "https://a.com"})
    assert none.website_url is None
    assert none.website_origin == "none"


# ==================================================================================================
# Stage 1 — the per-item discovery coroutine. Real caller + real orchestration; only the gateway and
# the provider edge are faked.
# ==================================================================================================

async def test_discovery_resolves_selected_candidate_to_discovered_url():
    """Behavior (happy path): a valid `selected_id` ⇒ `discovered` with the candidate's verbatim URL.
    Core: Stage 1 search → index → select → resolve produces the official URL and its telemetry.
    Real-vs-mock: real caller/coroutine; fake gateway returns 2 hits, fake provider picks c1.
    Evidence: asserts the resolved URL equals the first hit AND telemetry records selected_id/url —
    fails if indexing, selection wiring, or resolution dropped or swapped the pick.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com", "https://x.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "discovered"
    assert verdict.website_url == "https://gv.com"
    assert telemetry is not None
    assert telemetry.selected_id == "c1" and telemetry.resolved_url == "https://gv.com"


async def test_discovery_null_sentinel_is_terminal_without_retry():
    """Behavior: a confident `none` sentinel is terminal — the selection turn is NOT retried.
    Core: spec "Failure vs empty" — a chosen `none` ends discovery; only *invalid* verdicts retry.
    Real-vs-mock: real coroutine; the retry/no-retry decision is the behavior, so asserting the
    second queued body is left UNCONSUMED is a legitimate interaction assertion.
    Evidence: verdict is `none` and the provider still holds its second body — fails if the code
    retried a confident `none`.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com"])])
    provider = FakeProvider(turns=[_discovery_turn()], bodies=[{"selected_id": None}, {"selected_id": "c1"}])
    verdict, _ = await _discover(
        _service(gateway, StructuredLLMCaller([provider])), _rec(1, "p", "Green Valley", "https://x")
    )
    assert verdict.website_origin == "none"
    assert provider._bodies == [{"selected_id": "c1"}]


async def test_discovery_retries_once_on_invalid_id_then_resolves():
    """Behavior: an id outside the issued set is an invalid verdict ⇒ exactly one selection retry.
    Core: id-indirection rejects a hallucinated/out-of-set id, re-asks once with the same candidates.
    Real-vs-mock: real coroutine; fake provider returns bad `c9` then valid `c1`.
    Evidence: final verdict is `discovered` at the first hit's URL — fails if the invalid id were
    accepted (unresolvable) or if no retry happened.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c9"}, {"selected_id": "c1"}])
    verdict, _ = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "discovered"
    assert verdict.website_url == "https://gv.com"


async def test_discovery_degrades_to_none_after_two_invalid_ids():
    """Behavior: invalid id on both the attempt and its one retry ⇒ terminal `none` (give-up bound).
    Core: the selection retry is capped at one; a second invalid verdict degrades, never loops.
    Real-vs-mock: real coroutine; fake provider returns `c9` then `c8` (both out of set).
    Evidence: verdict is `none` — fails if the retry budget were >1 (then the second bad id would
    not yet terminate) or if a bad id leaked through.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://gv.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c9"}, {"selected_id": "c8"}])
    verdict, _ = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"


async def test_discovery_retries_search_once_on_tool_failure_then_none():
    """Behavior: a `search_web` `ToolFailure` triggers exactly one re-issue, then degrades to `none`.
    Core: spec "Failure vs empty" — tool failure (not empty) gets one R3.M1.3-level retry.
    Real-vs-mock: real coroutine; fake gateway returns two ToolFailures and records both calls.
    Evidence: verdict `none`, telemetry `None`, and exactly 2 gateway search calls — the call count
    is the observable proof of "one call + one retry" (fails at 1 or 3 calls).
    """
    gateway = FakeGateway(
        search_outcomes=[ToolFailure("web_search", "timeout", "x"), ToolFailure("web_search", "timeout", "x")]
    )
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"
    assert telemetry is None
    assert len(gateway.search_calls) == 2


async def test_discovery_degrades_to_none_on_provider_exhaustion_without_searching():
    """Behavior: provider exhaustion on the tool turn ⇒ `none` and the gateway is never reached (D5).
    Core: a failure before a usable search must degrade to `none`, not raise out of the task, and
    must not spend a billed search.
    Real-vs-mock: real coroutine; empty provider ⇒ real caller raises MetricResolutionProviderError.
    Evidence: verdict `none`, telemetry `None`, and zero gateway search calls — the empty
    `search_calls` list proves no search was attempted (fails if the exception escaped or a search ran).
    """
    gateway = FakeGateway(search_outcomes=[])
    caller = _caller(turns=[], bodies=[])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"
    assert telemetry is None
    assert gateway.search_calls == []


async def test_discovery_with_no_selectable_candidates_yields_none_with_telemetry():
    """Behavior: a search whose hits all have `url is None` ⇒ genuine `none` with recorded telemetry.
    Core: no candidate to pick is not a failure drift — the selection turn is skipped and telemetry
    still captures the (empty) candidate set for offline eval.
    Real-vs-mock: real coroutine; fake gateway returns two url-less excerpts; provider has NO body
    queued, proving the selection turn is never invoked.
    Evidence: verdict `none` with telemetry present and `candidates == ()` — fails if a selection
    turn were attempted (the empty provider would raise) or if telemetry were omitted.
    """
    gateway = FakeGateway(search_outcomes=[_search_with([None, None])])
    caller = _caller(turns=[_discovery_turn()], bodies=[])
    verdict, telemetry = await _discover(_service(gateway, caller), _rec(1, "p", "Green Valley", "https://x"))
    assert verdict.website_origin == "none"
    assert telemetry is not None
    assert telemetry.candidates == ()


# ==================================================================================================
# STEP 3 orchestration — run_specific_metric_resolution end-to-end (real service). RC7 / RC8 / D5.
# ==================================================================================================

def _state_for_batch() -> AmenitySearchState:
    """Handoff state as after M1: one eligible category (pA google-pass, pB declined, pD missing
    record) and one ineligible basic_profile category (pC)."""
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


async def test_batch_produces_a_verdict_for_every_eligible_work_item_rc8():
    """Behavior (RC8 "URL-first for everyone"): after the barrier every eligible work item has a
    verdict, with the gate-official item taking the zero-cost path (no search) and the declined item
    resolved by search.
    Core: the pre-pass writes `google` immediately; the fan-out resolves the declined subset; the
    gateway lifecycle brackets the run; STEP 4+ is unbuilt so `amenity_records` stays None.
    Real-vs-mock: real service/gate/caller; fake gateway (1 hit) + fake provider (picks c1).
    Evidence: the verdict keys equal exactly {pA,pB,pD}; pA is `google`, pB is `discovered` at the
    found URL, pD is `none`; exactly ONE search ran (pA skipped it); gateway opened+closed;
    amenity_records is None — fails if any item lacked a verdict or the google item spent a search.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://found.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    out = await _service(gateway, caller).run_specific_metric_resolution(_state_for_batch())

    assert gateway.opened and gateway.closed
    assert out.amenity_records is None

    wsr = out.website_search_results
    assert set(wsr) == {(1, "pA"), (1, "pB"), (1, "pD")}
    assert wsr[(1, "pA")].website_origin == "google"
    assert wsr[(1, "pA")].website_url == "https://greenvalleydental.com"
    assert wsr[(1, "pB")].website_origin == "discovered"
    assert wsr[(1, "pB")].website_url == "https://found.com"
    assert wsr[(1, "pD")].website_origin == "none"
    assert len(gateway.search_calls) == 1  # only the declined item searched


async def test_batch_excludes_basic_profile_category_rc7():
    """Behavior (RC7 eligibility): a category with no `specific_metrics` produces no work item.
    Core: `_derive_work_items` filters out basic_profile categories, so their places never get a
    discovery verdict or gate record.
    Real-vs-mock: real service; fake edges.
    Evidence: the basic_profile place (2,"pC") is absent from both the verdict store and the gate
    store — fails if ineligible categories leaked into the batch.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://found.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    out = await _service(gateway, caller).run_specific_metric_resolution(_state_for_batch())
    assert (2, "pC") not in out.website_search_results
    assert (2, "pC") not in out.official_gate_results


async def test_batch_records_missing_record_as_none_without_crashing():
    """Behavior: a work item with no `PredefinedMetricsRecord` ⇒ `none`/`missing_record`, no search.
    Core: a precondition gap (no identity) is rejected to `none` and audited, not crashed or
    silently dropped, and must not consume a search.
    Real-vs-mock: real service; pD has no record.
    Evidence: verdict for (1,"pD") is `none`, its gate record reason is `missing_record`, and the
    only search spent is the declined item's — fails if a missing record raised or triggered a search.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://found.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    out = await _service(gateway, caller).run_specific_metric_resolution(_state_for_batch())
    assert out.website_search_results[(1, "pD")].website_origin == "none"
    assert out.official_gate_results[(1, "pD")].reason_code == "missing_record"
    assert len(gateway.search_calls) == 1


async def test_batch_gate_telemetry_covers_all_items_search_telemetry_only_declined():
    """Behavior: Stage-0 telemetry is written for EVERY work item; Stage-1 telemetry only for the
    declined subset that actually searched.
    Core: `official_gate_results` is all-items audit; `discovery_search_results` is the searched
    subset — the two stores have different coverage by design.
    Real-vs-mock: real service; fake edges.
    Evidence: gate-record keys == {pA,pB,pD} with reason codes sld_match / denylist_hit /
    missing_record; discovery-record keys == {pB} only — fails if coverage of either store drifted.
    """
    gateway = FakeGateway(search_outcomes=[_search_with(["https://found.com"])])
    caller = _caller(turns=[_discovery_turn()], bodies=[{"selected_id": "c1"}])
    out = await _service(gateway, caller).run_specific_metric_resolution(_state_for_batch())

    assert set(out.official_gate_results) == {(1, "pA"), (1, "pB"), (1, "pD")}
    assert out.official_gate_results[(1, "pA")].reason_code == "sld_match"
    assert out.official_gate_results[(1, "pB")].reason_code == "denylist_hit"
    assert out.official_gate_results[(1, "pD")].reason_code == "missing_record"
    assert set(out.discovery_search_results) == {(1, "pB")}
