"""R3.M1.4 step 1 (Phase-1 Loop) — behavior suite authored with the backend-test-writer skill.

Plan: `feature_tests/R3_M1_4_Phase1_Loop_test_plan.md` (one six-field entry per test below). The
suite complements `test_r3_m1_4_phase1_loop.py` and protects the decisions with the highest stakes:
the per-metric billed-search ceiling, the two-turn limit, a replayable shared conversation, evidence
text that is exactly what the LLM saw, per-amenity failure isolation, and exact breaker counting.

Real vs mock (skill rule: fake only what is non-deterministic, costly, or outside the system):
- FAKED: the LLM provider edge (`RoutingProvider`: answers per amenity from its own queue, so
  concurrent pipelines get deterministic turns) and the MCP gateway's `search_web` (`FakeGateway`:
  outcomes keyed by objective; every invocation is recorded because each one is a billed search).
- REAL: `StructuredLLMCaller` (fallback + `cause` aggregation), the R3.M1.1 catalog / guard /
  steps 3-5, budget admission, R3.M1.2 shaping, `MetricsSourceContent`, the circuit breaker, the
  pipeline catch, the STEP 5 sweep, the official-URL gate, and the phase-1 prompt builder.

Excerpt fixtures reuse the shapes of the real run in `sample_outputs.py`: multi-line markdown text,
`...` gaps, unicode, and two URLs that differ only by a trailing `%20`.
"""

import json

import pytest

import src.services.deep_search.specific_metric_resolution as smr
from src.clients.llm_provider import AssistantTurn, StructuredLLMCaller, ToolCall
from src.clients.mcp_tools import RawToolDefinition, SearchExcerpt, ToolFailure, WebSearchResult
from src.exceptions.deep_search import MetricResolutionProviderError
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    MetricResolutionSource,
    MetricSpec,
    PredefinedMetricsRecord,
    WebsiteSearchResult,
)
from src.services.deep_search.phase_tool_catalog import build_tool_catalog
from src.services.deep_search.specific_metric_resolution import (
    SpecificMetricResolution,
    _CircuitBreaker,
    _DiscoveryWorkItem,
)

