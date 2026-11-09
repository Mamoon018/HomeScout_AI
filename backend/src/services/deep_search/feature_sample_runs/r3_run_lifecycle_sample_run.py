"""Manual, stage-by-stage run of R3 as an independent service: retry a run that failed in STEP 4
after its STEP 3 checkpoint.

Not a test: it asserts nothing and writes nothing to Supabase or to disk. It seeds one `r3_runs`
row as an earlier execution would have left it: STEP 3 (website discovery) finished cleanly and
was checkpointed (`completed_step = "discovery_batch"`), then every amenity pipeline failed on the
LLM provider, so STEP 5's run-level raise saved the run `failed`, retryable, at `attempts = 0`,
with a completed `discovery_batch` step row and a failed `pipelines` step row.

The seed is the R2 -> R3 handoff plus STEP 3's output, as R3.M1.3 writes it. No earlier mechanism
is called, and the resume skips STEP 3:
- two real places from the M1.1 capture (`data/m1_1_discovered_places.json`): Brentanobad (an
  outdoor pool) and Baeckerei Schaan (a bakery), each with a `PredefinedMetricsRecord` built from
  its captured name, address, website and Google reviews;
- two runner-defined specific metrics per category (one factual, one experiential);
- `website_search_results = google` for both captured websites, with the matching gate records.
None of this reuses the R3 prompt worked pairs (Northgate Branch Library, Northside Bouldering
Hall, Lantern Street Coworking Cafe) or the R3.M2.2 runner seed (Elmstead ice rink, Brackley
allotments).

Rows live in an in-memory holder with `R3RunStore`'s method names and the same fence and claim
rules; every state, output and step payload round-trips through the real codecs and JSON. The
runner drives the real `R3RunCoordinator.retry_run` with the real factory (a real gateway per run on
the real app-wide provider limits) and the real LLM caller, waits for the background task, then
calls `get_run`. Live calls: STEP 4 only (phase-1 tool turns, Parallel searches, resolution turns).

From `backend/` (needs OPENAI_API_KEY and/or GROQ_API_KEY, the Parallel / Firecrawl MCP settings
(FIRECRAWL_API_KEY: the gateway opens both sessions) and network access; no Supabase):
    python -m src.services.deep_search.feature_sample_runs.r3_run_lifecycle_sample_run
"""

import asyncio
import dataclasses
import functools
import json
import logging
import pathlib
import sys
from datetime import datetime, timezone

from src.clients.llm_provider import LLM_PROVIDER_ATTEMPT_EVENT, create_structured_llm_caller
from src.clients.mcp_tools import create_mcp_provider_limits
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import RunConflictError, RunNotFoundError, StateVersionMismatchError
from src.services.deep_search.feature_schemas.schemas import (
    PREDEFINED_METRICS_BY_DEPTH,
    CanonicalPlace,
    CategoryMetricPlan,
    MetricResolutionSource,
    MetricSpec,
    OfficialGateRecord,
    PredefinedMetricsRecord,
    R3RunRecord,
    R3StepRecord,
    SpecificMetricResolutionState,
    WebsiteSearchResult,
)
from src.services.deep_search.r3_run_coordinator import R3RunCoordinator
from src.services.deep_search.r3_run_store import (
    dump_output,
    dump_state,
    dump_step_output,
    load_output,
    load_state,
)
from src.services.deep_search.specific_metric_resolution import (
    DISCOVERY_BATCH_START_EVENT,
    PHASE1_DONE_EVENT,
    PHASE1_TURN_EVENT,
    PIPELINES_DONE_EVENT,
    PIPELINES_START_EVENT,
    RESOLUTION_DONE_EVENT,
    create_specific_metric_resolution,
)

_RULE = "=" * 78
_RUN_ID = "5d2c8e70-0000-4000-8000-00000000f301"
_USER_ID = "5d2c8e70-0000-4000-8000-0000000000a3"
_R2_RUN_ID = "5d2c8e70-0000-4000-8000-00000000b201"

_CAPTURE_PATH = pathlib.Path(__file__).parent / "data" / "m1_1_discovered_places.json"
# (category_id in the capture, place_id): the two amenities this run resolves.
_POOL = (0, "ChIJY4ZI450JvUcRjTDtxXhyNi4")  # Brentanobad
_BAKERY = (1, "ChIJ3ThJAmwJvUcRiJWH23UG-F0")  # Baeckerei Schaan


