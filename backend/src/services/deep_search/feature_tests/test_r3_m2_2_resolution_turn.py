"""R3.M2.2 — Run the resolution turn and validate the body: behavior suite.

No live calls. Fakes stand in ONLY for the non-deterministic edges: the LLM provider (queued
phase-1 turns, queued structured bodies or provider errors; every resolution user turn it receives
is recorded) and the MCP gateway (`search_web` outcomes keyed by objective). Everything the app
decides runs for real: the shared `StructuredLLMCaller` and its `cause` aggregation, the R3.M2.1
schema / instruction / renderer, the breaker, the reviews item, the skip rule, label coverage, the
follow-up policy, the pipeline catch and the STEP 5 sweep.

Each test asserts an observable outcome: the record (kept / unresolved / calls / outcome), the user
turns the provider received, the evidence store, the breaker state, or a structured log line.
"""

import json
import logging

import pytest

from src.clients.llm_provider import AssistantTurn, StructuredLLMCaller, ToolCall
from src.clients.mcp_tools import RawToolDefinition, SearchExcerpt, WebSearchResult
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import MetricResolutionProviderError
from src.exceptions.llm import LLMProviderError
from src.services.deep_search import specific_metric_resolution as smr
from src.services.deep_search.feature_schemas.schemas import (
    SpecificMetricResolutionState,
    CanonicalPlace,
    CategoryMetricPlan,
    MetricResolutionSource,
    MetricsSourceContent,
    MetricSpec,
    Phase1Result,
    PredefinedMetricsRecord,
    WebsiteSearchResult,
)
from src.services.deep_search.phase_tool_catalog import build_tool_catalog
from src.services.deep_search.specific_metric_resolution import (
    RESOLUTION_FOLLOWUP_STAGE,
    RESOLUTION_STAGE,
    SpecificMetricResolution,
    _CircuitBreaker,
    _DiscoveryWorkItem,
    _record_review_evidence,
    _shape_reviews_text,
)

# --------------------------------------------------------------------------------------------------
# Edge fakes.
# --------------------------------------------------------------------------------------------------
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
RETRIEVED_AT = "2026-11-01T09:00:00+00:00"


class FakeProvider:
    """Pops queued phase-1 turns and structured bodies (or raises queued errors)."""

    name = "openai"
    model = "fake-model"

    def __init__(self, *, turns=None, bodies=None) -> None:
        self._turns = list(turns or [])
        self._bodies = list(bodies or [])
        self.user_turns: list[dict] = []  # each resolution user turn, decoded

    async def generate_turn(self, *, messages, tools, tool_choice):
        if not self._turns:
            raise LLMProviderError("no recorded turn left", failure_class="content")
        item = self._turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def generate_structured(self, *, instruction, user_content, json_schema, schema_name):
        assert schema_name == "metric_resolution"
        self.user_turns.append(json.loads(user_content))
        if not self._bodies:
            raise LLMProviderError("no recorded body left", failure_class="content")
        item = self._bodies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self) -> None:
        pass


class FakeGateway:
    """`search_web` outcomes keyed by objective (one per call)."""

    def __init__(self, outcomes: dict | None = None) -> None:
        self._outcomes = {k: list(v) for k, v in (outcomes or {}).items()}

    async def open(self) -> None:
        pass

    def get_tool_definitions(self):
        return RAW_DEFS

    async def search_web(self, objective, search_queries):
        return self._outcomes[objective].pop(0)

    async def aclose(self) -> None:
        pass


def _service(provider: FakeProvider) -> SpecificMetricResolution:
    return SpecificMetricResolution(
        tool_gateway=FakeGateway(),
        llm_caller=StructuredLLMCaller([provider]),
        owns_caller=False,
    )