# ==================================================================================================
# Edge fakes (the only stand-ins).
# ==================================================================================================
RAW_DEFS = {
    "parallel": {
        "web_search": RawToolDefinition(
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
    }
}
CATALOG = build_tool_catalog(RAW_DEFS, "metric_web_search")
RETRIEVED_AT = "2026-10-29T16:09:08.616967+00:00"


class RoutingProvider:
    """LLM provider edge: answers each amenity from its own queue (keyed by the amenity name the
    phase-1 instruction carries), and records a JSON snapshot of every history it was sent."""

    name = "openai"
    model = "fake-model"

    def __init__(self, queues: dict[str, list]) -> None:
        self._queues = {name: list(items) for name, items in queues.items()}
        self.sent: dict[str, list[list[dict]]] = {name: [] for name in queues}

    def _amenity(self, messages: list[dict]) -> str:
        system = messages[0]["content"]
        for name in self._queues:
            if f'"amenity_name": "{name}"' in system:
                return name
        raise AssertionError("no queue for this amenity")

    async def generate_turn(self, *, messages, tools, tool_choice):
        name = self._amenity(messages)
        self.sent[name].append(json.loads(json.dumps(messages)))
        if not self._queues[name]:
            raise LLMProviderError("no recorded turn left", failure_class="content")
        item = self._queues[name].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def generate_structured(self, **_kwargs):  # pragma: no cover - discovery never runs here
        raise LLMProviderError("unexpected structured call", failure_class="content")

    async def aclose(self) -> None:
        pass

    def total_calls(self) -> int:
        return sum(len(v) for v in self.sent.values())


class FakeGateway:
    """MCP edge: `search_web` outcomes keyed by objective; every invocation is recorded."""

    def __init__(self, outcomes: dict[str, list] | None = None) -> None:
        self._outcomes = {k: list(v) for k, v in (outcomes or {}).items()}
        self.search_calls: list[str] = []
        self.closed = False

    async def open(self) -> None:
        pass

    def get_tool_definitions(self):
        return RAW_DEFS

    async def search_web(self, objective, search_queries):
        self.search_calls.append(objective)
        queue = self._outcomes.get(objective)
        if not queue:
            return ToolFailure("web_search", "tool_error", "no fixture for this objective")
        return queue.pop(0)

    async def aclose(self) -> None:
        self.closed = True


def _service(provider: RoutingProvider, gateway: FakeGateway, *, threshold: int = 3):
    return SpecificMetricResolution(
        tool_gateway=gateway,
        llm_caller=StructuredLLMCaller([provider]),
        owns_caller=False,
        breaker_threshold=threshold,
    )


# ==================================================================================================
# Domain builders.
# ==================================================================================================
def _metric(label: str, evidence_class: str = "factual") -> MetricSpec:
    source = (
        MetricResolutionSource(web_target=f"{label} facts", scrape_target=f"{label} page")
        if evidence_class == "factual"
        else MetricResolutionSource(web_target=f"{label} accounts", review_target="reviews")
    )
    return MetricSpec(
        label=label,
        question=f"What is the {label}?",
        value_type="boolean",
        unit=None,
        enum_values=[],
        evidence_class=evidence_class,
        resolution_source=source,
        verification="stated explicitly",
        null_policy="null",
        band="specific_attributes",
    )


METRICS = [
    _metric("free_with_pass"),
    _metric("adult_price"),
    _metric("weekday_crowding", "experiential"),
]
LABELS = [m.label for m in METRICS]
A, B, C, D, E = "Alpha", "Bravo", "Charlie", "Delta", "Echo"


def _rec(place_id: str, word: str) -> PredefinedMetricsRecord:
    # "<word> Climbing Gym" + "<word>climbinggym.com": the real gate trusts it (SLD match), so the
    # entry tests never run discovery and every LLM call is a phase-1 call.
    return PredefinedMetricsRecord(
        category_id=1,
        taxonomy_node="climbing_gym",
        depth="specific_attributes",
        place_id=place_id,
        name=f"{word} Climbing Gym",
        category=None,
        address=f"1 {word} Street, Portside 30301",
        website=f"https://{word.lower()}climbinggym.com",
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


def _state(words: list[str]) -> AmenitySearchState:
    plan = CategoryMetricPlan(1, "climbing_gym", "specific_attributes", [], METRICS)
    return AmenitySearchState(
        origin=GeoPoint(0.0, 0.0),
        radius_km=2.0,
        category_metric_plans=[plan],
        discovered_places={1: {w.lower(): CanonicalPlace(w.lower(), {}) for w in words}},
        predefined_records={1: {w.lower(): _rec(w.lower(), w) for w in words}},
    )


def _obj(amenity: str, label: str, tag: str = "") -> str:
    return f"{amenity} {label}{tag}"


def _call(call_id: str, amenity: str, label: str | None, tag: str = "", name="web_search"):
    args: dict = {"objective": _obj(amenity, label or "untagged", tag), "search_queries": ["q"]}
    if label is not None:
        args["metric_label"] = label
    return ToolCall(id=call_id, name=name, arguments=json.dumps(args))


def _turn(*calls: ToolCall) -> AssistantTurn:
    return AssistantTurn(
        provider="openai",
        finish_reason="tool_calls",
        content=None,
        tool_calls=tuple(calls),
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in calls
            ],
        },
    )


def _turn1(amenity: str, prefix: str = "t1") -> AssistantTurn:
    return _turn(*(_call(f"{prefix}_{i}", amenity, label) for i, label in enumerate(LABELS)))


def _result(objective: str, hits) -> WebSearchResult:
    excerpts = tuple(SearchExcerpt(url=u, title=t, text=x) for u, t, x in hits)
    return WebSearchResult(objective, ("q",), excerpts, RETRIEVED_AT)


