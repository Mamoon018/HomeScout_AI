"""Fixture set for R3 as an independent service (R3-C2 to R3-C9). No live calls, no database.

- The REAL `SpecificMetricResolution` runs through the coordinator's factory on a `FakeGateway`
  (every `search_web` answers `ok`) and a `FakeProvider` LLM edge (phase-1 turns that search every
  metric, resolution turns that answer every label). Used for parity, resume and the STEP 5 raise.
- `ScriptedService` is a duck-typed R3 for lifecycle cases: it can hold before STEP 1 behind a
  gate, report a breaker-open STEP 3, wait after the checkpoint, or raise an injected error.
- `FakeR3RunStore` keeps rows in memory and applies the same rules as the SQL (each rule sits next
  to a comment naming the condition it copies). Every payload round-trips through the real codecs
  and JSON, so the coordinator sees what the database would give back.
- `FakeR2Output` stands in for `R2RunStore.get_finished_output`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.app.api.dependencies.deep_search import get_r3_run_coordinator
from src.app.api.dependencies.supabase import get_access_token_verifier
from src.app.main import app
from src.clients.llm_provider import AssistantTurn, StructuredLLMCaller, ToolCall
from src.clients.mcp_tools import RawToolDefinition, SearchExcerpt, WebSearchResult
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import (
    MetricResolutionProviderError,
    MetricResolutionValidationError,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    StateVersionMismatchError,
)
from src.exceptions.llm import LLMProviderError
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError
from src.services.auth.session_cookies import ACCESS_TOKEN_COOKIE_POLICY
from src.services.deep_search.feature_schemas.schemas import (
    AmenityResolutionRecord,
    AmenitySearchOutput,
    CanonicalPlace,
    CategoryMetricPlan,
    MetricResolutionSource,
    MetricSearchOutcome,
    MetricsSourceContent,
    MetricSpec,
    OfficialGateRecord,
    Phase1Result,
    PredefinedMetricsRecord,
    R3RunRecord,
    R3StepRecord,
    SpecificMetricResolutionState,
    WebsiteSearchResult,
)
from src.services.deep_search.r3_run_coordinator import (
    MAX_RETRY_ATTEMPTS,
    R3RunCoordinator,
    is_config_error,
)
from src.services.deep_search.r3_run_store import (
    R3_STATE_SCHEMA_VERSION,
    dump_output,
    dump_resolution_entries,
    dump_state,
    dump_step_output,
    load_output,
    load_state,
    load_step_output,
)
from src.services.deep_search.specific_metric_resolution import SpecificMetricResolution
from tests.conftest import make_access_token_verifier, mint_access_token

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
R2_RUN = "66666666-6666-4666-8666-666666666666"
RETRIEVED_AT = "2026-11-09T10:00:00+00:00"

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


# --------------------------------------------------------------------------- inputs


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


METRICS = [_metric("has_sauna"), _metric("evening_crowding", "experiential")]
LABELS = [m.label for m in METRICS]
WORDS = ["Harbor", "Quarry"]


def _rec(place_id: str, word: str) -> PredefinedMetricsRecord:
    # "<word> Swim Hall" + "<word>swimhall.com": the real gate trusts it (SLD match), so STEP 3
    # makes no LLM call and every LLM call is a STEP 4 call.
    return PredefinedMetricsRecord(
        category_id=1,
        taxonomy_node="swimming_pool",
        depth="specific_attributes",
        place_id=place_id,
        name=f"{word} Swim Hall",
        category=None,
        address=f"9 {word} Road, Lakeside 40101",
        website=f"https://{word.lower()}swimhall.com",
        google_maps_uri=None,
        coordinates=None,
        opening_hours=None,
        contact_phone=None,
        rating=None,
        review_volume=None,
        price_level=2,
        reviews=None,
        routing={},
        transit=None,
    )


def _handoff(words: list[str] = WORDS) -> AmenitySearchOutput:
    plan = CategoryMetricPlan(1, "swimming_pool", "specific_attributes", [], METRICS)
    return AmenitySearchOutput(
        category_metric_plans=[plan],
        discovered_places={1: {w.lower(): CanonicalPlace(w.lower(), {"id": w.lower()}) for w in words}},
        predefined_records={1: {w.lower(): _rec(w.lower(), w) for w in words}},
    )


# --------------------------------------------------------------------------- edge fakes


class FakeProvider:
    """LLM edge: phase-1 turns that search every metric once; resolution turns that answer every
    label as unmet. `fail_turns` makes every phase-1 turn fail with an availability error."""

    name = "openai"
    model = "fake-model"

    def __init__(self) -> None:
        self.fail_turns = False
        self.turns = 0
        self.structured = 0

    async def generate_turn(self, *, messages, tools, tool_choice):
        self.turns += 1
        if self.fail_turns:
            raise LLMProviderError("provider down", failure_class="availability")
        system = messages[0]["content"]
        amenity = next(w for w in WORDS if f"{w} Swim Hall" in system)
        calls = tuple(
            ToolCall(
                id=f"c{i}",
                name="web_search",
                arguments=json.dumps(
                    {
                        "objective": f"{amenity} {label}",
                        "search_queries": [f"{amenity} {label}"],
                        "metric_label": label,
                    }
                ),
            )
            for i, label in enumerate(LABELS)
        )
        return AssistantTurn(
            provider="openai",
            finish_reason="tool_calls",
            content=None,
            tool_calls=calls,
            message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in calls
                ],
            },
        )

    async def generate_structured(self, *, instruction, user_content, json_schema, schema_name):
        self.structured += 1
        payload = json.loads(user_content)
        return {
            "metrics": [
                {
                    "metric_label": metric["label"],
                    "web_value": "yes",
                    "scrape_value": None,
                    "reviews_value": None,
                    "relation": "none",
                    "verification_met": False,
                    "final_value": None,
                    "opinion_mixed": False,
                    "basis": "none",
                    "evidence": [],
                }
                for metric in payload["metrics"]
            ]
        }

    async def aclose(self) -> None:
        pass


class FakeGateway:
    """MCP edge: every `search_web` answers one excerpt derived from the objective."""

    def __init__(self, counter: dict) -> None:
        self._counter = counter
        self.closed = False

    async def open(self) -> None:
        self._counter["opened"] = self._counter.get("opened", 0) + 1

    def get_tool_definitions(self):
        return RAW_DEFS

    async def search_web(self, objective, search_queries):
        self._counter["searches"] = self._counter.get("searches", 0) + 1
        excerpt = SearchExcerpt(
            url=f"https://evidence.example/{objective.replace(' ', '-')}",
            title="Page",
            text=f"Text about {objective}.",
        )
        return WebSearchResult(objective, tuple(search_queries), (excerpt,), RETRIEVED_AT)

    async def aclose(self) -> None:
        self.closed = True


class Script:
    """What every `ScriptedService` built for one coordinator does, in order of executions."""

    def __init__(self) -> None:
        self.gate: asyncio.Event | None = None  # held before STEP 1
        self.after_checkpoint: asyncio.Event | None = None  # held after the STEP 3 callback
        self.waiting = 0
        self.breaker_open: list[bool] = []  # per execution; default False
        self.errors: list[BaseException | None] = []  # per execution, raised in STEP 4
        self.setup_errors: list[BaseException | None] = []  # per execution, raised before STEP 3
        self.executions: list[str | None] = []  # resume_after of each execution
        self.step3_runs = 0
        self.closed = 0


class ScriptedService:
    """Duck-typed R3: same entry signature, scripted STEP 3 / STEP 4 behavior."""

    def __init__(self, script: Script) -> None:
        self._script = script

    async def run_specific_metric_resolution(self, state, *, resume_after=None, on_step_completed=None):
        script = self._script
        index = len(script.executions)
        script.executions.append(resume_after)
        if script.gate is not None:
            script.waiting += 1
            await script.gate.wait()
        setup_error = script.setup_errors[index] if index < len(script.setup_errors) else None
        if setup_error is not None:
            raise setup_error
        if resume_after != "discovery_batch":
            script.step3_runs += 1
            breaker_open = script.breaker_open[index] if index < len(script.breaker_open) else False
            for category_id, places in state.discovered_places.items():
                for place_id in places:
                    origin = "none" if breaker_open else "google"
                    url = None if breaker_open else state.predefined_records[category_id][place_id].website
                    state.website_search_results[(category_id, place_id)] = WebsiteSearchResult(url, origin)
            if on_step_completed is not None:
                await on_step_completed("discovery_batch", state, breaker_open)
            if script.after_checkpoint is not None:
                script.waiting += 1
                await script.after_checkpoint.wait()
        error = script.errors[index] if index < len(script.errors) else None
        if error is not None:
            raise error
        for category_id, places in state.discovered_places.items():
            for place_id in places:
                state.resolution_results[(category_id, place_id)] = AmenityResolutionRecord(
                    category_id=category_id,
                    place_id=place_id,
                    outcome="completed",
                    kept={},
                    unresolved={label: "no_evidence" for label in LABELS},
                    phase1=None,
                )
        return state

    async def aclose(self) -> None:
        self._script.closed += 1


class FakeR2Output:
    """`R2RunStore.get_finished_output` over in-memory finished R2 outputs."""

    def __init__(self) -> None:
        self.finished: dict[tuple[str, str], AmenitySearchOutput] = {}
        self.version_mismatch = False

    async def get_finished_output(self, run_id: str, user_id: str):
        if self.version_mismatch:
            raise StateVersionMismatchError(99, 1)
        return self.finished.get((run_id, user_id))


def _j(value):
    return json.loads(json.dumps(value))


class FakeR3RunStore:
    """In-memory `r3_runs` + `r3_run_steps` with `R3RunStore`'s method names and SQL rules."""

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.steps: dict[str, dict[str, dict]] = {}
        self.step_history: list[tuple[str, str, str]] = []
        self.reads = 0
        self.fail_ops: dict[str, int] = {}  # operation -> remaining failures

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _maybe_fail(self, operation: str) -> None:
        if self.fail_ops.get(operation, 0) > 0:
            self.fail_ops[operation] -= 1
            raise RunStoreError(f"{operation} failed: injected", operation=operation)

    def _fenced(self, run_id, user_id, attempts) -> dict | None:
        # WHERE run_id AND user_id AND status = 'running' AND attempts = <mine>
        row = self.runs.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        if row["status"] != "running" or row["attempts"] != attempts:
            return None
        return row

    def _touch(self, row: dict, **values) -> None:
        row.update(values)
        row["updated_at"] = self._now()  # the updated_at trigger

    async def create_run(self, run_id, user_id, r2_run_id, state) -> None:
        self._maybe_fail("create_run")
        self.runs[run_id] = {
            "run_id": run_id,
            "user_id": user_id,
            "r2_run_id": r2_run_id,
            "status": "running",
            "state": _j(dump_state(state)),
            "completed_step": None,
            "output": None,
            "failure_stage": None,
            "retryable": False,
            "attempts": 0,
            "updated_at": self._now(),
        }
        self.steps[run_id] = {}

    async def save_checkpoint(self, run_id, user_id, *, attempts, state) -> bool:
        self._maybe_fail("save_checkpoint")
        row = self._fenced(run_id, user_id, attempts)
        if row is None:
            return False
        self._touch(row, state=_j(dump_state(state)), completed_step="discovery_batch")
        return True

    async def save_finished(self, run_id, user_id, *, attempts, state, output) -> bool:
        self._maybe_fail("save_finished")
        row = self._fenced(run_id, user_id, attempts)
        if row is None:
            return False
        # CHECK ((status = 'finished') = (output is not null)); the failure fields are cleared.
        self._touch(
            row,
            status="finished",
            state=_j(dump_state(state)),
            output=_j(dump_output(output)),
            retryable=False,
            failure_stage=None,
        )
        return True

    async def save_failed(self, run_id, user_id, *, attempts, stage, message, retryable) -> bool:
        self._maybe_fail("save_failed")
        row = self._fenced(run_id, user_id, attempts)
        if row is None:
            return False
        # state and completed_step are not in the SET list.
        self._touch(row, status="failed", failure_stage=stage, retryable=retryable)
        return True

    async def claim_retry(self, run_id, user_id, *, expected_attempts, stale_before) -> bool:
        self._maybe_fail("claim_retry")
        # WHERE run_id AND user_id AND attempts = n AND ((status = 'failed' AND retryable)
        #   OR (status = 'running' AND updated_at < cutoff))
        row = self.runs.get(run_id)
        if row is None or row["user_id"] != user_id or row["attempts"] != expected_attempts:
            return False
        failed = row["status"] == "failed" and row["retryable"]
        stale = row["status"] == "running" and row["updated_at"] < stale_before
        if not (failed or stale):
            return False
        self._touch(row, status="running", attempts=expected_attempts + 1, retryable=False)
        return True

    async def mark_version_mismatch(self, run_id, user_id) -> None:
        row = self.runs.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] == "finished":
            return
        self._touch(row, status="failed", failure_stage="load_state", retryable=False)

    async def load_run(self, run_id, user_id) -> R3RunRecord | None:
        self.reads += 1
        self._maybe_fail("load_run")
        row = self.runs.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        record = R3RunRecord(
            run_id=run_id,
            user_id=row["user_id"],
            r2_run_id=row["r2_run_id"],
            status=row["status"],
            state=load_state(row["state"]),
            completed_step=row["completed_step"],
            attempts=row["attempts"],
            retryable=row["retryable"],
            updated_at=row["updated_at"].isoformat(),
            output=load_output(row["output"]) if row["output"] is not None else None,
            failure_stage=row["failure_stage"],
            steps={
                step_id: R3StepRecord(
                    step_id=step_id,
                    status=step["status"],
                    error_type=step.get("error_type"),
                    retryable=step.get("retryable"),
                )
                for step_id, step in self.steps[run_id].items()
            },
        )
        # A real read takes the snapshot, then yields while the reply travels back, so two
        # concurrent retries can both read the same failed row before either claims it.
        await asyncio.sleep(0)
        return record

    def _step_row(self, run_id, step_id, expected: tuple[str, ...]) -> dict | None:
        row = self.steps.get(run_id, {}).get(step_id)
        if row is None or row["status"] == "completed":  # completed rows never change (trigger)
            return None
        return row if row["status"] in expected else None

    def _new_row(self, run_id, step_id, values: dict) -> bool:
        if step_id in self.steps[run_id]:  # primary key (run_id, step_id)
            return False
        self.steps[run_id][step_id] = dict(values)
        self.step_history.append((run_id, step_id, values["status"]))
        return True

    async def insert_step(self, run_id, step_id, state) -> bool:
        self._maybe_fail("insert_step")
        return self._new_row(
            run_id, step_id, {"status": "completed", "output": _j(dump_step_output(step_id, state))}
        )

    async def complete_claimed_step(self, run_id, step_id, state) -> bool:
        row = self._step_row(run_id, step_id, ("started",))
        if row is None:
            return False
        row.update(status="completed", output=_j(dump_step_output(step_id, state)))
        self.step_history.append((run_id, step_id, "completed"))
        return True

    async def save_step_degraded(self, run_id, step_id, state, *, claimed) -> bool:
        # CHECK ((status in ('completed', 'degraded')) = (output is not null))
        values = {"status": "degraded", "output": _j(dump_step_output(step_id, state))}
        if claimed:
            row = self._step_row(run_id, step_id, ("started",))
            if row is None:
                return False
            row.update(values)
            self.step_history.append((run_id, step_id, "degraded"))
            return True
        return self._new_row(run_id, step_id, values)

    async def save_step_failed(
        self, run_id, step_id, *, error_type, message, retryable, claimed
    ) -> bool:
        values = {"status": "failed", "output": None, "error_type": error_type, "retryable": retryable}
        if claimed:
            row = self._step_row(run_id, step_id, ("started",))
            if row is None:
                return False
            row.update(values)
            self.step_history.append((run_id, step_id, "failed"))
            return True
        return self._new_row(run_id, step_id, values)

    async def claim_step(self, run_id, step_id) -> bool:
        # WHERE run_id AND step_id AND status IN ('failed', 'degraded'); output and error cleared.
        row = self._step_row(run_id, step_id, ("failed", "degraded"))
        if row is None:
            return False
        row.update(status="started", output=None, error_type=None, retryable=None)
        self.step_history.append((run_id, step_id, "started"))
        return True


