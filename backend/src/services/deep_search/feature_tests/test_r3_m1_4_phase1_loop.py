"""R3.M1.4 step 1 — Phase-1 Loop, run-level circuit breaker, and STEP 4/5 behavior suite.

No live calls. Fakes stand in ONLY for the non-deterministic edges: the LLM provider (queued
assistant turns or provider errors) and the MCP gateway (`search_web` outcomes keyed by objective,
so the concurrent `gather` order cannot change which outcome a call gets). Everything the app
decides runs for real: the shared `StructuredLLMCaller` funnel and its `cause` aggregation, the
R3.M1.1 catalog + guard + steps 3-5, the budget admission, R3.M1.2 shaping, evidence recording,
the breaker, and the pipeline catch / sweep.

Each test asserts an observable outcome: the ledger, the shared message list, the evidence store,
the record written to state, a raised error, or a gateway call count where the absence of a call
IS the behavior (no retry of `empty`, no search once the breaker is open).
"""

import json

import pytest

from src.clients.llm_provider import AssistantTurn, StructuredLLMCaller, ToolCall
from src.clients.mcp_tools import RawToolDefinition, SearchExcerpt, ToolFailure, WebSearchResult
from src.exceptions.deep_search import MetricResolutionProviderError
from src.exceptions.llm import LLMProviderError
from src.services.deep_search.feature_prompts.phase1_web_search_instruction import (
    build_phase1_search_instruction,
)
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    MetricResolutionSource,
    MetricsSourceContent,
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

# --------------------------------------------------------------------------------------------------
# Edge fakes.
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
CATALOG = build_tool_catalog(RAW_DEFS, "metric_web_search")


class FakeProvider:
    """Pops queued assistant turns (or raises queued errors); records the history it was sent."""

    def __init__(self, name="openai", *, turns=None, bodies=None) -> None:
        self.name = name
        self.model = f"{name}-model"
        self._turns = list(turns or [])
        self._bodies = list(bodies or [])
        self.sent_histories: list[list[dict]] = []

    async def generate_turn(self, *, messages, tools, tool_choice):
        self.sent_histories.append([dict(m) for m in messages])
        assert tool_choice == "required"
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
        pass


class FakeGateway:
    """Serves `search_web` outcomes by objective (a list per objective = one per attempt)."""

    def __init__(self, outcomes: dict | None = None) -> None:
        self._outcomes = {k: list(v) for k, v in (outcomes or {}).items()}
        self.search_calls: list[tuple[str, tuple[str, ...]]] = []
        self.opened = self.closed = False

    async def open(self) -> None:
        self.opened = True

    def get_tool_definitions(self):
        return RAW_DEFS

    async def search_web(self, objective, search_queries):
        self.search_calls.append((objective, tuple(search_queries)))
        return self._outcomes[objective].pop(0)

    async def aclose(self) -> None:
        self.closed = True


def _service(gateway, turns, *, threshold=3) -> tuple[SpecificMetricResolution, FakeProvider]:
    provider = FakeProvider(turns=turns)
    service = SpecificMetricResolution(
        tool_gateway=gateway,
        llm_caller=StructuredLLMCaller([provider]),
        owns_caller=False,
        breaker_threshold=threshold,
    )
    return service, provider


# --------------------------------------------------------------------------------------------------
# Domain builders (fresh venue, not any prompt worked example).
# --------------------------------------------------------------------------------------------------
def _metric(label, evidence_class="factual") -> MetricSpec:
    source = (
        MetricResolutionSource(web_target=f"{label} info", scrape_target=f"{label} page")
        if evidence_class == "factual"
        else MetricResolutionSource(web_target=f"{label} reviews", review_target="reviews")
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


METRICS = [_metric("dogs_allowed"), _metric("has_lockers"), _metric("noise_level", "experiential")]


def _rec(place_id="p1", name="Harbor Climbing Gym") -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=1,
        taxonomy_node="climbing_gym",
        depth="specific_attributes",
        place_id=place_id,
        name=name,
        category=None,
        address="4 Pier Rd, Portside 30301",
        website="https://harborclimbinggym.com",
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


def _work_item(place_id="p1", metrics=None) -> _DiscoveryWorkItem:
    return _DiscoveryWorkItem(1, place_id, "climbing_gym", "specific_attributes", metrics or METRICS)


WEBSITE = WebsiteSearchResult("https://harborclimbinggym.com", "google")


def _call(call_id, label, objective=None, name="web_search", **overrides) -> ToolCall:
    args = {"objective": objective or f"obj {label}", "search_queries": [f"q {label}"]}
    if label is not None:
        args["metric_label"] = label
    args.update(overrides)
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
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in calls
            ],
        },
    )