def _ok(objective: str, url: str = "https://hit.example/page") -> WebSearchResult:
    return _result(objective, [(url, "Title", f"text for {objective}")])


def _empty(objective: str) -> WebSearchResult:
    return _result(objective, [])


def _fail(kind: str = "timeout") -> ToolFailure:
    return ToolFailure("web_search", kind, "x")


async def _loop(service: SpecificMetricResolution, amenity: str = A):
    """Run the real `_phase1_loop` for one amenity with an official site."""
    word = amenity
    rec = _rec(word.lower(), word)
    work_item = _DiscoveryWorkItem(1, word.lower(), "climbing_gym", "specific_attributes", METRICS)
    website = WebsiteSearchResult(rec.website, "google")
    return await service._phase1_loop(
        work_item, rec, website, CATALOG, _CircuitBreaker(threshold=3), "run"
    )


def _rec_name(amenity: str) -> str:
    return f"{amenity} Climbing Gym"


def _assert_replayable(messages: list[dict]) -> None:
    """The provider's pairing rule: each assistant message's tool calls are answered by exactly
    the tool messages that immediately follow it (one per id), and no tool message stands alone."""
    i = 0
    while i < len(messages):
        message = messages[i]
        if message["role"] == "tool":
            raise AssertionError(f"tool message {message['tool_call_id']} has no assistant before it")
        i += 1
        if message["role"] != "assistant":
            continue
        ids = [c["id"] for c in message.get("tool_calls", [])]
        assert ids, "a replayed assistant message must carry at least one tool call"
        assert len(ids) == len(set(ids)), "duplicate tool_call ids in one assistant message"
        answered = []
        while i < len(messages) and messages[i]["role"] == "tool":
            answered.append(messages[i]["tool_call_id"])
            i += 1
        assert sorted(answered) == sorted(ids), f"calls {ids} answered by {answered}"


def _tool_payloads(messages: list[dict]) -> dict[str, dict]:
    return {m["tool_call_id"]: json.loads(m["content"]) for m in messages if m["role"] == "tool"}


# ==================================================================================================
# Budget and termination (the app owns attempts; every gateway call is billed).
# ==================================================================================================
async def test_no_metric_gets_more_than_two_billed_searches_even_when_the_llm_keeps_asking():
    """Behavior: on the retry turn, done (`ok`), terminal (`empty`) and duplicate calls are not run;
    only the failed metric's first call reaches the gateway.
    Core: one search + one retry per metric; `ok`/`empty` never searched again.
    Real-vs-mock: real loop, guard, admission; faked provider + gateway.
    Evidence: per-metric gateway invocation counts are the billed-search behavior itself.
    """
    free, price, crowd = LABELS
    provider = RoutingProvider({_rec_name(A): [
        _turn1(A),
        _turn(
            _call("r_0", A, free),
            _call("r_1", A, price),
            _call("r_2", A, crowd),
            _call("r_3", A, crowd, tag=" again"),
        ),
    ]})
    gateway = FakeGateway({
        _obj(A, free): [_ok(_obj(A, free))],
        _obj(A, price): [_empty(_obj(A, price))],
        _obj(A, crowd): [_fail("timeout"), _ok(_obj(A, crowd))],
    })
    result = await _loop(_service(provider, gateway))

    per_metric = {label: sum(label in c for c in gateway.search_calls) for label in LABELS}
    assert per_metric == {free: 1, price: 1, crowd: 2}
    assert len(gateway.search_calls) == 4
    assert {k: v.attempts_used for k, v in result.metric_outcomes.items()} == {
        free: 1, price: 1, crowd: 2,
    }
    assert result.metric_outcomes[crowd].status == "ok"