# --------------------------------------------------------------------------------------------------
# Domain builders (a fresh venue; not any prompt worked example or runner seed).
# --------------------------------------------------------------------------------------------------
def _metric(label: str, evidence_class: str = "factual") -> MetricSpec:
    source = (
        MetricResolutionSource(web_target=f"{label} info", scrape_target=f"{label} page")
        if evidence_class == "factual"
        else MetricResolutionSource(web_target=f"{label} reviews", review_target="visitor talk")
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


METRICS = [_metric("has_parking"), _metric("sells_rye"), _metric("queue_noise", "experiential")]
LABELS = [m.label for m in METRICS]
WEBSITE = WebsiteSearchResult("https://quarryhillbakery.com", "google")


def _review(text=None, rating=None, original=None, author="Pat Example") -> dict:
    review: dict = {
        "name": "places/x/reviews/y",
        "relative_publish_time_description": "a month ago",
        "author_attribution": {"display_name": author, "uri": "https://maps.example/u"},
        "publish_time": "2026-09-01T10:00:00Z",
    }
    if rating is not None:
        review["rating"] = rating
    if text is not None:
        review["text"] = {"text": text, "language_code": "en"}
    if original is not None:
        review["original_text"] = {"text": original, "language_code": "en"}
    return review


def _rec(place_id: str = "p1", reviews=None) -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=1,
        taxonomy_node="bakery",
        depth="specific_attributes",
        place_id=place_id,
        name="Quarry Hill Bakery",
        category=None,
        address="9 Quarry Hill, Millbrook 40411",
        website="https://quarryhillbakery.com",
        google_maps_uri=None,
        coordinates=None,
        opening_hours=None,
        contact_phone=None,
        rating=None,
        review_volume=None,
        price_level=None,
        reviews=reviews,
        routing={},
        transit=None,
    )


def _work_item(place_id: str = "p1", metrics=None) -> _DiscoveryWorkItem:
    return _DiscoveryWorkItem(1, place_id, "bakery", "specific_attributes", metrics or METRICS)


def _store(labels_with_evidence) -> MetricsSourceContent:
    store = MetricsSourceContent()
    for label in labels_with_evidence:
        store.record("web", f"https://guide.example/{label}", f"Guide\n{label} line", RETRIEVED_AT, label)
    return store


def _phase1(store: MetricsSourceContent) -> Phase1Result:
    return Phase1Result(
        messages=[], metrics_source_content=store, metric_outcomes={}, uncovered_labels=(),
        turns_run=1,
    )


def _entry(label: str) -> dict:
    return {
        "metric_label": label,
        "web_value": "yes",
        "scrape_value": None,
        "reviews_value": None,
        "relation": "none",
        "verification_met": True,
        "final_value": True,
        "opinion_mixed": False,
        "basis": "web",
        "evidence": [{"source": "web", "url": f"https://guide.example/{label}", "quote": "line"}],
    }


def _body(*labels: str) -> dict:
    return {"metrics": [_entry(label) for label in labels]}


async def _resolve(service, store, *, rec=None, breaker=None, metrics=None):
    return await service._resolve_amenity(
        _work_item(metrics=metrics), rec or _rec(), WEBSITE, _phase1(store),
        breaker or _CircuitBreaker(threshold=3), "run",
    )


def _assert_partition(record, labels=LABELS) -> None:
    """Every submitted label is in exactly one of kept / unresolved."""
    assert not set(record.kept) & set(record.unresolved)
    assert set(record.kept) | set(record.unresolved) == set(labels)


def _events(caplog, name: str) -> list[dict]:
    out = []
    for rec in caplog.records:
        try:
            payload = json.loads(rec.getMessage())
        except ValueError:
            continue
        if payload.get("event") == name:
            out.append(payload)
    return out


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.DEBUG, logger=DEEP_SEARCH_LOGGER_NAME)
    return caplog


# --------------------------------------------------------------------------------------------------
# Step 1: the reviews item.
# --------------------------------------------------------------------------------------------------
def test_reviews_block_numbers_written_reviews_with_whole_star_ratings_and_fallback():
    reviews = [
        _review("Crusty loaves 🍞\n\nLong queue at 8am.", rating=4.0),
        _review(rating=5.0),  # rating-only: skipped, not numbered
        _review("Friendly staff.", rating=None),  # no rating: no star
        _review(original="Brot war frisch.", rating=3.0),  # only original_text
    ]
    text, count = _shape_reviews_text(reviews)
    assert count == 3
    assert text == (
        "Review 1 (★4): Crusty loaves 🍞\n\nLong queue at 8am."
        "\n\nReview 2: Friendly staff."
        "\n\nReview 3 (★3): Brot war frisch."
    )
    assert "Pat Example" not in text and "2026-09-01" not in text and "maps.example" not in text