def _ok(objective, hits=(("https://a.example/x", "Title A", "text a"),)) -> WebSearchResult:
    excerpts = tuple(SearchExcerpt(url=u, title=t, text=x) for u, t, x in hits)
    return WebSearchResult(objective, ("q",), excerpts, "2026-10-29T00:00:00+00:00")


def _empty(objective) -> WebSearchResult:
    return WebSearchResult(objective, ("q",), (), "2026-10-29T00:00:00+00:00")


def _failure(kind="timeout") -> ToolFailure:
    return ToolFailure("web_search", kind, "x")


def _all_three_turn(prefix="t") -> AssistantTurn:
    return _turn(*(_call(f"{prefix}{i}", m.label) for i, m in enumerate(METRICS)))


async def _loop(service, *, metrics=None, website=WEBSITE, breaker=None):
    return await service._phase1_loop(
        _work_item(metrics=metrics), _rec(), website, CATALOG,
        breaker or _CircuitBreaker(threshold=3), "run",
    )


def _tool_messages(messages):
    return [m for m in messages if m["role"] == "tool"]


def _answered_once(messages) -> bool:
    """Every assistant tool_call id has exactly one tool message, and no tool message is orphaned."""
    call_ids = [
        c["id"] for m in messages if m["role"] == "assistant" for c in m.get("tool_calls", [])
    ]
    tool_ids = [m["tool_call_id"] for m in _tool_messages(messages)]
    return sorted(call_ids) == sorted(tool_ids) and len(set(call_ids)) == len(call_ids)


# --------------------------------------------------------------------------------------------------
# Phase-1 Loop.
# --------------------------------------------------------------------------------------------------
async def test_all_ok_turn_one_ends_phase_without_retry_and_records_evidence():
    gateway = FakeGateway({f"obj {m.label}": [_ok(f"obj {m.label}")] for m in METRICS})
    service, provider = _service(gateway, [_all_three_turn()])
    result = await _loop(service)

    assert len(provider.sent_histories) == 1  # no further LLM call
    assert result.turns_run == 1
    assert {r.status for r in result.metric_outcomes.values()} == {"ok"}
    assert all(r.attempts_used == 1 for r in result.metric_outcomes.values())
    # The same hit text came back for three metrics -> one item, labels unioned (identity rule).
    assert len(result.metrics_source_content.items) == 1
    item = result.metrics_source_content.items[0]
    assert item.metric_labels == {m.label for m in METRICS}
    assert item.shaped_text == "Title A\ntext a"
    assert _answered_once(result.messages)


async def test_failed_metric_gets_one_retry_turn_for_only_that_metric():
    gateway = FakeGateway({
        "obj dogs_allowed": [_ok("obj dogs_allowed")],
        "obj has_lockers": [_failure("timeout"), _ok("obj has_lockers")],
        "obj noise_level": [_empty("obj noise_level")],
    })
    service, provider = _service(gateway, [_all_three_turn(), _turn(_call("r1", "has_lockers"))])
    result = await _loop(service)

    assert result.turns_run == 2
    lockers = result.metric_outcomes["has_lockers"]
    assert (lockers.status, lockers.attempts_used) == ("ok", 2)
    # The retry turn saw the full history (nothing re-sent): the failed result is in it.
    retry_history = provider.sent_histories[1]
    failed = [
        json.loads(m["content"]) for m in retry_history if m["role"] == "tool"
        if json.loads(m["content"])["status"] == "failed"
    ]
    assert failed == [{"status": "failed", "metric_label": "has_lockers", "failure": "timed out"}]
    assert _answered_once(result.messages)


async def test_empty_is_terminal_and_never_retried():
    gateway = FakeGateway({
        "obj dogs_allowed": [_empty("obj dogs_allowed")],
        "obj has_lockers": [_ok("obj has_lockers")],
        "obj noise_level": [_ok("obj noise_level")],
    })
    service, provider = _service(gateway, [_all_three_turn()])
    result = await _loop(service)
    dogs = result.metric_outcomes["dogs_allowed"]
    assert (dogs.status, dogs.attempts_used) == ("empty", 1)
    assert len(provider.sent_histories) == 1
    assert len(gateway.search_calls) == 3
    assert result.metrics_source_content.items_for("dogs_allowed") == ()