@pytest.mark.parametrize("scenario", ["all_empty", "fails_twice"])
async def test_phase1_never_runs_more_than_two_llm_turns_and_needs_a_failure_for_the_second(
    scenario,
):
    """Behavior: all-`empty` → one LLM turn; a metric failing twice → exactly two turns, no third.
    Core: retry turn only when something is retry-eligible; at most two turns.
    Real-vs-mock: real loop; faked provider (queue has spare turns a buggy loop would consume).
    Evidence: the provider's call count is the cost boundary.
    """
    free, price, crowd = LABELS
    spare = [_turn1(A, "x1"), _turn1(A, "x2")]
    if scenario == "all_empty":
        outcomes = {_obj(A, label): [_empty(_obj(A, label))] for label in LABELS}
        queue = [_turn1(A)] + spare
    else:
        outcomes = {
            _obj(A, free): [_ok(_obj(A, free))],
            _obj(A, price): [_ok(_obj(A, price))],
            _obj(A, crowd): [_fail("transport"), _fail("transport"), _fail("transport")],
        }
        queue = [_turn1(A), _turn(_call("r_2", A, crowd))] + spare
    provider = RoutingProvider({_rec_name(A): queue})
    result = await _loop(_service(provider, FakeGateway(outcomes)))

    if scenario == "all_empty":
        assert provider.total_calls() == 1 and result.turns_run == 1
        assert {r.status for r in result.metric_outcomes.values()} == {"empty"}
    else:
        assert provider.total_calls() == 2 and result.turns_run == 2
        assert result.metric_outcomes[crowd].status == "failed"
        assert result.metric_outcomes[crowd].attempts_used == 2


# ==================================================================================================
# The shared conversation (triage and phase 2 continue it; a malformed history breaks them).
# ==================================================================================================
async def test_retry_turn_resends_turn_one_history_unchanged_with_the_failure_named():
    """Behavior: turn 2 is sent exactly the turn-1 history + the turn-1 assistant message + its tool
    messages (no new user message), and the failed message names the metric and the failure.
    Core: "nothing re-sent"; the failed tool message carries label + kind, no retry flag.
    Real-vs-mock: real loop; faked provider records what it actually received.
    Evidence: compares the two histories the provider saw, not the loop's internal list.
    """
    free, price, crowd = LABELS
    provider = RoutingProvider({_rec_name(A): [_turn1(A), _turn(_call("r_1", A, price))]})
    gateway = FakeGateway({
        _obj(A, free): [_ok(_obj(A, free))],
        _obj(A, price): [_fail("timeout"), _ok(_obj(A, price))],
        _obj(A, crowd): [_ok(_obj(A, crowd))],
    })
    await _loop(_service(provider, gateway))

    first, second = provider.sent[_rec_name(A)]
    assert [m["role"] for m in first] == ["system", "user"]
    assert second[:2] == first  # instruction and user turn untouched
    assert [m["role"] for m in second[2:]] == ["assistant", "tool", "tool", "tool"]
    failed = [p for p in _tool_payloads(second).values() if p["status"] == "failed"]
    assert failed == [{"status": "failed", "metric_label": price, "failure": "timed out"}]


async def test_history_stays_replayable_through_rejected_skipped_and_out_of_catalog_calls():
    """Behavior: after a guard-rejected turn 1 (invalid label + out-of-catalog call + valid sibling)
    and a turn 2 with a duplicate and a done metric, the conversation still satisfies the provider's
    tool-call pairing rule, and the out-of-catalog call is gone.
    Core: every kept call gets exactly one tool message right after its assistant message.
    Real-vs-mock: real guard + steps 3-5 + admission; faked edges.
    Evidence: validates the final message list with the pairing rule a provider enforces.
    """
    free, price, crowd = LABELS
    rejected = _turn(
        _call("t1_0", A, free),
        _call("t1_1", A, "no_such_metric"),
        _call("t1_2", A, crowd),
        ToolCall(id="t1_3", name="firecrawl_scrape", arguments="{}"),
    )
    retry = _turn(
        _call("r_0", A, free),
        _call("r_1", A, free, tag=" again"),
        _call("r_2", A, crowd),
    )
    provider = RoutingProvider({_rec_name(A): [rejected, retry]})
    gateway = FakeGateway({
        _obj(A, free): [_ok(_obj(A, free))],
        _obj(A, crowd): [_ok(_obj(A, crowd))],
    })
    result = await _loop(_service(provider, gateway))

    _assert_replayable(result.messages)
    all_ids = [
        c["id"] for m in result.messages if m["role"] == "assistant" for c in m["tool_calls"]
    ]
    assert "t1_3" not in all_ids  # out-of-catalog call removed before replay
    # The replayed history is also what the provider received on turn 2.
    _assert_replayable(provider.sent[_rec_name(A)][1])