def _metric(
    label: str, question: str, evidence_class: str, web_target: str, second_target: str
) -> MetricSpec:
    factual = evidence_class == "factual"
    return MetricSpec(
        label=label,
        question=question,
        value_type="boolean",
        unit=None,
        enum_values=[],
        evidence_class=evidence_class,
        resolution_source=MetricResolutionSource(
            web_target=web_target,
            scrape_target=second_target if factual else None,
            review_target=None if factual else second_target,
        ),
        verification=(
            "stated on the official site or a current listing"
            if factual
            else "described by at least two visitor accounts"
        ),
        null_policy="unknown",
        band="specific_attributes",
    )


_POOL_METRICS = [
    _metric(
        "heated_pool_water",
        "Is the pool water heated?",
        "factual",
        "whether the outdoor pool's water is heated",
        "facilities or pool information page",
    ),
    _metric(
        "busy_on_summer_weekends",
        "Is the pool usually crowded on summer weekends?",
        "experiential",
        "visitor accounts of weekend crowding in summer",
        "reviews mentioning crowds or queues",
    ),
]
_BAKERY_METRICS = [
    _metric(
        "sourdough_bread_offered",
        "Does the bakery sell sourdough bread?",
        "factual",
        "whether the bakery's range includes sourdough bread",
        "product range or bread page",
    ),
    _metric(
        "long_saturday_morning_queue",
        "Is there usually a long queue on Saturday mornings?",
        "experiential",
        "visitor accounts of queues on Saturday mornings",
        "reviews mentioning waiting or queues",
    ),
]


def _record(category_id: int, taxonomy_node: str, place_id: str, place: dict) -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=category_id,
        taxonomy_node=taxonomy_node,
        depth="specific_attributes",
        place_id=place_id,
        name=(place.get("display_name") or {}).get("text"),
        category=place.get("primary_type"),
        address=place.get("formatted_address"),
        website=place.get("website_uri") or None,
        google_maps_uri=place.get("google_maps_uri"),
        coordinates=None,
        opening_hours=None,
        contact_phone=place.get("international_phone_number"),
        rating=place.get("rating"),
        review_volume=place.get("user_rating_count"),
        price_level=None,
        reviews=place.get("reviews"),
        routing={},
        transit=None,
    )


def _seed_state() -> SpecificMetricResolutionState:
    """The checkpointed state: R2's handoff plus STEP 3's verdicts; STEP 4 not yet run."""
    capture = json.loads(_CAPTURE_PATH.read_text(encoding="utf-8"))
    pool_place = capture[str(_POOL[0])][_POOL[1]]
    bakery_place = capture[str(_BAKERY[0])][_BAKERY[1]]
    pool = _record(0, "swimming_pool", _POOL[1], pool_place)
    bakery = _record(1, "bakery", _BAKERY[1], bakery_place)
    state = SpecificMetricResolutionState(
        category_metric_plans=[
            CategoryMetricPlan(
                0,
                "swimming_pool",
                "specific_attributes",
                list(PREDEFINED_METRICS_BY_DEPTH["specific_attributes"]),
                _POOL_METRICS,
            ),
            CategoryMetricPlan(
                1,
                "bakery",
                "specific_attributes",
                list(PREDEFINED_METRICS_BY_DEPTH["specific_attributes"]),
                _BAKERY_METRICS,
            ),
        ],
        discovered_places={
            0: {_POOL[1]: CanonicalPlace(_POOL[1], pool_place)},
            1: {_BAKERY[1]: CanonicalPlace(_BAKERY[1], bakery_place)},
        },
        predefined_records={0: {_POOL[1]: pool}, 1: {_BAKERY[1]: bakery}},
    )
    # STEP 3's output as the official-URL gate writes it: both Google websites trusted.
    for key, rec, host, sld in (
        (_POOL, pool, "www.frankfurter-baeder.de", "frankfurter-baeder"),
        (_BAKERY, bakery, "schaan.de", "schaan"),
    ):
        state.website_search_results[key] = WebsiteSearchResult(rec.website, "google")
        state.official_gate_results[key] = OfficialGateRecord(
            name=rec.name,
            website=rec.website,
            host=host,
            registered_domain=f"{sld}.de",
            sld=sld,
            suffix="de",
            compact_name=None,
            compact_sld=sld.replace("-", ""),
            verdict="official",
            reason_code="sld_match",
        )
    return state


def _json(value: object) -> object:
    return json.loads(json.dumps(value))