@pytest.mark.parametrize("reviews", [None, [], [_review(rating=5.0), _review("   ", rating=2.0)]])
def test_no_reviews_item_when_nothing_to_quote(reviews):
    store = _store(["has_parking"])
    assert _record_review_evidence(_rec(reviews=reviews), store, RETRIEVED_AT) == 0
    assert [i.source_kind for i in store.items] == ["web"]


def test_reviews_item_is_unlinked_and_in_no_metric_bucket():
    store = _store(["has_parking"])
    _record_review_evidence(_rec(reviews=[_review("Good rye.", rating=5)]), store, RETRIEVED_AT)
    item = next(i for i in store.items if i.source_kind == "google_reviews")
    assert (item.url, item.metric_labels, item.retrieved_at) == (None, set(), RETRIEVED_AT)
    assert all(item not in store.items_for(label) for label in LABELS)


# --------------------------------------------------------------------------------------------------
# Step 2: the skip rule.
# --------------------------------------------------------------------------------------------------
async def test_skip_rule_no_evidence_no_reviews_makes_no_call():
    provider = FakeProvider()
    record = await _resolve(_service(provider), MetricsSourceContent())
    assert provider.user_turns == []
    assert (record.outcome, record.resolution_calls, record.kept) == ("completed", 0, {})
    assert record.unresolved == {label: "no_evidence" for label in LABELS}


async def test_reviews_alone_are_enough_to_send_the_call():
    provider = FakeProvider(bodies=[_body(*LABELS)])
    rec = _rec(reviews=[_review("Always a queue.", rating=3)])
    record = await _resolve(_service(provider), MetricsSourceContent(), rec=rec)
    assert len(provider.user_turns) == 1 and record.resolution_calls == 1
    assert provider.user_turns[0]["google_reviews"] == {"text": "Review 1 (★3): Always a queue."}


async def test_one_metric_bucket_is_enough_to_send_the_call():
    provider = FakeProvider(bodies=[_body(*LABELS)])
    await _resolve(_service(provider), _store(["sells_rye"]))
    assert len(provider.user_turns) == 1


# --------------------------------------------------------------------------------------------------
# Steps 3-4: call 1, label coverage, follow-up.
# --------------------------------------------------------------------------------------------------
async def test_complete_body_is_kept_in_one_call_with_every_metric_and_reviews_once(logs):
    provider = FakeProvider(bodies=[_body(*reversed(LABELS))])
    rec = _rec(reviews=[_review("Fresh.", rating=5)])
    record = await _resolve(_service(provider), _store(["has_parking"]), rec=rec)

    assert (record.outcome, record.resolution_calls, record.unresolved) == ("completed", 1, {})
    assert list(record.kept) == LABELS  # plan order, whatever order the body used
    turn = provider.user_turns[0]
    assert [m["label"] for m in turn["metrics"]] == LABELS
    assert turn["google_reviews"]["text"] == "Review 1 (★5): Fresh."
    validated = _events(logs, "metric_resolution.validated")
    assert validated == [validated[0]] and validated[0]["stage"] == RESOLUTION_STAGE
    assert (validated[0]["kept"], validated[0]["missing"]) == (3, 0)


async def test_extra_label_is_dropped_and_rest_kept_without_follow_up(logs):
    provider = FakeProvider(bodies=[_body(*LABELS, "made_up_label")])
    record = await _resolve(_service(provider), _store(LABELS))
    assert list(record.kept) == LABELS and record.resolution_calls == 1
    assert "made_up_label" not in record.kept and "made_up_label" not in record.unresolved
    assert _events(logs, "metric_resolution.extra_label_dropped")[0]["labels"] == ["made_up_label"]


async def test_duplicate_label_drops_all_copies_and_follow_up_asks_only_for_it(logs):
    provider = FakeProvider(bodies=[_body("has_parking", "sells_rye", "sells_rye", "queue_noise"),
                                    _body("sells_rye")])
    record = await _resolve(_service(provider), _store(LABELS))

    assert [m["label"] for m in provider.user_turns[1]["metrics"]] == ["sells_rye"]
    assert list(record.kept) == LABELS and record.resolution_calls == 2
    assert _events(logs, "metric_resolution.duplicate_label")[0]["labels"] == ["sells_rye"]
    assert _events(logs, "metric_resolution.missing_label_retry")[0]["labels"] == ["sells_rye"]
    _assert_partition(record)