async def test_two_rejected_turns_end_metrics_failed_without_any_billed_search():
    """Behavior: both turns guard-rejected → attributed metrics end failed/rejected with 2 attempts,
    no gateway call is ever made, and there is no third LLM turn.
    Core: a rejection spends the attempt but is never executed.
    Real-vs-mock: real guard + attribution; faked edges (spare turn queued).
    Evidence: zero gateway calls and the provider call count.
    """
    free, price, crowd = LABELS
    bad1 = _turn(_call("t1_0", A, free), _call("t1_1", A, crowd), _call("t1_2", A, "bogus"))
    bad2 = _turn(_call("r_0", A, free), _call("r_1", A, crowd), _call("r_2", A, "bogus"))
    provider = RoutingProvider({_rec_name(A): [bad1, bad2, _turn1(A, "spare")]})
    gateway = FakeGateway()
    result = await _loop(_service(provider, gateway))

    assert gateway.search_calls == []
    assert provider.total_calls() == 2
    for label in (free, crowd):
        row = result.metric_outcomes[label]
        assert (row.status, row.attempts_used, row.failure_kind) == ("failed", 2, "rejected")
    assert result.uncovered_labels == (price,)
    _assert_replayable(result.messages)


# ==================================================================================================
# Evidence (R3.M2.4 checks quotes against shaped_text; attribution feeds each metric's bucket).
# ==================================================================================================
_REAL_FAQ_TEXT = (
    "Read our [cookie policy](https://www.rijksmuseum.nl/en/footer/cookie-policy) .\n\n"
    "# FAQ Tickets and visit\n\n## TICKETS\n\n...\n\n"
    "  These are the prices:\n  \n    + Adults: € 25\n    + Up to 18 years old: free\n"
    "    + Museum card, I Amsterdam City Card, ICOM, Amsterdamse Stadspas , Vereniging: free\n\n"
    "...\n\nThe relatively quiet days are Tuesday and Wednesday."
)
_REAL_PRICES_TEXT = (
    "# Admissions and opening hours\n\nIt is our pleasure to welcome you!\n\n"
    "## Admission prices\n\n* Adults: €25\n* Free for ages 18 and under\n"
    "* Half-price for CJP and EYCA members: €11,25"
)
_PRICES_URL = "https://www.rijksmuseum.nl/en/visit/practical-info/opening-hours-and-prices"


async def test_evidence_text_is_exactly_what_the_llm_saw_for_real_multiline_excerpts():
    """Behavior: every recorded item's text equals the hit the LLM received (title + newline +
    text; text only when the title is missing), with the call's retrieved_at and its own label.
    Core: shaped_text is the provenance target for R3.M2.4's quote check.
    Real-vs-mock: real shaping + recording; real-run excerpt shapes; faked edges.
    Evidence: the expected text is rebuilt from the parsed tool-message JSON (the LLM's view), so
    any divergence between the two code paths fails it.
    """
    free, price, crowd = LABELS
    hits = [
        ("https://www.rijksmuseum.nl/en/visit/faq", "FAQ - Rijksmuseum", _REAL_FAQ_TEXT),
        (_PRICES_URL, "Opening hours and prices - Rijksmuseum", _REAL_PRICES_TEXT),
        ("https://untitled.example/page", None, "A hit with no title.\n\nSecond paragraph."),
    ]
    provider = RoutingProvider({_rec_name(A): [_turn1(A)]})
    gateway = FakeGateway({
        _obj(A, free): [_result(_obj(A, free), hits)],
        _obj(A, price): [_empty(_obj(A, price))],
        _obj(A, crowd): [_empty(_obj(A, crowd))],
    })
    result = await _loop(_service(provider, gateway))

    seen = _tool_payloads(result.messages)["t1_0"]["hits"]
    expected = {
        (h["url"], f"{h['title']}\n{h['text']}" if h["title"] else h["text"]) for h in seen
    }
    items = result.metrics_source_content.items_for(free)
    assert {(i.url, i.shaped_text) for i in items} == expected
    assert len(items) == 3
    assert all(i.retrieved_at == RETRIEVED_AT and i.metric_labels == {free} for i in items)
    assert all(i.source_kind == "web" for i in items)