# --------------------------------------------------------------------------- helpers


def _scripted_setup(script: Script | None = None, store: FakeR3RunStore | None = None):
    script = script or Script()
    store = store or FakeR3RunStore()
    r2 = FakeR2Output()
    r2.finished[(R2_RUN, USER_A)] = _handoff()
    coordinator = R3RunCoordinator(
        store, r2, service_factory=lambda: ScriptedService(script), stale_after_seconds=1800
    )
    return coordinator, script, store, r2


def _real_setup(provider: FakeProvider | None = None, store: FakeR3RunStore | None = None):
    provider = provider or FakeProvider()
    store = store or FakeR3RunStore()
    counter: dict = {}
    r2 = FakeR2Output()
    r2.finished[(R2_RUN, USER_A)] = _handoff()

    def factory() -> SpecificMetricResolution:
        return SpecificMetricResolution(
            tool_gateway=FakeGateway(counter),
            llm_caller=StructuredLLMCaller([provider]),
            owns_caller=False,
            breaker_threshold=3,
        )

    coordinator = R3RunCoordinator(store, r2, service_factory=factory, stale_after_seconds=1800)
    return coordinator, provider, store, counter


async def _drain(coordinator: R3RunCoordinator) -> None:
    """Wait until every background task has ended and been removed from the task dict."""
    for _ in range(100):
        tasks = [live.task for live in coordinator.tasks.values()]
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)
    raise AssertionError("background tasks did not finish")