async def test_label_still_missing_after_follow_up_is_body_invalid_and_no_third_call(logs):
    provider = FakeProvider(bodies=[_body("has_parking"), _body("sells_rye"), _body("queue_noise")])
    record = await _resolve(_service(provider), _store(LABELS))

    assert len(provider.user_turns) == 2 and record.resolution_calls == 2
    assert list(record.kept) == ["has_parking", "sells_rye"]
    assert record.unresolved == {"queue_noise": "resolution_body_invalid"}
    assert _events(logs, "metric_resolution.rejected")[0]["labels"] == ["queue_noise"]
    stages = [e["stage"] for e in _events(logs, "metric_resolution.validated")]
    assert stages == [RESOLUTION_STAGE, RESOLUTION_FOLLOWUP_STAGE]


async def test_follow_up_never_overwrites_a_kept_entry():
    overwrite = _entry("has_parking") | {"final_value": False, "web_value": "no"}
    provider = FakeProvider(bodies=[_body("has_parking", "sells_rye"),
                                    {"metrics": [overwrite, _entry("queue_noise")]}])
    record = await _resolve(_service(provider), _store(LABELS))
    assert record.kept["has_parking"].final_value is True
    assert set(record.kept) == set(LABELS) and record.unresolved == {}


async def test_follow_up_skipped_when_missing_metrics_have_no_evidence_and_no_reviews():
    provider = FakeProvider(bodies=[_body("has_parking", "sells_rye")])
    record = await _resolve(_service(provider), _store(["has_parking", "sells_rye"]))
    assert len(provider.user_turns) == 1 and record.resolution_calls == 1
    assert record.unresolved == {"queue_noise": "no_evidence"}


async def test_follow_up_user_turn_still_carries_the_shared_reviews():
    provider = FakeProvider(bodies=[_body("has_parking", "sells_rye"), _body("queue_noise")])
    rec = _rec(reviews=[_review("Loud queue.", rating=2)])
    record = await _resolve(_service(provider), _store(["has_parking"]), rec=rec)
    follow_up = provider.user_turns[1]
    assert [m["label"] for m in follow_up["metrics"]] == ["queue_noise"]
    assert follow_up["metrics"][0]["evidence"] == []
    assert follow_up["google_reviews"]["text"] == "Review 1 (★2): Loud queue."
    assert set(record.kept) == set(LABELS)


async def test_each_call_logs_the_rendered_evidence_per_metric_bucket(logs):
    """The DEBUG `input_rendered` line records exactly what each call sent: one bucket per metric
    with its formatted items (text verbatim from the store), and the shared reviews block."""
    provider = FakeProvider(bodies=[_body("has_parking", "sells_rye"), _body("queue_noise")])
    rec = _rec(reviews=[_review("Loud queue at 8am.", rating=2)])
    store = _store(["has_parking", "queue_noise"])
    await _resolve(_service(provider), store, rec=rec)

    first, second = _events(logs, "metric_resolution.input_rendered")
    assert (first["stage"], second["stage"]) == (RESOLUTION_STAGE, RESOLUTION_FOLLOWUP_STAGE)
    assert [b["label"] for b in first["buckets"]] == LABELS
    assert [b["label"] for b in second["buckets"]] == ["queue_noise"]
    parking = first["buckets"][0]
    assert parking["evidence_items"] == 1
    assert parking["evidence"] == [{
        "source": "web",
        "url": "https://guide.example/has_parking",
        "text": store.items_for("has_parking")[0].shaped_text,
    }]
    assert first["buckets"][1]["evidence"] == []  # an empty bucket is logged as sent
    assert first["google_reviews"] == {"text": "Review 1 (★2): Loud queue at 8am."}
    assert second["google_reviews"] == first["google_reviews"]
    assert first["amenity"]["website_url"] == WEBSITE.website_url
    # It is the same payload the provider received, not a re-derivation.
    assert [m["evidence"] for m in provider.user_turns[0]["metrics"]] == [
        b["evidence"] for b in first["buckets"]
    ]