async def test_url_is_part_of_evidence_identity_even_for_near_duplicates():
    """Behavior: real near-duplicate URLs (`...prices` vs `...prices%20`) with identical text stay
    two items; the identical hit found by two metrics is one item carrying both labels.
    Core: identity is (source_kind, url, shaped_text).
    Real-vs-mock: real store via the loop; faked edges.
    Evidence: observable item count and label sets.
    """
    free, price, crowd = LABELS
    title = "Opening hours and prices - Rijksmuseum"
    faq = ("https://www.rijksmuseum.nl/en/visit/faq", "FAQ - Rijksmuseum", _REAL_FAQ_TEXT)
    provider = RoutingProvider({_rec_name(A): [_turn1(A)]})
    gateway = FakeGateway({
        _obj(A, free): [_result(_obj(A, free), [
            (_PRICES_URL, title, _REAL_PRICES_TEXT),
            (_PRICES_URL + "%20", title, _REAL_PRICES_TEXT),
            faq,
        ])],
        _obj(A, price): [_result(_obj(A, price), [faq])],
        _obj(A, crowd): [_empty(_obj(A, crowd))],
    })
    result = await _loop(_service(provider, gateway))

    items = result.metrics_source_content.items
    assert len(items) == 3
    by_url = {i.url: i for i in items}
    assert by_url[_PRICES_URL].metric_labels == {free}
    assert by_url[_PRICES_URL + "%20"].metric_labels == {free}
    assert by_url[faq[0]].metric_labels == {free, price}


async def test_each_metric_bucket_holds_only_evidence_from_its_own_search():
    """Behavior: two `ok` metrics in the same turn each get exactly their own call's hits; a metric
    that failed on turn 1 and came back `empty` on its retry gets no items.
    Core: attribution is per tagged call; only `ok` results record evidence.
    Real-vs-mock: real loop + store; faked edges.
    Evidence: bucket URL sets compared with each metric's own hits; two ok metrics in one turn make
    cross-attribution observable.
    """
    free, price, crowd = LABELS
    provider = RoutingProvider({_rec_name(A): [_turn1(A), _turn(_call("r_2", A, crowd))]})
    gateway = FakeGateway({
        _obj(A, free): [_result(_obj(A, free), [
            ("https://a.example/1", "A1", "a one"), ("https://a.example/2", "A2", "a two"),
        ])],
        _obj(A, price): [_result(_obj(A, price), [("https://b.example/1", "B1", "b one")])],
        _obj(A, crowd): [_fail("timeout"), _empty(_obj(A, crowd))],
    })
    result = await _loop(_service(provider, gateway))
    store = result.metrics_source_content

    assert {i.url for i in store.items_for(free)} == {"https://a.example/1", "https://a.example/2"}
    assert {i.url for i in store.items_for(price)} == {"https://b.example/1"}
    assert store.items_for(crowd) == ()
    assert result.metric_outcomes[crowd].status == "empty"
    assert len(store.items) == 3