async def test_guard_rejected_turn_spends_attempts_strips_stray_call_and_retries():
    bad_turn = _turn(
        _call("t0", "dogs_allowed"),
        _call("t1", "not_a_metric"),  # out-of-set label -> whole message rejected
        _call("t2", "noise_level"),
        ToolCall(id="t3", name="firecrawl_scrape", arguments="{}"),  # out of catalog
    )
    retry = _turn(_call("r0", "dogs_allowed"), _call("r2", "noise_level"))
    gateway = FakeGateway({
        "obj dogs_allowed": [_ok("obj dogs_allowed")],
        "obj noise_level": [_ok("obj noise_level", hits=(("https://b", "B", "b"),))],
    })
    service, provider = _service(gateway, [bad_turn, retry])
    result = await _loop(service)

    assert result.turns_run == 2
    assert result.metric_outcomes["dogs_allowed"].attempts_used == 2
    assert result.metric_outcomes["dogs_allowed"].status == "ok"
    assert result.metric_outcomes["has_lockers"].status == "not_searched"
    assert result.uncovered_labels == ("has_lockers",)
    # Out-of-catalog call removed from the replayed assistant message; every kept call answered.
    first_assistant = next(m for m in result.messages if m["role"] == "assistant")
    assert [c["id"] for c in first_assistant["tool_calls"]] == ["t0", "t1", "t2"]
    assert _answered_once(result.messages)


async def test_retry_turn_does_not_run_done_metrics_or_duplicates():
    gateway = FakeGateway({
        "obj dogs_allowed": [_ok("obj dogs_allowed")],
        "obj has_lockers": [_failure("transport"), _ok("obj has_lockers")],
        "obj noise_level": [_ok("obj noise_level")],
    })
    retry = _turn(
        _call("r0", "dogs_allowed"),  # already ok -> not executed
        _call("r1", "has_lockers"),
        _call("r2", "has_lockers", objective="obj has_lockers again"),  # duplicate -> not executed
    )
    service, _ = _service(gateway, [_all_three_turn(), retry])
    result = await _loop(service)

    assert len(gateway.search_calls) == 4  # 3 in turn 1 + only the eligible retry
    assert result.metric_outcomes["dogs_allowed"].attempts_used == 1
    retry_payloads = {
        m["tool_call_id"]: json.loads(m["content"]) for m in _tool_messages(result.messages)
    }
    assert retry_payloads["r0"]["failure"].startswith("not run: this metric was already searched")
    assert retry_payloads["r2"]["failure"].startswith("not run: another call in this turn")
    assert _answered_once(result.messages)


async def test_metric_with_no_call_is_uncovered_and_gets_no_retry():
    gateway = FakeGateway({
        "obj dogs_allowed": [_ok("obj dogs_allowed")],
        "obj noise_level": [_ok("obj noise_level")],
    })
    turn = _turn(_call("t0", "dogs_allowed"), _call("t2", "noise_level"))
    service, provider = _service(gateway, [turn])
    result = await _loop(service)
    assert result.uncovered_labels == ("has_lockers",)
    assert len(provider.sent_histories) == 1  # untagged is not retry-eligible


async def test_still_failed_after_retry_stays_failed():
    gateway = FakeGateway({
        "obj dogs_allowed": [_failure("timeout"), _failure("rate_limited")],
        "obj has_lockers": [_ok("obj has_lockers")],
        "obj noise_level": [_ok("obj noise_level")],
    })
    service, _ = _service(gateway, [_all_three_turn(), _turn(_call("r0", "dogs_allowed"))])
    result = await _loop(service)
    dogs = result.metric_outcomes["dogs_allowed"]
    assert (dogs.status, dogs.attempts_used, dogs.failure_kind) == ("failed", 2, "rate_limited")


