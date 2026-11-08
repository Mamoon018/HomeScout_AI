"""Manual, stage-by-stage run of R2 as an independent service: retry a run that failed in
enrichment after its discovery checkpoint.

Not a test: it asserts nothing and writes nothing to Supabase or to disk. It seeds one `r2_runs`
row as an earlier execution would have left it: discovery finished and was checkpointed
(`completed_step = "discovery"`), then the transit matrix failed, so the run is `failed`,
retryable, at `attempts = 0`, with a completed `discovery` step row and a failed `enrichment` step
row. Discovery is not re-run: its output is the real M1.1 capture
(`data/m1_1_discovered_places.json`), seeded with the origin, radius and plans that produced it,
because enrichment re-searches Places at that origin and joins routing back by `place_id`. R2
makes no LLM call, so it has no prompt worked pairs to avoid.

Rows live in an in-memory holder with `R2RunStore`'s method names and the same fence and claim
rules; every state, output and step payload round-trips through the real codecs and JSON. The
runner drives the real `R2RunCoordinator.retry_run` with the real shared Places and Routes clients
and a global Places cap, waits for the background task, then calls `get_run`. Live calls: the
routing re-search (2 categories x 3 modes) and one transit matrix batch.

From `backend/` (needs GOOGLE_MAPS_API in the environment and network access):
    python -m src.services.deep_search.feature_sample_runs.r2_run_lifecycle_sample_run
"""

import asyncio
import json
import logging
import pathlib
import sys
from datetime import datetime, timezone

from src.clients.google_places import create_places_async_client
from src.clients.google_routes import create_routes_async_client
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, PLACES_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import RunConflictError, RunNotFoundError, StateVersionMismatchError
from src.services.deep_search.amenity_search import (
    ATTACHMENT_ACCESSIBILITY_DEGRADED_EVENT,
    ATTACHMENT_COMPLETED_EVENT,
    DISCOVERY_CATEGORY_EVENT,
    DISCOVERY_REQUEST_EVENT,
    ENRICHMENT_MODE_EVENT,
    ENRICHMENT_TRANSIT_EVENT,
    GLOBAL_PLACES_CONCURRENCY,
)
from src.services.deep_search.feature_schemas.schemas import (
    DEFAULT_RADIUS_KM,
    PREDEFINED_METRICS_BY_DEPTH,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    R2RunRecord,
    R2StepRecord,
)
from src.services.deep_search.r2_run_coordinator import R2RunCoordinator
from src.services.deep_search.r2_run_store import (
    dump_output,
    dump_state,
    dump_step_output,
    load_output,
    load_state,
)

_RULE = "=" * 78
_RUN_ID = "9b7e3c10-0000-4000-8000-00000000c201"
_USER_ID = "9b7e3c10-0000-4000-8000-0000000000d2"
_R1_RUN_ID = "9b7e3c10-0000-4000-8000-00000000e301"

# The exact origin the M1.1 discovery sample used to produce the capture. It MUST match, or the
# routing re-search returns a different place set and the join by place_id finds nothing.
_ORIGIN = GeoPoint(latitude=50.130034, longitude=8.628251)
_DISCOVERED_PLACES_PATH = pathlib.Path(__file__).parent / "data" / "m1_1_discovered_places.json"


def _seed_state() -> AmenitySearchState:
    """The checkpointed state: inputs plus the real discovered set; enrichment not yet run."""
    raw = json.loads(_DISCOVERED_PLACES_PATH.read_text(encoding="utf-8"))
    discovered = {
        int(category_id): {
            place_id: CanonicalPlace(place_id=place_id, place=place)
            for place_id, place in places.items()
        }
        for category_id, places in raw.items()
    }
    return AmenitySearchState(
        origin=_ORIGIN,
        radius_km=DEFAULT_RADIUS_KM,
        category_metric_plans=[
            CategoryMetricPlan(
                category_id=0,
                taxonomy_node="swimming_pool",
                depth="operating_details",
                predefined_metrics=list(PREDEFINED_METRICS_BY_DEPTH["operating_details"]),
                specific_metrics=[],
            ),
            CategoryMetricPlan(
                category_id=1,
                taxonomy_node="bakery",
                depth="basic_profile",
                predefined_metrics=list(PREDEFINED_METRICS_BY_DEPTH["basic_profile"]),
                specific_metrics=[],
            ),
        ],
        discovered_places=discovered,
    )


def _json(value: object) -> object:
    return json.loads(json.dumps(value))