async def test_no_rendered_evidence_line_when_the_breaker_stops_the_call(logs):
    provider = FakeProvider(bodies=[_body(*LABELS)])
    with pytest.raises(MetricResolutionProviderError):
        await _resolve(_service(provider), _store(LABELS),
                       breaker=_CircuitBreaker(threshold=1, open=True))
    assert _events(logs, "metric_resolution.input_rendered") == []


# --------------------------------------------------------------------------------------------------
# Failures and the breaker.
# --------------------------------------------------------------------------------------------------
def _phase1_turn(prefix: str = "t") -> AssistantTurn:
    calls = [
        ToolCall(
            id=f"{prefix}{i}",
            name="web_search",
            arguments=json.dumps(
                {"objective": f"obj {label}", "search_queries": ["q"], "metric_label": label}
            ),
        )
        for i, label in enumerate(LABELS)
    ]
    return AssistantTurn(
        provider="openai",
        finish_reason="tool_calls",
        content=None,
        tool_calls=tuple(calls),
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": c.arguments}}
                for c in calls
            ],
        },
    )


def _ok(objective: str) -> WebSearchResult:
    hit = SearchExcerpt(url=f"https://guide.example/{objective}", title="T", text="t")
    return WebSearchResult(objective, ("q",), (hit,), RETRIEVED_AT)


def _gateway(amenities: int = 1) -> FakeGateway:
    return FakeGateway({f"obj {label}": [_ok(f"obj {label}")] * amenities for label in LABELS})


def _pipeline_service(provider, amenities: int = 1, threshold: int = 3):
    return SpecificMetricResolution(
        tool_gateway=_gateway(amenities),
        llm_caller=StructuredLLMCaller([provider]),
        owns_caller=False,
        breaker_threshold=threshold,
    )


async def test_first_call_provider_error_ends_the_amenity_and_discards_evidence():
    provider = FakeProvider(
        turns=[_phase1_turn()],
        bodies=[LLMProviderError("timed out", failure_class="availability")],
    )
    breaker = _CircuitBreaker(threshold=3)
    record = await _pipeline_service(provider)._run_amenity_pipeline(
        _work_item(), _rec(), WEBSITE, CATALOG, breaker, "run"
    )
    assert record.outcome == "resolution_call_failed" and record.phase1 is None
    assert (record.failed_stage, record.failed_cause) == (RESOLUTION_STAGE, "availability")
    assert record.unresolved == {label: "resolution_call_failed" for label in LABELS}
    assert record.resolution_calls == 1 and breaker.counter == 1


async def test_unparseable_first_body_is_a_content_failure_that_does_not_count(logs):
    provider = FakeProvider(turns=[_phase1_turn()], bodies=[{"metrics": [{"metric_label": "x"}]}])
    breaker = _CircuitBreaker(threshold=1)
    record = await _pipeline_service(provider)._run_amenity_pipeline(
        _work_item(), _rec(), WEBSITE, CATALOG, breaker, "run"
    )
    assert (record.outcome, record.failed_cause) == ("resolution_call_failed", "content")
    assert (breaker.counter, breaker.open) == (0, False)
    unparseable = _events(logs, "metric_resolution.body_unparseable")
    assert unparseable[0]["stage"] == RESOLUTION_STAGE and unparseable[0]["error_count"] > 0


async def test_follow_up_provider_error_fails_only_its_labels(logs):
    provider = FakeProvider(bodies=[_body("has_parking"),
                                    LLMProviderError("timed out", failure_class="availability")])
    breaker = _CircuitBreaker(threshold=3)
    record = await _resolve(_service(provider), _store(LABELS), breaker=breaker)

    assert record.outcome == "completed" and record.phase1 is not None
    assert list(record.kept) == ["has_parking"]
    assert record.unresolved == {"sells_rye": "resolution_call_failed",
                                 "queue_noise": "resolution_call_failed"}
    assert record.resolution_calls == 2 and breaker.counter == 1
    failed = _events(logs, "metric_resolution.followup_failed")[0]
    assert (failed["stage"], failed["cause"]) == (RESOLUTION_FOLLOWUP_STAGE, "availability")