@pytest.mark.parametrize("fail_on_turn", [1, 2])
async def test_provider_error_in_either_turn_propagates_with_cause(fail_on_turn):
    timeout = LLMProviderError("timed out", failure_class="availability")
    gateway = FakeGateway({
        "obj dogs_allowed": [_failure("timeout")],
        "obj has_lockers": [_ok("obj has_lockers")],
        "obj noise_level": [_ok("obj noise_level")],
    })
    turns = [timeout] if fail_on_turn == 1 else [_all_three_turn(), timeout]
    service, _ = _service(gateway, turns)
    with pytest.raises(MetricResolutionProviderError) as exc:
        await _loop(service)
    assert exc.value.cause == "availability"
    assert exc.value.stage == ("r3_m1_4_phase1_turn1" if fail_on_turn == 1 else "r3_m1_4_phase1_retry")


async def test_unexpected_search_exception_is_shaped_failed_not_raised():
    class RaisingGateway(FakeGateway):
        async def search_web(self, objective, search_queries):
            if objective == "obj dogs_allowed":
                raise RuntimeError("boom")
            return await super().search_web(objective, search_queries)

    gateway = RaisingGateway({
        "obj has_lockers": [_ok("obj has_lockers")],
        "obj noise_level": [_ok("obj noise_level")],
    })
    # The raise is shaped `failed`, so dogs_allowed is retry-eligible; its retry also raises.
    service, _ = _service(gateway, [_all_three_turn(), _turn(_call("r0", "dogs_allowed"))])
    result = await _loop(service)
    dogs = result.metric_outcomes["dogs_allowed"]
    assert (dogs.status, dogs.failure_kind, dogs.attempts_used) == ("failed", "tool_error", 2)
    assert result.metric_outcomes["has_lockers"].status == "ok"
    assert _answered_once(result.messages)


# --------------------------------------------------------------------------------------------------
# Evidence identity and instruction rendering.
# --------------------------------------------------------------------------------------------------
def test_same_url_different_text_stays_two_items():
    store = MetricsSourceContent()
    a = store.record("web", "https://x", "T\none", "now", "m1")
    b = store.record("web", "https://x", "T\ntwo", "now", "m1")
    c = store.record("web", "https://x", "T\none", "now", "m2")
    assert a is not b and a is c
    assert len(store.items) == 2
    assert a.metric_labels == {"m1", "m2"}
    assert [i.evidence_id for i in store.items_for("m2")] == [a.evidence_id]


def test_instruction_host_scoping_is_per_metric():
    text = build_phase1_search_instruction(
        "Harbor Climbing Gym", "4 Pier Rd", "climbing_gym", "https://www.harborclimbinggym.com/", METRICS
    )
    metrics = json.loads(text.split("METRICS\n", 1)[1])
    by_label = {m["label"]: m for m in metrics}
    assert by_label["dogs_allowed"]["host_scoping"] == "include_site_query"
    assert by_label["dogs_allowed"]["site_host"] == "harborclimbinggym.com"
    assert by_label["noise_level"]["host_scoping"] == "no_site_query"
    assert "scrape_target" not in text and "review_target" not in text

    no_site = build_phase1_search_instruction("Gym", None, "climbing_gym", None, METRICS)
    assert all(
        m["host_scoping"] == "no_site_query" for m in json.loads(no_site.split("METRICS\n", 1)[1])
    )


# --------------------------------------------------------------------------------------------------
# Circuit breaker.
# --------------------------------------------------------------------------------------------------
def test_breaker_counts_only_availability_and_resets_on_success():
    breaker = _CircuitBreaker(threshold=2)
    breaker.record_failure("availability", "s")
    breaker.record_failure("content", "s")
    breaker.record_failure("circuit_open", "s")
    assert (breaker.counter, breaker.open) == (1, False)
    breaker.record_success()
    assert breaker.counter == 0
    breaker.record_failure("availability", "s")
    breaker.record_failure("availability", "s")
    assert breaker.open
    with pytest.raises(MetricResolutionProviderError) as exc:
        breaker.check("r3_m1_4_phase1_turn1")
    assert exc.value.cause == "circuit_open"


async def test_open_breaker_stops_phase1_before_any_llm_call_or_search():
    gateway = FakeGateway()
    service, provider = _service(gateway, [_all_three_turn()])
    breaker = _CircuitBreaker(threshold=1, open=True)
    with pytest.raises(MetricResolutionProviderError) as exc:
        await _loop(service, breaker=breaker)
    assert exc.value.cause == "circuit_open"
    assert provider.sent_histories == [] and gateway.search_calls == []