async def test_empty_and_failed_stay_distinct_outcomes():
    """Behavior: `empty` is terminal with no failure kind; `failed` keeps the last gateway kind.
    Core: R3.M2 maps empty → no_evidence and failed → tool-failure reason.
    Real-vs-mock: real loop + shaping; faked edges.
    Evidence: (status, attempts_used, failure_kind) triples per metric.
    """
    free, price, crowd = LABELS
    provider = RoutingProvider({_rec_name(A): [_turn1(A), _turn(_call("r_2", A, crowd))]})
    gateway = FakeGateway({
        _obj(A, free): [_ok(_obj(A, free))],
        _obj(A, price): [_empty(_obj(A, price))],
        _obj(A, crowd): [_fail("timeout"), _fail("rate_limited")],
    })
    outcomes = (await _loop(_service(provider, gateway))).metric_outcomes

    triples = {k: (v.status, v.attempts_used, v.failure_kind) for k, v in outcomes.items()}
    assert triples == {
        free: ("ok", 1, None),
        price: ("empty", 1, None),
        crowd: ("failed", 2, "rate_limited"),
    }


# ==================================================================================================
# Failure isolation through the real entry point (D5).
# ==================================================================================================
async def test_tool_failures_never_end_the_amenity():
    """Behavior: every search fails in both turns, yet the amenity completes (all metrics failed,
    no evidence) and the run does not raise.
    Core: a tool failure becomes a failed tool message; only provider failures end an amenity.
    Real-vs-mock: real entry, gate, pipelines, sweep; faked edges.
    Evidence: record outcome `completed`, not `resolution_call_failed` / `pipeline_error`.
    """
    provider = RoutingProvider({_rec_name(A): [
        _turn1(A), _turn(*(_call(f"r_{i}", A, label) for i, label in enumerate(LABELS))),
    ]})
    gateway = FakeGateway({_obj(A, label): [_fail("transport")] * 2 for label in LABELS})
    state = await _service(provider, gateway).run_specific_metric_resolution(_state([A]))

    record = state.phase1_results[(1, "alpha")]
    assert record.outcome == "completed"
    assert {r.status for r in record.phase1.metric_outcomes.values()} == {"failed"}
    assert record.phase1.metrics_source_content.items == []
    assert len(gateway.search_calls) == 6 and gateway.closed


async def test_retry_turn_provider_failure_discards_only_that_amenitys_evidence():
    """Behavior: amenity A gathers evidence on turn 1, then its retry turn hits a provider refusal;
    A ends `resolution_call_failed` with no phase-1 output, while B completes normally.
    Core: a provider failure in any LLM step ends that amenity and discards its evidence; siblings
    are isolated; the run returns because one pipeline completed.
    Real-vs-mock: real entry + caller cause aggregation + pipeline catch; routing provider keeps A
    and B deterministic under concurrency.
    Evidence: A's turn-1 searches succeeded (gateway calls made) yet its record holds no evidence.
    """
    free, price, crowd = LABELS
    provider = RoutingProvider({
        _rec_name(A): [
            _turn1(A),
            LLMProviderError("refused", failure_class="content"),
        ],
        _rec_name(B): [_turn1(B)],
    })
    gateway = FakeGateway({
        _obj(A, free): [_ok(_obj(A, free))],
        _obj(A, price): [_ok(_obj(A, price))],
        _obj(A, crowd): [_fail("timeout")],
        **{_obj(B, label): [_ok(_obj(B, label))] for label in LABELS},
    })
    state = await _service(provider, gateway).run_specific_metric_resolution(_state([A, B]))

    a, b = state.phase1_results[(1, "alpha")], state.phase1_results[(1, "bravo")]
    assert sum(_obj(A, "") in c for c in gateway.search_calls) == 3  # A's turn 1 did search
    assert (a.outcome, a.phase1) == ("resolution_call_failed", None)
    assert (a.failed_stage, a.failed_cause) == ("r3_m1_4_phase1_retry", "content")
    assert b.outcome == "completed"
    assert {r.status for r in b.phase1.metric_outcomes.values()} == {"ok"}
    assert len(b.phase1.metrics_source_content.items) == 3