async def test_open_breaker_stops_the_first_call_before_the_provider():
    provider = FakeProvider(turns=[_phase1_turn()], bodies=[_body(*LABELS)])
    service = _pipeline_service(provider)
    with pytest.raises(MetricResolutionProviderError) as exc:
        await _resolve(service, _store(LABELS), breaker=_CircuitBreaker(threshold=1, open=True))
    assert (exc.value.stage, exc.value.cause) == (RESOLUTION_STAGE, "circuit_open")
    assert provider.user_turns == []


async def test_open_breaker_before_follow_up_keeps_kept_entries_and_counts_no_call():
    provider = FakeProvider(bodies=[_body("has_parking")])
    service = _service(provider)
    breaker = _CircuitBreaker(threshold=1)
    original = service._run_resolution_call

    async def _open_then_call(*args, **kwargs):  # the outage trips between call 1 and call 2
        if args[4] == RESOLUTION_FOLLOWUP_STAGE:
            breaker.open = True
        return await original(*args, **kwargs)

    service._run_resolution_call = _open_then_call
    record = await _resolve(service, _store(LABELS), breaker=breaker)
    assert list(record.kept) == ["has_parking"] and record.resolution_calls == 1
    assert set(record.unresolved.values()) == {"resolution_call_failed"}


async def test_label_coverage_problems_never_move_the_breaker():
    provider = FakeProvider(bodies=[_body("has_parking", "bogus"), _body("bogus")])
    breaker = _CircuitBreaker(threshold=1)
    record = await _resolve(_service(provider), _store(LABELS), breaker=breaker)
    assert (breaker.counter, breaker.open) == (0, False)
    assert set(record.unresolved.values()) == {"resolution_body_invalid"}


# --------------------------------------------------------------------------------------------------
# STEP 4/5 through the real entry point.
# --------------------------------------------------------------------------------------------------
@pytest.fixture
def one_pipeline_at_a_time(monkeypatch):
    """Sequential pipelines so the shared provider queues are consumed in a known order."""
    monkeypatch.setattr(smr, "AMENITY_PIPELINE_CONCURRENCY", 1)


def _state(place_ids) -> SpecificMetricResolutionState:
    plan = CategoryMetricPlan(1, "bakery", "specific_attributes", [], METRICS)
    return SpecificMetricResolutionState(
        category_metric_plans=[plan],
        discovered_places={1: {pid: CanonicalPlace(pid, {}) for pid in place_ids}},
        predefined_records={1: {pid: _rec(pid) for pid in place_ids}},
    )


async def test_entry_writes_one_record_per_amenity_and_one_failure_does_not_raise(
    one_pipeline_at_a_time,
):
    provider = FakeProvider(
        turns=[_phase1_turn("a"), _phase1_turn("b")],
        bodies=[_body(*LABELS), LLMProviderError("refused", failure_class="content")],
    )
    state = await _pipeline_service(provider, amenities=2).run_specific_metric_resolution(
        _state(["p1", "p2"])
    )
    first, second = state.resolution_results[(1, "p1")], state.resolution_results[(1, "p2")]
    assert (first.outcome, second.outcome) == ("completed", "resolution_call_failed")
    assert second.failed_stage == RESOLUTION_STAGE
    for record in (first, second):
        _assert_partition(record)


async def test_entry_raises_when_every_first_call_fails(one_pipeline_at_a_time):
    refusal = LLMProviderError("refused", failure_class="content")
    provider = FakeProvider(
        turns=[_phase1_turn("a"), _phase1_turn("b")], bodies=[refusal, refusal]
    )
    state = _state(["p1", "p2"])
    with pytest.raises(MetricResolutionProviderError) as exc:
        await _pipeline_service(provider, amenities=2).run_specific_metric_resolution(state)
    assert exc.value.cause == "content"
    assert {r.outcome for r in state.resolution_results.values()} == {"resolution_call_failed"}


def test_sweep_turns_a_crashed_pipeline_into_pipeline_error_with_every_label_failed():
    service = _service(FakeProvider())
    records = service._sweep_pipeline_results(
        [_work_item("p1")], [RuntimeError("bug")], _CircuitBreaker(threshold=3), "run"
    )
    record = records[(1, "p1")]
    assert (record.outcome, record.phase1, record.kept) == ("pipeline_error", None, {})
    assert record.unresolved == {label: "resolution_call_failed" for label in LABELS}