class _MemoryRunRows:
    """`r2_runs` + `r2_run_steps` in memory, with `R2RunStore`'s method names, fence and codecs."""

    def __init__(self) -> None:
        self.run: dict = {}
        self.steps: dict[str, dict] = {}
        self.writes: list[str] = []

    def seed(self) -> None:
        state = _seed_state()
        self.run = {
            "run_id": _RUN_ID,
            "user_id": _USER_ID,
            "r1_run_id": _R1_RUN_ID,
            "status": "failed",
            "state": _json(dump_state(state)),
            "completed_step": "discovery",
            "output": None,
            "failure_stage": "retrieve_transit",
            "retryable": True,
            "attempts": 0,
            "updated_at": datetime.now(timezone.utc),
        }
        self.steps = {
            "discovery": {
                "status": "completed",
                "output": _json(dump_step_output("discovery", state.discovered_places)),
            },
            "enrichment": {
                "status": "failed",
                "error_type": "TransitRetrievalError",
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

    async def load_run(self, run_id, user_id) -> R2RunRecord | None:
        if not self._owned(run_id, user_id):
            return None
        return R2RunRecord(
            run_id=run_id,
            user_id=user_id,
            r1_run_id=self.run["r1_run_id"],
            status=self.run["status"],
            state=load_state(self.run["state"]),
            completed_step=self.run["completed_step"],
            attempts=self.run["attempts"],
            retryable=self.run["retryable"],
            updated_at=self.run["updated_at"].isoformat(),
            output=load_output(self.run["output"]) if self.run["output"] else None,
            failure_stage=self.run["failure_stage"],
            steps={
                step_id: R2StepRecord(step_id, row["status"], row.get("error_type"), row.get("retryable"))
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
            f"r2_runs: claim_retry, {('failed' if failed else 'stale running')} -> running, "
            f"attempts {expected_attempts} -> {expected_attempts + 1}"
        )
        return True

    async def claim_failed_step(self, run_id, step_id) -> bool:
        row = self.steps.get(step_id)
        if row is None or row["status"] != "failed":
            return False
        self.steps[step_id] = {"status": "started"}
        self.writes.append(f"r2_run_steps[{step_id}]: failed -> started")
        return True

    async def save_checkpoint(self, run_id, user_id, *, attempts, state, completed_step) -> bool:
        if not self._fenced(run_id, user_id, attempts):
            return False
        self._touch(state=_json(dump_state(state)), completed_step=completed_step)
        self.writes.append(f"r2_runs: checkpoint completed_step={completed_step}")
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
            f"r2_runs: running -> finished, output {len(json.dumps(self.run['output']))} chars"
        )
        return True

    async def save_failed(self, run_id, user_id, *, attempts, stage, message, retryable) -> bool:
        if not self._fenced(run_id, user_id, attempts):
            return False
        self._touch(status="failed", failure_stage=stage, retryable=retryable)
        self.writes.append(f"r2_runs: running -> failed (stage={stage}, retryable={retryable})")
        return True

    async def mark_version_mismatch(self, run_id, user_id) -> None:
        self._touch(status="failed", retryable=False)

    async def insert_step(self, run_id, step_id, result) -> bool:
        if step_id in self.steps:
            return False
        self.steps[step_id] = {"status": "completed", "output": _json(dump_step_output(step_id, result))}
        self.writes.append(f"r2_run_steps[{step_id}]: inserted completed")
        return True

    async def complete_claimed_step(self, run_id, step_id, result) -> bool:
        row = self.steps.get(step_id)
        if row is None or row["status"] != "started":
            return False
        self.steps[step_id] = {"status": "completed", "output": _json(dump_step_output(step_id, result))}
        self.writes.append(f"r2_run_steps[{step_id}]: started -> completed")
        return True

    async def save_step_failed(self, run_id, step_id, *, error_type, message, retryable, claimed) -> bool:
        self.steps[step_id] = {"status": "failed", "error_type": error_type, "retryable": retryable}
        self.writes.append(f"r2_run_steps[{step_id}]: failed ({error_type}, retryable={retryable})")
        return True


class _NoR1Reads:
    """A retry never reads R1's output; any call here would be a bug in this runner's path."""

    async def get_finished_output(self, run_id, user_id):
        raise AssertionError("retry must not read R1's output")


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
    for name in (DEEP_SEARCH_LOGGER_NAME, PLACES_LOGGER_NAME):
        logging.getLogger(name).addHandler(collector)

    rows = _MemoryRunRows()
    rows.seed()
    places_client = create_places_async_client(settings)
    routes_client = create_routes_async_client(settings)
    coordinator = R2RunCoordinator(
        rows,
        _NoR1Reads(),
        places_client=places_client,
        routes_client=routes_client,
        global_places_semaphore=asyncio.Semaphore(GLOBAL_PLACES_CONCURRENCY),
        stale_after_seconds=settings.r2_stale_after_seconds,
    )
    try:
        _section("1. SEEDED RUN ROW (r2_runs) AND STEP ROWS (r2_run_steps)")
        print(json.dumps({k: v for k, v in rows.run.items() if k not in ("state", "output")},
                         indent=2, default=str))
        seeded = load_state(rows.run["state"])
        for category_id, places in seeded.discovered_places.items():
            plan = next(p for p in seeded.category_metric_plans if p.category_id == category_id)
            print(f"discovered: category {category_id} ({plan.taxonomy_node}): {len(places)} places")
        for step_id, row in rows.steps.items():
            print(f"step {step_id:<11} {row['status']:<10} {row.get('error_type') or ''}")

        view = await coordinator.retry_run(_USER_ID, _RUN_ID)
        _section("2. RETRY REPLY (202 body) AND CLAIM WRITES")
        print(f"view: status={view.status} completed_step={view.completed_step}")
        claim_writes = list(rows.writes)
        for line in claim_writes:
            print(line)

        # Wait for the background execution, as the page would by polling.
        tasks = [task for task, _ in coordinator.tasks.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)

        _section("3. DISCOVERY CALLS DURING THE RESUME (must be 0)")
        discovery = collector.events(DISCOVERY_REQUEST_EVENT, DISCOVERY_CATEGORY_EVENT)
        print(f"discovery events: {len(discovery)}")

        _section("4. ENRICHMENT - LIVE GOOGLE CALLS")
        for event in collector.events(ENRICHMENT_MODE_EVENT):
            print(f"routing re-search: category {event['category_id']} mode {event['mode']:<5} "
                  f"legs={event['leg_count']}")
        for event in collector.events(ENRICHMENT_TRANSIT_EVENT):
            print(f"transit matrix: batch={event['batch_size']} elements={event['element_count']}")
        for event in collector.prefixed("places.") + collector.prefixed("routes."):
            print(f"client line: {json.dumps(event, default=str)}")

        _section("5. ATTACHMENT")
        for event in collector.events(ATTACHMENT_COMPLETED_EVENT):
            print(f"records per category: {event['record_counts']}")
        degraded = collector.events(ATTACHMENT_ACCESSIBILITY_DEGRADED_EVENT)
        print(f"places missing from enrichment (attachment.accessibility_degraded): {len(degraded)}")

        _section("6. FINISH WRITE AND STEP ROWS")
        for line in rows.writes[len(claim_writes):]:
            print(line)
        print(f"row: status={rows.run['status']} attempts={rows.run['attempts']} "
              f"completed_step={rows.run['completed_step']} failure_stage={rows.run['failure_stage']}")
        for step_id, row in rows.steps.items():
            print(f"step {step_id:<11} {row['status']}")

        status_view = await coordinator.get_run(_USER_ID, _RUN_ID)
        _section("7. STATUS READ (E3)")
        print(f"status={status_view.status} completed_step={status_view.completed_step} "
              f"retryable={status_view.retryable}")
        for category_id, records in (status_view.result or {}).items():
            # A place the live re-search no longer returns keeps null walk/drive/cycle (A3).
            no_routing = sum(
                1 for record in records.values() if all(v is None for v in record.routing.values())
            )
            print(f"category {category_id}: {len(records)} records, {no_routing} with no routing")
            for record in list(records.values())[:2]:
                walk = record.routing.get("walk")
                drive = record.routing.get("drive")
                print(
                    f"  {record.name!r}: walk={walk.duration_min if walk else None} min, "
                    f"drive={drive.duration_min if drive else None} min, "
                    f"transit={record.transit.duration_min if record.transit else None} min"
                )

        _section("8. RUN LIFECYCLE LINES (r2_run.* / r2_step.*)")
        for event in collector.prefixed("r2_"):
            fields = {k: v for k, v in event.items() if k not in ("timestamp", "user_id")}
            print(json.dumps(fields, default=str))

        if rows.run["status"] != "finished":
            _section("FAILED")
            print(f"failure_stage: {rows.run['failure_stage']}")
            print(f"retryable:     {rows.run['retryable']}")
            for event in collector.events("r2_run.failed"):
                print(f"exception:     {event.get('error_class')}")
                print(f"message:       {event.get('message')}")
            return False
        return True
    finally:
        await coordinator.shutdown()
        await places_client.aclose()
        await routes_client.aclose()


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