async def test_open_breaker_makes_discovery_return_none_without_searching():
    gateway = FakeGateway()
    service, provider = _service(gateway, [])
    rec = _rec()
    verdict, telemetry = await service._discover_website_url(
        _work_item(), rec, RAW_DEFS, "batch", breaker=_CircuitBreaker(threshold=1, open=True)
    )
    assert (verdict.website_url, verdict.website_origin, telemetry) == (None, "none", None)
    assert provider.sent_histories == []


# --------------------------------------------------------------------------------------------------
# STEP 4 / STEP 5 through the real entry point.
# --------------------------------------------------------------------------------------------------
def _state(place_ids) -> AmenitySearchState:
    plan = CategoryMetricPlan(1, "climbing_gym", "specific_attributes", [], METRICS)
    return AmenitySearchState(
        origin=GeoPoint(0.0, 0.0),
        radius_km=2.0,
        category_metric_plans=[plan],
        discovered_places={1: {pid: CanonicalPlace(pid, {}) for pid in place_ids}},
        # Each record's own Google website passes the official-URL gate, so no discovery search.
        predefined_records={
            1: {
                pid: _rec(pid, name="Harbor Climbing Gym")
                for pid in place_ids
            }
        },
    )


async def test_entry_writes_completed_record_per_amenity():
    gateway = FakeGateway({f"obj {m.label}": [_ok(f"obj {m.label}")] for m in METRICS})
    service, _ = _service(gateway, [_all_three_turn()])
    state = await service.run_specific_metric_resolution(_state(["p1"]))
    record = state.phase1_results[(1, "p1")]
    assert record.outcome == "completed"
    assert record.phase1.metric_outcomes["dogs_allowed"].status == "ok"
    assert state.website_search_results[(1, "p1")].website_origin == "google"
    assert gateway.closed


async def test_entry_mixed_results_do_not_raise():
    gateway = FakeGateway({f"obj {m.label}": [_ok(f"obj {m.label}")] for m in METRICS})
    content_failure = LLMProviderError("refused", failure_class="content")
    # Pipelines run concurrently; whichever pipeline calls first gets the ok turn.
    service, _ = _service(gateway, [_all_three_turn(), content_failure])
    state = await service.run_specific_metric_resolution(_state(["p1", "p2"]))
    outcomes = sorted(r.outcome for r in state.phase1_results.values())
    assert outcomes == ["completed", "resolution_call_failed"]
    failed = next(r for r in state.phase1_results.values() if r.outcome != "completed")
    assert (failed.phase1, failed.failed_cause) == (None, "content")


async def test_entry_all_provider_failures_raise_and_breaker_skips_later_amenities():
    timeout = LLMProviderError("timed out", failure_class="availability")
    gateway = FakeGateway()
    service, provider = _service(gateway, [timeout] * 10, threshold=2)
    state = _state(["p1", "p2", "p3", "p4", "p5", "p6"])
    with pytest.raises(MetricResolutionProviderError) as exc:
        await service.run_specific_metric_resolution(state)
    assert exc.value.cause == "circuit_open"
    records = state.phase1_results.values()
    assert len(records) == 6 and all(r.outcome == "resolution_call_failed" for r in records)
    assert {r.failed_cause for r in records} >= {"availability", "circuit_open"}
    # Once open, later pipelines never reach the provider (at most 4 in flight hit it before).
    assert len(provider.sent_histories) < 6
    assert gateway.search_calls == [] and gateway.closed


async def test_sweep_turns_an_exception_slot_into_pipeline_error():
    service, _ = _service(FakeGateway(), [])
    work_items = [_work_item("p1"), _work_item("p2")]
    ok_record = await service._run_amenity_pipeline(
        work_items[0], None, WEBSITE, CATALOG, _CircuitBreaker(threshold=3), "run"
    )  # missing record -> pipeline_error by precondition
    records = service._sweep_pipeline_results(
        work_items, [ok_record, RuntimeError("bug")], _CircuitBreaker(threshold=3), "run"
    )
    assert records[(1, "p1")].outcome == "pipeline_error"
    assert records[(1, "p2")].outcome == "pipeline_error"
    # Crashes alone are not provider failures: no run-level raise.
    service._raise_if_no_pipeline_completed(records, _CircuitBreaker(threshold=3))