async def _start(coordinator: R3RunCoordinator, user: str = USER_A) -> str:
    view = await coordinator.start_run(user, R2_RUN)
    await _drain(coordinator)
    return view.run_id


def _strip_ids(value):
    """Drop the per-run random evidence ids, so two runs over the same responses compare equal."""
    if isinstance(value, dict):
        return {k: _strip_ids(v) for k, v in value.items() if k != "evidence_id"}
    if isinstance(value, list):
        return [_strip_ids(v) for v in value]
    return value


def _fingerprint(state_json: dict) -> str:
    return json.dumps(_strip_ids(state_json), sort_keys=True)


@pytest.fixture
def step3_counter(monkeypatch):
    """Count real STEP 3 executions without changing the method."""
    calls = {"step3": 0}
    original = SpecificMetricResolution._run_discovery_batch

    async def counted(self, *args, **kwargs):
        calls["step3"] += 1
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(SpecificMetricResolution, "_run_discovery_batch", counted)
    return calls


@pytest.fixture
def deep_search_caplog(caplog):
    """Capture homescout.deep_search lines despite the logger's propagate=False handler."""
    deep_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    previous = deep_logger.propagate
    deep_logger.propagate = True
    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        yield caplog
    deep_logger.propagate = previous


def _events(caplog, name: str) -> list[dict]:
    found = []
    for record in caplog.records:
        try:
            body = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if body.get("event") == name:
            found.append(body)
    return found


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _HTTPStatusError(Exception):
    """Shaped like an httpx status error: the status sits on `response.status_code`."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.response = _Resp(status_code)


def _connection_error(cause: BaseException) -> McpConnectionError:
    """An `McpConnectionError` raised `from` the cause, as the gateway raises it."""
    try:
        raise McpConnectionError("could not open MCP session for server 'firecrawl'") from cause
    except McpConnectionError as exc:
        return exc


# --------------------------------------------------------------------------- parity and resume (real R3)


async def test_default_call_matches_a_coordinator_run(step3_counter) -> None:
    coordinator, provider, store, _ = _real_setup()
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert row["status"] == "finished" and row["completed_step"] == "discovery_batch"

    direct = SpecificMetricResolution(
        tool_gateway=FakeGateway({}), llm_caller=StructuredLLMCaller([provider]), owns_caller=False
    )
    plan_state = SpecificMetricResolutionState(
        category_metric_plans=_handoff().category_metric_plans,
        discovered_places=_handoff().discovered_places,
        predefined_records=_handoff().predefined_records,
    )
    await direct.run_specific_metric_resolution(plan_state)  # no new arguments: today's call
    assert _fingerprint(row["state"]) == _fingerprint(_j(dump_state(plan_state)))
    assert {r["value"]["outcome"] for r in row["output"]["output"]} == {"completed"}


async def test_resume_after_a_step4_failure_skips_step3_and_matches_a_clean_run(step3_counter) -> None:
    clean_coordinator, _, clean_store, _ = _real_setup()
    clean_run = await _start(clean_coordinator)
    step3_clean = step3_counter["step3"]

    provider = FakeProvider()
    provider.fail_turns = True  # every phase-1 turn fails: no pipeline completes, run-level raise
    coordinator, _, store, counter = _real_setup(provider)
    run_id = await _start(coordinator)
    failed = store.runs[run_id]
    assert (failed["status"], failed["retryable"]) == ("failed", True)
    assert failed["completed_step"] == "discovery_batch"
    assert failed["failure_stage"] == "run_specific_metric_resolution"
    # A STEP 5 raise leaves no completed `pipelines` row (it waits for the finish write).
    assert store.steps[run_id]["discovery_batch"]["status"] == "completed"
    assert store.steps[run_id]["pipelines"]["status"] == "failed"

    provider.fail_turns = False
    view = await coordinator.retry_run(USER_A, run_id)
    assert view.completed_step == "discovery_batch"
    await _drain(coordinator)
    row = store.runs[run_id]
    assert row["status"] == "finished"
    assert _fingerprint(row["state"]) == _fingerprint(clean_store.runs[clean_run]["state"])
    # STEP 3 ran once for the failed run and was NOT rerun by the retry.
    assert step3_counter["step3"] - step3_clean == 1
    assert store.steps[run_id]["pipelines"]["status"] == "completed"
    assert counter["opened"] == 2  # one fresh gateway per execution (R3-C2)


async def test_save_as_failed_never_touches_state_or_checkpoint() -> None:
    script = Script()
    script.errors = [MetricResolutionProviderError("down", stage="r3_m1_4", cause="availability")]
    coordinator, _, store, _ = _scripted_setup(script)
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    checkpoint = load_state(row["state"])
    assert row["status"] == "failed" and row["completed_step"] == "discovery_batch"
    assert len(checkpoint.website_search_results) == 2 and checkpoint.resolution_results == {}


# --------------------------------------------------------------------------- R3-C3 degraded STEP 3


async def test_breaker_open_at_step3_is_not_a_checkpoint_and_is_kept_as_degraded(
    deep_search_caplog,
) -> None:
    script = Script()
    script.breaker_open = [True, False]
    script.errors = [
        MetricResolutionProviderError("breaker", stage="run_specific_metric_resolution", cause="circuit_open"),
        None,
    ]
    coordinator, _, store, _ = _scripted_setup(script)
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert (row["status"], row["retryable"], row["completed_step"]) == ("failed", True, None)
    degraded = store.steps[run_id]["discovery_batch"]
    assert degraded["status"] == "degraded"
    kept = load_step_output("discovery_batch", degraded["output"])
    assert {v.website_origin for v in kept["website_search_results"].values()} == {"none"}
    assert store.steps[run_id]["pipelines"]["status"] == "failed"
    assert len(_events(deep_search_caplog, "r3_run.step3_degraded")) == 1

    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert script.executions == [None, None]  # completed_step was null: STEP 3 runs again
    assert script.step3_runs == 2
    assert store.runs[run_id]["status"] == "finished"
    assert store.steps[run_id]["discovery_batch"]["status"] == "completed"
    assert store.steps[run_id]["pipelines"]["status"] == "completed"
    history = [(step, status) for _, step, status in store.step_history]
    assert history == [
        ("pipelines", "failed"),
        ("discovery_batch", "degraded"),
        ("discovery_batch", "started"),
        ("pipelines", "started"),
        ("discovery_batch", "completed"),
        ("pipelines", "completed"),
    ]


# --------------------------------------------------------------------------- R3-C4 round trip


def _record_with_evidence(place_id: str) -> AmenityResolutionRecord:
    content = MetricsSourceContent()
    content.record("web", "https://a.example/x", "text one", RETRIEVED_AT, "has_sauna")
    content.record("web", "https://a.example/x", "text one", RETRIEVED_AT, "evening_crowding")
    content.record("google_reviews", None, "Review 1 (★4): fine", RETRIEVED_AT, None)
    phase1 = Phase1Result(
        messages=[{"role": "user", "content": "q"}],
        metrics_source_content=content,
        metric_outcomes={"has_sauna": MetricSearchOutcome("has_sauna", "ok", 1)},
        uncovered_labels=(),
        turns_run=1,
    )
    return AmenityResolutionRecord(
        category_id=1,
        place_id=place_id,
        outcome="completed",
        kept={},
        unresolved={"has_sauna": "no_evidence"},
        phase1=phase1,
        resolution_calls=1,
    )


def test_states_round_trip_with_comma_place_ids_and_rebuilt_evidence_index() -> None:
    handoff = _handoff()
    initial = SpecificMetricResolutionState(
        category_metric_plans=handoff.category_metric_plans,
        discovered_places=handoff.discovered_places,
        predefined_records=handoff.predefined_records,
    )
    key = (1, "pl,ace,1")
    after_step3 = SpecificMetricResolutionState(
        category_metric_plans=handoff.category_metric_plans,
        website_search_results={key: WebsiteSearchResult("https://x.example", "google"), (1, "b"): WebsiteSearchResult(None, "none")},
        official_gate_results={key: OfficialGateRecord(
            "X", "https://x.example", "x.example", "x.example", "x", "example", "x", "x", "official", "sld_match"
        )},
    )
    finished = SpecificMetricResolutionState(
        category_metric_plans=handoff.category_metric_plans,
        resolution_results={key: _record_with_evidence(key[1])},
    )
    for state in (initial, after_step3, finished):
        back = load_state(_j(dump_state(state)))
        assert back == state
    assert list(load_state(_j(dump_state(after_step3))).website_search_results) == [key, (1, "b")]
    content = load_state(_j(dump_state(finished))).resolution_results[key].phase1.metrics_source_content
    assert content._index[("web", "https://a.example/x", "text one")] is content.items[0]
    assert content.items_for("evening_crowding") == (content.items[0],)
    assert load_output(_j(dump_output(finished.resolution_results))) == finished.resolution_results
    rows = dump_resolution_entries(finished.resolution_results)
    assert rows[0]["category_id"] == 1 and rows[0]["place_id"] == "pl,ace,1"
    assert rows[0]["value"]["phase1"]["metrics_source_content"]["_index"] == {}


def test_a_saved_state_of_another_version_is_rejected() -> None:
    data = _j(dump_state(SpecificMetricResolutionState(category_metric_plans=[])))
    data["version"] = R3_STATE_SCHEMA_VERSION + 1
    with pytest.raises(StateVersionMismatchError):
        load_state(data)


async def test_version_mismatch_closes_the_run_on_retry_and_reads_as_failed() -> None:
    script = Script()
    script.errors = [MetricResolutionProviderError("down", stage="s", cause="availability")]
    coordinator, _, store, _ = _scripted_setup(script)
    run_id = await _start(coordinator)
    store.runs[run_id]["state"]["version"] = 99

    status_view = await coordinator.get_run(USER_A, run_id)
    assert (status_view.status, status_view.retryable) == ("failed", False)
    assert store.runs[run_id]["retryable"] is True  # the status read writes nothing

    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, run_id)
    assert conflict.value.retryable is False
    assert (store.runs[run_id]["status"], store.runs[run_id]["retryable"]) == ("failed", False)


async def test_an_r2_output_of_another_version_is_not_found() -> None:
    coordinator, _, store, r2 = _scripted_setup()
    r2.version_mismatch = True
    with pytest.raises(RunNotFoundError):
        await coordinator.start_run(USER_A, R2_RUN)
    assert store.runs == {}


# --------------------------------------------------------------------------- R3-C6 guard


async def test_two_concurrent_retries_run_once() -> None:
    script = Script()
    script.errors = [MetricResolutionProviderError("down", stage="s", cause="availability")]
    coordinator, _, store, _ = _scripted_setup(script)
    run_id = await _start(coordinator)
    outcomes = await asyncio.gather(
        coordinator.retry_run(USER_A, run_id),
        coordinator.retry_run(USER_A, run_id),
        return_exceptions=True,
    )
    await _drain(coordinator)
    assert sum(1 for o in outcomes if isinstance(o, RunConflictError)) == 1
    assert len(script.executions) == 2  # the start plus exactly one retry
    assert store.runs[run_id]["status"] == "finished"


def _seed_running(store: FakeR3RunStore, run_id: str, *, age: timedelta, attempts: int = 0) -> None:
    handoff = _handoff()
    state = SpecificMetricResolutionState(
        category_metric_plans=handoff.category_metric_plans,
        discovered_places=handoff.discovered_places,
        predefined_records=handoff.predefined_records,
    )
    store.runs[run_id] = {
        "run_id": run_id, "user_id": USER_A, "r2_run_id": R2_RUN, "status": "running",
        "state": _j(dump_state(state)), "completed_step": None, "output": None,
        "failure_stage": None, "retryable": False, "attempts": attempts,
        "updated_at": datetime.now(timezone.utc) - age,
    }
    store.steps[run_id] = {}


async def test_a_stale_running_run_is_reclaimed_and_a_fresh_one_is_not() -> None:
    coordinator, script, store, _ = _scripted_setup()
    _seed_running(store, "stale", age=timedelta(minutes=31))
    _seed_running(store, "fresh", age=timedelta(minutes=5))
    _seed_running(store, "used", age=timedelta(minutes=31), attempts=1)

    await coordinator.retry_run(USER_A, "stale")
    await _drain(coordinator)
    assert store.runs["stale"]["status"] == "finished" and store.runs["stale"]["attempts"] == 1

    with pytest.raises(RunConflictError) as fresh:
        await coordinator.retry_run(USER_A, "fresh")
    assert fresh.value.status == "running"
    with pytest.raises(RunConflictError) as used:
        await coordinator.retry_run(USER_A, "used")
    assert used.value.retryable is False


async def test_a_late_older_execution_changes_nothing() -> None:
    script = Script()
    script.after_checkpoint = asyncio.Event()
    script.errors = [None]
    coordinator, _, store, _ = _scripted_setup(script)
    view = await coordinator.start_run(USER_A, R2_RUN)
    while script.waiting == 0:
        await asyncio.sleep(0)
    # A newer execution claimed the row in the meantime (a stale reclaim elsewhere).
    store.runs[view.run_id]["attempts"] = 1
    history_before = list(store.step_history)
    script.after_checkpoint.set()
    await _drain(coordinator)
    row = store.runs[view.run_id]
    assert row["status"] == "running" and row["output"] is None
    assert store.step_history == history_before  # no pipelines row from the old execution


async def test_a_lost_checkpoint_fence_stops_the_run_before_step4() -> None:
    script = Script()
    store = FakeR3RunStore()
    coordinator, _, _, _ = _scripted_setup(script, store)
    view = await coordinator.start_run(USER_A, R2_RUN)
    store.runs[view.run_id]["attempts"] = 5  # owned by a newer execution before STEP 3 ends
    await _drain(coordinator)
    row = store.runs[view.run_id]
    assert row["status"] == "running" and row["completed_step"] is None
    assert store.steps[view.run_id] == {}
    assert script.closed == 1  # the instance still closed


async def test_retry_limit_is_one() -> None:
    script = Script()
    error = MetricResolutionProviderError("down", stage="s", cause="availability")
    script.errors = [error, error]
    coordinator, _, store, _ = _scripted_setup(script)
    run_id = await _start(coordinator)
    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert store.runs[run_id]["retryable"] is False and MAX_RETRY_ATTEMPTS == 1
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(USER_A, run_id)


async def test_a_finished_run_cannot_be_retried() -> None:
    coordinator, _, _, _ = _scripted_setup()
    run_id = await _start(coordinator)
    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, run_id)
    assert conflict.value.status == "finished"


async def test_a_step_row_that_moved_closes_the_run() -> None:
    script = Script()
    script.errors = [MetricResolutionProviderError("down", stage="s", cause="availability")]
    coordinator, _, store, _ = _scripted_setup(script)
    run_id = await _start(coordinator)
    assert store.steps[run_id]["pipelines"]["status"] == "failed"

    async def moved(run, step):
        return False  # the row changed between the read and the claim (WHERE status matched none)

    store.claim_step = moved
    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, run_id)
    assert conflict.value.retryable is False
    assert (store.runs[run_id]["status"], store.runs[run_id]["retryable"]) == ("failed", False)


# --------------------------------------------------------------------------- R3-C7 retryable split


@pytest.mark.parametrize(
    ("error", "stage", "retryable"),
    [
        (MetricResolutionProviderError("x", stage="r3_m1_4_phase1_turn1", cause="availability"), "r3_m1_4_phase1_turn1", True),
        (MetricResolutionProviderError("x", stage="run_specific_metric_resolution", cause="circuit_open"), "run_specific_metric_resolution", True),
        (MetricResolutionValidationError("bad catalog"), "build_tool_catalog", False),
        (McpToolUnavailableError("missing tool"), "verify_capabilities", False),
        (RunStoreError("down", operation="save_checkpoint"), "run_store", True),
        (ValueError("bug"), "unexpected", False),
    ],
)
def test_the_retryable_split(error, stage, retryable) -> None:
    assert R3RunCoordinator._retryable_for(error, 0)[:2] == (stage, retryable)
    assert R3RunCoordinator._retryable_for(error, 1)[1] is False  # the retry itself is never retryable


def test_cancellation_is_retryable_while_under_the_limit() -> None:
    assert R3RunCoordinator._retryable_for(asyncio.CancelledError(), 0) == ("cancelled", True, None)
    assert R3RunCoordinator._retryable_for(asyncio.CancelledError(), 1)[1] is False


def test_config_error_check_walks_causes_and_exception_groups() -> None:
    assert is_config_error(_connection_error(_HTTPStatusError(401))) == 401
    grouped = ExceptionGroup("session", [OSError("x"), _HTTPStatusError(403)])
    assert is_config_error(_connection_error(grouped)) == 403
    assert is_config_error(_connection_error(TimeoutError("slow"))) is None
    assert is_config_error(_connection_error(_HTTPStatusError(503))) is None


async def test_a_refused_key_is_not_retryable_and_a_timeout_is(deep_search_caplog) -> None:
    script = Script()
    script.setup_errors = [_connection_error(ExceptionGroup("g", [_HTTPStatusError(401)]))]
    coordinator, _, store, _ = _scripted_setup(script)
    refused = await _start(coordinator)
    assert (store.runs[refused]["status"], store.runs[refused]["retryable"]) == ("failed", False)
    config_lines = _events(deep_search_caplog, "r3_run.config_error")
    assert len(config_lines) == 1 and config_lines[0]["http_status"] == 401
    assert store.steps[refused] == {}  # a setup error writes no step row

    script.setup_errors.append(_connection_error(TimeoutError("slow")))
    timed_out = await _start(coordinator)
    assert store.runs[timed_out]["retryable"] is True


async def test_a_database_error_on_the_checkpoint_is_retryable_and_reruns_step3() -> None:
    coordinator, script, store, _ = _scripted_setup()
    store.fail_ops["save_checkpoint"] = 1
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert (row["status"], row["failure_stage"], row["retryable"]) == ("failed", "run_store", True)
    assert store.steps[run_id]["discovery_batch"]["status"] == "failed"
    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert script.executions == [None, None] and store.runs[run_id]["status"] == "finished"


async def test_a_database_error_on_the_finish_write_records_pipelines_failed_then_completes() -> None:
    coordinator, script, store, _ = _scripted_setup()
    store.fail_ops["save_finished"] = 1
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert (row["status"], row["failure_stage"], row["retryable"]) == ("failed", "run_store", True)
    assert row["completed_step"] == "discovery_batch"
    assert store.steps[run_id]["pipelines"]["status"] == "failed"
    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert script.executions == [None, "discovery_batch"]  # the retry skips STEP 3
    assert store.runs[run_id]["status"] == "finished"
    assert store.steps[run_id]["pipelines"]["status"] == "completed"


async def test_store_down_for_the_fail_write_leaves_the_run_running(deep_search_caplog) -> None:
    script = Script()
    script.errors = [MetricResolutionProviderError("down", stage="s", cause="availability")]
    coordinator, _, store, _ = _scripted_setup(script)
    store.fail_ops["save_failed"] = 1
    run_id = await _start(coordinator)
    assert store.runs[run_id]["status"] == "running"
    assert len(_events(deep_search_caplog, "r3_run.failed_not_saved")) == 1


# --------------------------------------------------------------------------- ownership


async def test_another_users_runs_are_not_found() -> None:
    coordinator, _, store, _ = _scripted_setup()
    run_id = await _start(coordinator)
    with pytest.raises(RunNotFoundError):
        await coordinator.start_run(USER_B, R2_RUN)
    with pytest.raises(RunNotFoundError):
        await coordinator.retry_run(USER_B, run_id)
    with pytest.raises(RunNotFoundError):
        await coordinator.get_run(USER_B, run_id)
    assert len(store.runs) == 1


# --------------------------------------------------------------------------- R3-C7 background lifecycle


async def test_start_and_retry_return_before_step1() -> None:
    script = Script()
    script.gate = asyncio.Event()
    coordinator, _, _, _ = _scripted_setup(script)
    view = await coordinator.start_run(USER_A, R2_RUN)
    assert view.status == "running" and script.step3_runs == 0
    assert view.run_id in coordinator.tasks
    script.gate.set()
    await _drain(coordinator)
    assert coordinator.tasks == {} and script.closed == 1


async def test_shutdown_mid_run_saves_failed_retryable() -> None:
    script = Script()
    script.gate = asyncio.Event()
    coordinator, _, store, _ = _scripted_setup(script)
    view = await coordinator.start_run(USER_A, R2_RUN)
    while script.waiting == 0:
        await asyncio.sleep(0)
    await coordinator.shutdown()
    row = store.runs[view.run_id]
    assert (row["status"], row["failure_stage"], row["retryable"]) == ("failed", "cancelled", True)
    assert store.steps[view.run_id]["discovery_batch"]["status"] == "failed"
    assert coordinator.tasks == {} and script.closed == 1


async def test_status_answers_from_memory_with_the_checkpointed_step() -> None:
    script = Script()
    script.gate = asyncio.Event()
    script.after_checkpoint = asyncio.Event()
    coordinator, _, store, _ = _scripted_setup(script)
    view = await coordinator.start_run(USER_A, R2_RUN)

    before = await coordinator.get_run(USER_A, view.run_id)
    assert (before.status, before.completed_step) == ("running", None) and store.reads == 0
    with pytest.raises(RunNotFoundError):
        await coordinator.get_run(USER_B, view.run_id)

    script.gate.set()
    while script.waiting < 2:
        await asyncio.sleep(0)
    after = await coordinator.get_run(USER_A, view.run_id)
    assert after.completed_step == "discovery_batch" and store.reads == 0

    script.after_checkpoint.set()
    await _drain(coordinator)
    finished = await coordinator.get_run(USER_A, view.run_id)
    assert finished.status == "finished" and store.reads == 1
    assert {(r["category_id"], r["place_id"]) for r in finished.result} == {(1, "harbor"), (1, "quarry")}


# --------------------------------------------------------------------------- HTTP (R3-C8)

_BASE = "/api/specific-metric-resolution/runs"


@pytest.fixture
def http_setup():
    script = Script()
    coordinator, script, store, r2 = _scripted_setup(script)
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    app.dependency_overrides[get_r3_run_coordinator] = lambda: coordinator
    yield coordinator, script, store
    app.dependency_overrides.clear()


async def _client(user_id: str | None = USER_A) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    if user_id is not None:
        client.cookies.set(ACCESS_TOKEN_COOKIE_POLICY.name, mint_access_token(subject=user_id))
    return client


async def test_every_endpoint_requires_login(http_setup) -> None:
    run = "33333333-3333-4333-8333-333333333333"
    async with await _client(None) as client:
        codes = [
            (await client.post(_BASE, json={"r2_run_id": R2_RUN})).status_code,
            (await client.post(f"{_BASE}/{run}/retry")).status_code,
            (await client.get(f"{_BASE}/{run}")).status_code,
        ]
    assert codes == [401, 401, 401]


async def test_bad_input_is_rejected_before_any_row(http_setup) -> None:
    _, _, store = http_setup
    async with await _client() as client:
        not_uuid = await client.post(_BASE, json={"r2_run_id": "nope"})
        extra = await client.post(_BASE, json={"r2_run_id": R2_RUN, "user_id": USER_B})
        missing = await client.post(_BASE, json={})
    assert [r.status_code for r in (not_uuid, extra, missing)] == [422, 422, 422]
    assert store.runs == {}


async def test_http_start_poll_finish_and_status_codes(http_setup) -> None:
    coordinator, _, _ = http_setup
    async with await _client() as client:
        unknown = await client.post(_BASE, json={"r2_run_id": "55555555-5555-4555-8555-555555555555"})
        assert unknown.status_code == 404
        assert unknown.json() == {"error": "Finished amenity search run not found"}

        started = await client.post(_BASE, json={"r2_run_id": R2_RUN})
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        assert started.json() == {"run_id": run_id, "status": "running"}

        await _drain(coordinator)
        body = (await client.get(f"{_BASE}/{run_id}")).json()
        assert body["status"] == "finished" and body["completed_step"] == "discovery_batch"
        assert {(r["category_id"], r["place_id"]) for r in body["result"]} == {(1, "harbor"), (1, "quarry")}
        assert body["result"][0]["value"]["outcome"] == "completed"

        again = await client.post(f"{_BASE}/{run_id}/retry")
        assert again.status_code == 409 and again.json()["status"] == "finished"

    async with await _client(USER_B) as other:
        assert (await other.get(f"{_BASE}/{run_id}")).status_code == 404
        assert (await other.post(f"{_BASE}/{run_id}/retry")).status_code == 404


async def test_http_failure_reads_as_failed_with_retryable_and_retry_is_202(http_setup) -> None:
    coordinator, script, _ = http_setup
    script.errors = [MetricResolutionProviderError("down", stage="s", cause="availability")]
    async with await _client() as client:
        run_id = (await client.post(_BASE, json={"r2_run_id": R2_RUN})).json()["run_id"]
        await _drain(coordinator)
        failed = (await client.get(f"{_BASE}/{run_id}")).json()
        assert failed == {
            "run_id": run_id, "status": "failed", "completed_step": "discovery_batch", "retryable": True
        }
        retried = await client.post(f"{_BASE}/{run_id}/retry")
        assert retried.status_code == 202
        assert retried.json() == {"run_id": run_id, "status": "running", "completed_step": "discovery_batch"}
        await _drain(coordinator)
        assert (await client.get(f"{_BASE}/{run_id}")).json()["status"] == "finished"
        not_retryable = await client.post(f"{_BASE}/{run_id}/retry")
        assert not_retryable.status_code == 409


async def test_http_store_down_is_503(http_setup) -> None:
    _, _, store = http_setup
    store.fail_ops["create_run"] = 1
    store.fail_ops["load_run"] = 1
    async with await _client() as client:
        start = await client.post(_BASE, json={"r2_run_id": R2_RUN})
        status_read = await client.get(f"{_BASE}/33333333-3333-4333-8333-333333333333")
    assert start.status_code == 503 and start.json() == {"error": "Run storage is unavailable"}
    assert status_read.status_code == 503


async def test_endpoints_answer_503_when_r3_is_not_configured() -> None:
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    try:
        async with await _client() as client:
            response = await client.get(f"{_BASE}/33333333-3333-4333-8333-333333333333")
        assert response.status_code == 503
        assert response.json() == {"error": "Specific metric resolution is not available"}
    finally:
        app.dependency_overrides.clear()