class _MemoryRunRows:
    """`r3_runs` + `r3_run_steps` in memory, with `R3RunStore`'s method names, fence and codecs."""

    def __init__(self) -> None:
        self.run: dict = {}
        self.steps: dict[str, dict] = {}
        self.writes: list[str] = []

    def seed(self) -> None:
        state = _seed_state()
        self.run = {
            "run_id": _RUN_ID,
            "user_id": _USER_ID,
            "r2_run_id": _R2_RUN_ID,
            "status": "failed",
            "state": _json(dump_state(state)),
            "completed_step": "discovery_batch",
            "output": None,
            "failure_stage": "run_specific_metric_resolution",
            "retryable": True,
            "attempts": 0,
            "updated_at": datetime.now(timezone.utc),
        }
        self.steps = {
            "discovery_batch": {
                "status": "completed",
                "output": _json(dump_step_output("discovery_batch", state)),
            },
            "pipelines": {
                "status": "failed",
                "error_type": "MetricResolutionProviderError",
                "retryable": True,
            },
        }

    def _owned(self, run_id: str, user_id: str) -> bool:
        return self.run.get("run_id") == run_id and self.run.get("user_id") == user_id

    def _fenced(self, run_id: str, user_id: str, attempts: int) -> bool:
        return (
            self._owned(run_id, user_id)
            and self.run["status"] == "running"
            and self.run["attempts"] == attempts
        )

    def _touch(self, **values) -> None:
        self.run.update(values, updated_at=datetime.now(timezone.utc))

    async def load_run(self, run_id, user_id) -> R3RunRecord | None:
        if not self._owned(run_id, user_id):
            return None
        return R3RunRecord(
            run_id=run_id,
            user_id=user_id,
            r2_run_id=self.run["r2_run_id"],
            status=self.run["status"],
            state=load_state(self.run["state"]),
            completed_step=self.run["completed_step"],
            attempts=self.run["attempts"],
            retryable=self.run["retryable"],
            updated_at=self.run["updated_at"].isoformat(),
            output=load_output(self.run["output"]) if self.run["output"] else None,
            failure_stage=self.run["failure_stage"],
            steps={
                step_id: R3StepRecord(step_id, row["status"], row.get("error_type"), row.get("retryable"))
                for step_id, row in self.steps.items()
            },
        )

    async def claim_retry(self, run_id, user_id, *, expected_attempts, stale_before) -> bool:
        failed = self.run["status"] == "failed" and self.run["retryable"]
        stale = self.run["status"] == "running" and self.run["updated_at"] < stale_before
        if not self._owned(run_id, user_id) or self.run["attempts"] != expected_attempts:
            return False
        if not (failed or stale):
            return False
        self._touch(status="running", attempts=expected_attempts + 1, retryable=False)
        self.writes.append(
            f"r3_runs: claim_retry, {('failed' if failed else 'stale running')} -> running, "
            f"attempts {expected_attempts} -> {expected_attempts + 1}"
        )
        return True

    async def claim_step(self, run_id, step_id) -> bool:
        row = self.steps.get(step_id)
        if row is None or row["status"] not in ("failed", "degraded"):
            return False
        self.writes.append(f"r3_run_steps[{step_id}]: {row['status']} -> started")
        self.steps[step_id] = {"status": "started"}
        return True

    async def save_checkpoint(self, run_id, user_id, *, attempts, state) -> bool:
        if not self._fenced(run_id, user_id, attempts):
            return False
        self._touch(state=_json(dump_state(state)), completed_step="discovery_batch")
        self.writes.append("r3_runs: checkpoint completed_step=discovery_batch")
        return True

    async def save_finished(self, run_id, user_id, *, attempts, state, output) -> bool:
        if not self._fenced(run_id, user_id, attempts):
            return False
        self._touch(
            status="finished",
            state=_json(dump_state(state)),
            output=_json(dump_output(output)),
            retryable=False,
            failure_stage=None,
        )
        self.writes.append(
            f"r3_runs: running -> finished, output {len(json.dumps(self.run['output']))} chars, "
            f"state {len(json.dumps(self.run['state']))} chars"
        )
        return True

    async def save_failed(self, run_id, user_id, *, attempts, stage, message, retryable) -> bool:
        if not self._fenced(run_id, user_id, attempts):
            return False
        self._touch(status="failed", failure_stage=stage, retryable=retryable)
        self.writes.append(f"r3_runs: running -> failed (stage={stage}, retryable={retryable})")
        return True

    async def mark_version_mismatch(self, run_id, user_id) -> None:
        self._touch(status="failed", retryable=False)

    async def insert_step(self, run_id, step_id, state) -> bool:
        if step_id in self.steps:
            return False
        self.steps[step_id] = {"status": "completed", "output": _json(dump_step_output(step_id, state))}
        self.writes.append(f"r3_run_steps[{step_id}]: inserted completed")
        return True

    async def complete_claimed_step(self, run_id, step_id, state) -> bool:
        row = self.steps.get(step_id)
        if row is None or row["status"] != "started":
            return False
        self.steps[step_id] = {"status": "completed", "output": _json(dump_step_output(step_id, state))}
        self.writes.append(f"r3_run_steps[{step_id}]: started -> completed")
        return True

    async def save_step_degraded(self, run_id, step_id, state, *, claimed) -> bool:
        self.steps[step_id] = {"status": "degraded", "output": _json(dump_step_output(step_id, state))}
        self.writes.append(f"r3_run_steps[{step_id}]: degraded")
        return True

    async def save_step_failed(self, run_id, step_id, *, error_type, message, retryable, claimed) -> bool:
        self.steps[step_id] = {"status": "failed", "error_type": error_type, "retryable": retryable}
        self.writes.append(f"r3_run_steps[{step_id}]: failed ({error_type}, retryable={retryable})")
        return True