# ==================================================================================================
# Run-level circuit breaker (R3.M1.5), counted in completion order.
# ==================================================================================================
@pytest.fixture
def one_pipeline_at_a_time(monkeypatch):
    """Run pipelines sequentially so completion order (what the breaker counts) is deterministic."""
    monkeypatch.setattr(smr, "AMENITY_PIPELINE_CONCURRENCY", 1)


def _timeout_error() -> LLMProviderError:
    return LLMProviderError("timed out", failure_class="availability")


async def test_availability_outage_opens_breaker_and_later_amenities_make_no_llm_call(
    one_pipeline_at_a_time,
):
    """Behavior: with threshold 2, two availability failures open the breaker; the remaining three
    amenities stop with `circuit_open` without calling the provider; the run raises.
    Core: N consecutive availability failures open the breaker for the rest of the run.
    Real-vs-mock: real breaker + caller + pipeline catch; faked provider (every turn times out).
    Evidence: exact provider call count and the ordered causes.
    """
    words = [A, B, C, D, E]
    provider = RoutingProvider({_rec_name(w): [_timeout_error()] * 3 for w in words})
    gateway = FakeGateway()
    state = _state(words)
    with pytest.raises(MetricResolutionProviderError) as exc:
        await _service(provider, gateway, threshold=2).run_specific_metric_resolution(state)

    assert exc.value.cause == "circuit_open"
    assert provider.total_calls() == 2
    causes = [state.phase1_results[(1, w.lower())].failed_cause for w in words]
    assert causes == ["availability", "availability", "circuit_open", "circuit_open", "circuit_open"]
    assert gateway.search_calls == [] and gateway.closed


async def test_content_failures_never_open_the_breaker(one_pipeline_at_a_time):
    """Behavior: three content refusals in a row (threshold 2) never open the breaker: every
    amenity reaches the provider, and the run raises with `content`.
    Core: only `availability` moves the counter.
    Real-vs-mock: real breaker + caller; faked provider refuses.
    Evidence: provider called once per amenity and no `circuit_open` anywhere.
    """
    words = [A, B, C]
    refusal = LLMProviderError("refused", failure_class="content")
    provider = RoutingProvider({_rec_name(w): [refusal] for w in words})
    state = _state(words)
    with pytest.raises(MetricResolutionProviderError) as exc:
        await _service(provider, FakeGateway(), threshold=2).run_specific_metric_resolution(state)

    assert exc.value.cause == "content"
    assert provider.total_calls() == 3
    assert [state.phase1_results[(1, w.lower())].failed_cause for w in words] == ["content"] * 3


async def test_a_successful_llm_call_resets_the_outage_count(one_pipeline_at_a_time):
    """Behavior: fail (availability), succeed, fail (availability), then a fourth amenity, with
    threshold 2 → the breaker stays closed, so the fourth amenity still reaches the provider and
    completes; nothing is `circuit_open` and the run returns normally.
    Core: "consecutive" means no LLM success in between.
    Real-vs-mock: real breaker + caller; faked edges.
    Evidence: without the reset, the two failures (A and C) would trip the breaker and D would be
    `circuit_open` with no provider call; D completing and 4 provider calls prove the reset.
    """
    words = [A, B, C, D]
    provider = RoutingProvider({
        _rec_name(A): [_timeout_error()],
        _rec_name(B): [_turn1(B)],
        _rec_name(C): [_timeout_error()],
        _rec_name(D): [_turn1(D)],
    })
    gateway = FakeGateway({
        _obj(w, label): [_ok(_obj(w, label))] for w in (B, D) for label in LABELS
    })
    state = await _service(provider, gateway, threshold=2).run_specific_metric_resolution(
        _state(words)
    )

    outcomes = [
        (state.phase1_results[(1, w.lower())].outcome,
         state.phase1_results[(1, w.lower())].failed_cause)
        for w in words
    ]
    assert outcomes == [
        ("resolution_call_failed", "availability"),
        ("completed", None),
        ("resolution_call_failed", "availability"),
        ("completed", None),
    ]
    assert provider.total_calls() == 4