class _NoR2Reads:
    """A retry never reads R2's output; any call here would be a bug in this runner's path."""

    async def get_finished_output(self, run_id, user_id):
        raise AssertionError("retry must not read R2's output")


class _PeakSemaphore(asyncio.Semaphore):
    """Runner-only: an app-wide slot pool that also records its peak number of holders."""

    def __init__(self, value: int) -> None:
        super().__init__(value)
        self.limit = value
        self.held = 0
        self.peak = 0

    async def __aenter__(self):
        await super().__aenter__()
        self.held += 1
        self.peak = max(self.peak, self.held)
        return None

    async def __aexit__(self, *exc_info):
        self.held -= 1
        return await super().__aexit__(*exc_info)


class _RecordCollector(logging.Handler):
    """Keeps the service's structured records so this script can print the stage trail."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass

    def events(self, *names: str) -> list[dict]:
        return [record for record in self.records if record.get("event") in names]

    def prefixed(self, prefix: str) -> list[dict]:
        return [record for record in self.records if str(record.get("event", "")).startswith(prefix)]


async def run_sample() -> bool:
    settings = get_settings()
    configure_logging(settings.log_level)
    collector = _RecordCollector()
    logging.getLogger(DEEP_SEARCH_LOGGER_NAME).addHandler(collector)

    rows = _MemoryRunRows()
    rows.seed()
    llm_caller = create_structured_llm_caller(settings)
    limits = create_mcp_provider_limits(settings)
    search_slots = _PeakSemaphore(settings.r3_parallel_search_concurrency)
    firecrawl_slots = _PeakSemaphore(settings.r3_firecrawl_concurrency)
    limits = dataclasses.replace(limits, search_slots=search_slots, firecrawl_slots=firecrawl_slots)
    coordinator = R3RunCoordinator(
        rows,
        _NoR2Reads(),
        service_factory=functools.partial(
            create_specific_metric_resolution,
            settings,
            llm_caller=llm_caller,
            provider_limits=limits,
        ),
        stale_after_seconds=settings.r3_stale_after_seconds,
    )
    try:
        _section("1. SETTINGS AND APP-WIDE PROVIDER LIMITS")
        print(f"Parallel search slots (app-wide): {settings.r3_parallel_search_concurrency}")
        print(f"Firecrawl slots (app-wide):       {settings.r3_firecrawl_concurrency}")
        print(f"Firecrawl calls per minute:       {settings.r3_firecrawl_rate_per_minute}")
        print(f"stale_after: {settings.r3_stale_after_seconds:.0f} s, "
              f"breaker threshold: {settings.metric_resolution_breaker_threshold}")

        _section("2. SEEDED RUN ROW (r3_runs) AND STEP ROWS (r3_run_steps)")
        print(json.dumps({k: v for k, v in rows.run.items() if k not in ("state", "output")},
                         indent=2, default=str))
        seeded = load_state(rows.run["state"])
        for (category_id, place_id), verdict in seeded.website_search_results.items():
            rec = seeded.predefined_records[category_id][place_id]
            plan = next(p for p in seeded.category_metric_plans if p.category_id == category_id)
            print(f"category {category_id} ({plan.taxonomy_node}): {rec.name!r} "
                  f"website={verdict.website_url} origin={verdict.website_origin} "
                  f"reviews={len(rec.reviews or [])} metrics={[m.label for m in plan.specific_metrics]}")
        for step_id, row in rows.steps.items():
            print(f"step {step_id:<16} {row['status']:<10} {row.get('error_type') or ''}")

        view = await coordinator.retry_run(_USER_ID, _RUN_ID)
        _section("3. RETRY REPLY (202 body), PRE-CHECK AND CLAIM WRITES")
        print(f"view: status={view.status} completed_step={view.completed_step}")
        claim_writes = list(rows.writes)
        for line in claim_writes:
            print(line)

        # Wait for the background execution, as the page would by polling.
        tasks = [live.task for live in coordinator.tasks.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)

        _section("4. STEP 3 CALLS DURING THE RESUME (must be 0)")
        print(f"{DISCOVERY_BATCH_START_EVENT} events: "
              f"{len(collector.events(DISCOVERY_BATCH_START_EVENT))}")

        _section("5. STEP 4 TRAIL (live LLM + Parallel)")
        for event in collector.events(PIPELINES_START_EVENT, PIPELINES_DONE_EVENT):
            fields = {k: v for k, v in event.items() if k not in ("timestamp", "run_id")}
            print(json.dumps(fields, default=str))
        for event in collector.events(PHASE1_TURN_EVENT, PHASE1_DONE_EVENT, RESOLUTION_DONE_EVENT):
            fields = {k: v for k, v in event.items() if k not in ("timestamp", "run_id")}
            print(json.dumps(fields, default=str, ensure_ascii=False))
        attempts = collector.events(LLM_PROVIDER_ATTEMPT_EVENT)
        print(f"llm_provider.attempt lines: {len(attempts)} "
              f"(answered={sum(1 for a in attempts if a.get('outcome') == 'answered')}, "
              f"failed={sum(1 for a in attempts if a.get('outcome') == 'failed')})")
        for attempt in attempts:
            if attempt.get("outcome") == "failed":
                print(f"  failed: stage={attempt.get('stage')} provider={attempt.get('provider')} "
                      f"class={attempt.get('failure_class')} detail={attempt.get('detail')}")

        _section("6. PEAK IN-FLIGHT CALLS PER PROVIDER (app-wide pools)")
        print(f"Parallel:  peak {search_slots.peak} of {search_slots.limit}")
        print(f"Firecrawl: peak {firecrawl_slots.peak} of {firecrawl_slots.limit}")

        _section("7. FINISH WRITE AND STEP ROWS")
        for line in rows.writes[len(claim_writes):]:
            print(line)
        print(f"row: status={rows.run['status']} attempts={rows.run['attempts']} "
              f"completed_step={rows.run['completed_step']} failure_stage={rows.run['failure_stage']}")
        for step_id, row in rows.steps.items():
            print(f"step {step_id:<16} {row['status']}")

        status_view = await coordinator.get_run(_USER_ID, _RUN_ID)
        _section("8. STATUS READ (E3)")
        print(f"status={status_view.status} completed_step={status_view.completed_step} "
              f"retryable={status_view.retryable}")
        for entry in status_view.result or []:
            value = entry["value"]
            rec = seeded.predefined_records[entry["category_id"]][entry["place_id"]]
            print(f"{rec.name!r}: outcome={value['outcome']} resolution_calls={value['resolution_calls']}")
            for label, kept in value["kept"].items():
                print(f"  kept {label}: final_value={kept['final_value']!r} basis={kept['basis']} "
                      f"verification_met={kept['verification_met']}")
            for label, reason in value["unresolved"].items():
                print(f"  unresolved {label}: {reason}")

        _section("9. RUN LIFECYCLE LINES (r3_run.* / r3_step.*)")
        for event in collector.prefixed("r3_"):
            fields = {k: v for k, v in event.items() if k not in ("timestamp", "user_id")}
            print(json.dumps(fields, default=str))

        if rows.run["status"] != "finished":
            _section("FAILED")
            print(f"failure_stage: {rows.run['failure_stage']}")
            print(f"retryable:     {rows.run['retryable']}")
            for event in collector.events("r3_run.failed"):
                print(f"exception:     {event.get('error_class')}")
                print(f"stage:         {event.get('stage')}")
                print(f"message:       {event.get('message')}")
            return False
        return True
    finally:
        await coordinator.shutdown()
        await llm_caller.aclose()


def main() -> int:
    try:
        finished = asyncio.run(run_sample())
    except (RunConflictError, RunNotFoundError, StateVersionMismatchError) as exc:
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {getattr(exc, 'stage', 'retry_run')}")
        print(f"message:   {exc}")
        return 1
    return 0 if finished else 1


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


if __name__ == "__main__":
    sys.exit(main())
