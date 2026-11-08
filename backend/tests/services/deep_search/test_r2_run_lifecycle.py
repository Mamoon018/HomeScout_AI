"""Fixture set for R2 as an independent service (R2-C1 to R2-C8). No live calls, no database.

- `FakePlacesClient` / `FakeRoutesClient` return fixed responses, count calls per kind, track how
  many calls are in flight (overall and per run), can hold discovery behind a gate, and raise
  injected Google errors wrapped exactly as the real clients wrap them, so the config-error check
  walks the real `__cause__` chain.
- `FakeR2RunStore` keeps rows in memory and applies the same rules as the SQL (each rule sits next
  to a comment naming the condition it copies). Every payload round-trips through the real codecs
  and JSON, so the coordinator sees what the database would give back.
- `FakeR1Output` stands in for `R1RunStore.get_finished_output`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core import exceptions as google_exceptions
from google.maps import places_v1, routing_v2
from httpx import ASGITransport, AsyncClient

from src.app.api.dependencies.deep_search import get_r2_run_coordinator
from src.app.api.dependencies.supabase import get_access_token_verifier
from src.app.main import app
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, run_id_var
from src.exceptions.deep_search import (
    PlaceDiscoveryCallError,
    ResultAssemblyError,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    StateVersionMismatchError,
)
from src.exceptions.places import PlacesClientError
from src.exceptions.routes import RoutesClientError
from src.services.auth.session_cookies import ACCESS_TOKEN_COOKIE_POLICY
from src.services.deep_search.amenity_search import AmenitySearch
from src.services.deep_search.feature_schemas.schemas import (
    PREDEFINED_METRICS_BY_DEPTH,
    AmenitySearchOutput,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    EnrichmentBundle,
    GeoPoint,
    R2RunRecord,
    R2StepRecord,
    RouteLeg,
    TransitLeg,
)
from src.services.deep_search.r2_run_coordinator import (
    MAX_RETRY_ATTEMPTS,
    R2RunCoordinator,
    is_config_error,
    remaining_steps,
)
from src.services.deep_search.r2_run_store import (
    R2_STATE_SCHEMA_VERSION,
    dump_output,
    dump_state,
    dump_step_output,
    load_output,
    load_state,
    load_step_output,
)
from tests.conftest import make_access_token_verifier, mint_access_token

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
R1_RUN = "44444444-4444-4444-8444-444444444444"
ORIGIN = GeoPoint(latitude=48.2082, longitude=16.3738)

_CAPTURE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src/services/deep_search/feature_sample_runs/data/m1_1_discovered_places.json"
)


# --------------------------------------------------------------------------- inputs


def _plans() -> list[CategoryMetricPlan]:
    return [
        CategoryMetricPlan(
            category_id=0,
            taxonomy_node="pharmacy",
            depth="basic_profile",
            predefined_metrics=list(PREDEFINED_METRICS_BY_DEPTH["basic_profile"]),
            specific_metrics=[],
        ),
        CategoryMetricPlan(
            category_id=1,
            taxonomy_node="gym",
            depth="operating_details",
            predefined_metrics=list(PREDEFINED_METRICS_BY_DEPTH["operating_details"]),
            specific_metrics=[],
        ),
    ]


# place_id -> (lat, lng); `shared` is found by both categories.
_PLACES_BY_TYPE: dict[str, dict[str, tuple[float, float]]] = {
    "pharmacy": {"ph-1": (48.21, 16.37), "shared": (48.20, 16.38)},
    "gym": {"gym-1": (48.22, 16.36), "shared": (48.20, 16.38)},
}


def _place(place_id: str, lat: float, lng: float) -> places_v1.Place:
    return places_v1.Place(
        id=place_id,
        display_name={"text": f"Place {place_id}"},
        location={"latitude": lat, "longitude": lng},
        price_level=places_v1.PriceLevel.PRICE_LEVEL_MODERATE,
        rating=4.5,
    )


def _wrapped(google_exc: Exception, wrapper: type[Exception]) -> Exception:
    """A client error raised `from` a Google error, exactly as the real clients do."""
    try:
        try:
            raise google_exc
        except google_exceptions.GoogleAPIError as exc:
            raise wrapper(f"wrapped: {exc}") from exc
    except wrapper as wrapped:
        return wrapped


# --------------------------------------------------------------------------- fake clients


class FakePlacesClient:
    """Fixed searchNearby responses per primary type; counts and in-flight tracking per run."""

    def __init__(self, *, delay: float = 0.0) -> None:
        self.calls = {"discovery": 0, "routing": 0}
        self.fail: dict[str, list[Exception]] = {"discovery": [], "routing": []}
        self.fail_always: dict[str, Exception | None] = {"discovery": None, "routing": None}
        self.gate: asyncio.Event | None = None
        self.waiting = 0
        self.delay = delay
        self.in_flight = 0
        self.max_in_flight = 0
        self.per_run: dict[str, int] = {}
        self.max_per_run = 0
        self.closed = False
        self.on_close = None

    async def _enter(self, kind: str) -> None:
        if kind == "discovery" and self.gate is not None:
            self.waiting += 1
            await self.gate.wait()
            self.waiting -= 1
        self.calls[kind] += 1
        run = run_id_var.get()
        self.in_flight += 1
        self.per_run[run] = self.per_run.get(run, 0) + 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.max_per_run = max(self.max_per_run, self.per_run[run])
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail_always[kind] is not None:
                raise self.fail_always[kind]
            if self.fail[kind]:
                raise self.fail[kind].pop(0)
        finally:
            self.in_flight -= 1
            self.per_run[run] -= 1

    async def search_nearby_discovery(self, *, primary_type, **_kwargs):
        await self._enter("discovery")
        places = [_place(pid, *loc) for pid, loc in _PLACES_BY_TYPE[primary_type].items()]
        return places_v1.SearchNearbyResponse(places=places)

    async def search_nearby_routing(self, *, primary_type, travel_mode, **_kwargs):
        await self._enter("routing")
        seconds = {"walk": 600, "drive": 120, "cycle": 240}[travel_mode]
        places, summaries = [], []
        for pid in _PLACES_BY_TYPE[primary_type]:
            places.append(places_v1.Place(id=pid))
            summaries.append(
                places_v1.RoutingSummary(
                    legs=[{"distance_meters": 900, "duration": timedelta(seconds=seconds)}]
                )
            )
        return places_v1.SearchNearbyResponse(places=places, routing_summaries=summaries)

    async def aclose(self) -> None:
        if self.on_close is not None:
            self.on_close()
        self.closed = True


class FakeRoutesClient:
    def __init__(self) -> None:
        self.calls = 0
        self.fail: list[Exception] = []
        self.fail_always: Exception | None = None
        self.closed = False

    async def compute_route_matrix(self, *, origin, destinations, departure_time):
        self.calls += 1
        if self.fail_always is not None:
            raise self.fail_always
        if self.fail:
            raise self.fail.pop(0)
        return [
            routing_v2.RouteMatrixElement(
                origin_index=0,
                destination_index=index,
                condition=routing_v2.RouteMatrixElementCondition.ROUTE_EXISTS,
                distance_meters=2000 + index,
                duration=timedelta(seconds=900),
            )
            for index in range(len(destinations))
        ]

    async def aclose(self) -> None:
        self.closed = True


# --------------------------------------------------------------------------- fake stores


class FakeR1Output:
    """`R1RunStore.get_finished_output`: finished rows only, this user only, version checked."""

    def __init__(self) -> None:
        self.finished: dict[tuple[str, str], list[CategoryMetricPlan]] = {}
        self.mismatch: set[str] = set()

    async def get_finished_output(self, run_id: str, user_id: str):
        if run_id in self.mismatch:
            raise StateVersionMismatchError(2, 1)
        return self.finished.get((run_id, user_id))


class FakeR2RunStore:
    """In-memory `r2_runs` + `r2_run_steps` with `R2RunStore`'s method names and SQL rules."""

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.steps: dict[str, dict[str, dict]] = {}
        self.step_history: list[tuple[str, str, str]] = []
        self.checkpoint_states: list[dict] = []
        self.reads = 0
        self.writes = 0
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
        self.writes += 1

    async def create_run(self, run_id, user_id, r1_run_id, state) -> None:
        self._maybe_fail("create_run")
        self.runs[run_id] = {
            "run_id": run_id,
            "user_id": user_id,
            "r1_run_id": r1_run_id,
            "status": "running",
            "state": json.loads(json.dumps(dump_state(state))),
            "completed_step": None,
            "output": None,
            "failure_stage": None,
            "retryable": False,
            "attempts": 0,
            "updated_at": self._now(),
        }
        self.steps[run_id] = {}

    async def save_checkpoint(self, run_id, user_id, *, attempts, state, completed_step) -> bool:
        self._maybe_fail("save_checkpoint")
        row = self._fenced(run_id, user_id, attempts)
        if row is None:
            return False
        state_json = json.loads(json.dumps(dump_state(state)))
        self.checkpoint_states.append(state_json)
        self._touch(row, state=state_json, completed_step=completed_step)
        return True

    async def save_finished(self, run_id, user_id, *, attempts, state, output) -> bool:
        self._maybe_fail("save_finished")
        row = self._fenced(run_id, user_id, attempts)
        if row is None:
            return False
        # CHECK ((status = 'finished') = (output is not null))
        self._touch(
            row,
            status="finished",
            state=json.loads(json.dumps(dump_state(state))),
            output=json.loads(json.dumps(dump_output(output))),
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

    async def load_run(self, run_id, user_id) -> R2RunRecord | None:
        self.reads += 1
        self._maybe_fail("load_run")
        row = self.runs.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        record = R2RunRecord(
            run_id=run_id,
            user_id=row["user_id"],
            r1_run_id=row["r1_run_id"],
            status=row["status"],
            state=load_state(row["state"]),
            completed_step=row["completed_step"],
            attempts=row["attempts"],
            retryable=row["retryable"],
            updated_at=row["updated_at"].isoformat(),
            output=load_output(row["output"]) if row["output"] is not None else None,
            failure_stage=row["failure_stage"],
            steps={
                step_id: R2StepRecord(
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

    async def get_finished_output(self, run_id, user_id):
        row = self.runs.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "finished":
            return None
        return load_output(row["output"])

    def _step_update(self, run_id, step_id, expected) -> dict | None:
        row = self.steps.get(run_id, {}).get(step_id)
        if row is None or row["status"] == "completed":  # completed rows never change (trigger)
            return None
        return row if row["status"] == expected else None

    async def insert_step(self, run_id, step_id, result) -> bool:
        self._maybe_fail("insert_step")
        if step_id in self.steps[run_id]:  # primary key (run_id, step_id)
            return False
        self.steps[run_id][step_id] = {
            "status": "completed",
            "output": json.loads(json.dumps(dump_step_output(step_id, result))),
        }
        self.step_history.append((run_id, step_id, "completed"))
        return True

    async def complete_claimed_step(self, run_id, step_id, result) -> bool:
        row = self._step_update(run_id, step_id, "started")
        if row is None:
            return False
        row.update(
            status="completed", output=json.loads(json.dumps(dump_step_output(step_id, result)))
        )
        self.step_history.append((run_id, step_id, "completed"))
        return True

    async def claim_failed_step(self, run_id, step_id) -> bool:
        row = self._step_update(run_id, step_id, "failed")
        if row is None:
            return False
        row.update(status="started", error_type=None, retryable=None)
        self.step_history.append((run_id, step_id, "started"))
        return True

    async def save_step_failed(
        self, run_id, step_id, *, error_type, message, retryable, claimed
    ) -> bool:
        values = {"status": "failed", "error_type": error_type, "retryable": retryable}
        if claimed:
            row = self._step_update(run_id, step_id, "started")
            if row is None:
                return False
            row.update(values)
        else:
            if step_id in self.steps[run_id]:
                return False
            self.steps[run_id][step_id] = dict(values)
        self.step_history.append((run_id, step_id, "failed"))
        return True


# --------------------------------------------------------------------------- helpers


def _setup(
    *,
    places: FakePlacesClient | None = None,
    routes: FakeRoutesClient | None = None,
    store: FakeR2RunStore | None = None,
    global_cap: int | None = 15,
    plans: list[CategoryMetricPlan] | None = None,
):
    places = places or FakePlacesClient()
    routes = routes or FakeRoutesClient()
    store = store or FakeR2RunStore()
    r1 = FakeR1Output()
    r1.finished[(R1_RUN, USER_A)] = plans or _plans()
    coordinator = R2RunCoordinator(
        store,
        r1,
        places_client=places,
        routes_client=routes,
        global_places_semaphore=asyncio.Semaphore(global_cap) if global_cap else None,
        stale_after_seconds=600,
    )
    return coordinator, places, routes, store


async def _drain(coordinator: R2RunCoordinator) -> None:
    """Wait until every background task has ended and been removed from the task set."""
    for _ in range(100):
        tasks = [task for task, _ in coordinator.tasks.values()]
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)
    raise AssertionError("background tasks did not finish")


async def _start(coordinator: R2RunCoordinator, user: str = USER_A) -> str:
    view = await coordinator.start_run(user, R1_RUN, ORIGIN, 2.0)
    await _drain(coordinator)
    return view.run_id


def _final_state_json(store: FakeR2RunStore, run_id: str) -> str:
    return json.dumps(store.runs[run_id]["state"], sort_keys=True)


async def _direct_state_json() -> str:
    """The three step methods called directly, as a one-call R2 run does today."""
    search = AmenitySearch(FakePlacesClient(), FakeRoutesClient())
    state = AmenitySearchState(origin=ORIGIN, radius_km=2.0, category_metric_plans=_plans())
    await search.run_place_discovery(state)
    await search.run_accessibility_enrichment(state)
    search.run_result_attachment(state)
    return json.dumps(json.loads(json.dumps(dump_state(state))), sort_keys=True)


def _service_unavailable_transit() -> Exception:
    return _wrapped(google_exceptions.ServiceUnavailable("down"), RoutesClientError)


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


# --------------------------------------------------------------------------- R2-C2 step plan


def test_resume_rule_follows_completed_step() -> None:
    assert [s.name for s in remaining_steps(None)] == ["discovery", "enrichment", "attachment"]
    assert [s.name for s in remaining_steps("discovery")] == ["enrichment", "attachment"]


async def test_parity_with_a_direct_call_of_the_three_methods() -> None:
    coordinator, _, _, store = _setup()
    run_id = await _start(coordinator)
    assert store.runs[run_id]["status"] == "finished"
    assert _final_state_json(store, run_id) == await _direct_state_json()


async def test_resume_parity_and_discovery_runs_once_in_total() -> None:
    routes = FakeRoutesClient()
    routes.fail.append(_service_unavailable_transit())
    coordinator, places, _, store = _setup(routes=routes)

    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert (row["status"], row["retryable"], row["completed_step"]) == ("failed", True, "discovery")
    assert row["failure_stage"] == "retrieve_transit"

    view = await coordinator.retry_run(USER_A, run_id)
    assert (view.status, view.completed_step) == ("running", "discovery")
    await _drain(coordinator)

    assert store.runs[run_id]["status"] == "finished"
    assert store.runs[run_id]["failure_stage"] is None  # the finish write clears the old failure
    assert places.calls["discovery"] == len(_plans())  # one call per category, never repeated
    assert _final_state_json(store, run_id) == await _direct_state_json()


async def test_failure_in_attachment_keeps_the_discovery_checkpoint(monkeypatch) -> None:
    def broken(self, state):
        raise ResultAssemblyError("no plan", stage="assemble_amenity_records")

    monkeypatch.setattr(AmenitySearch, "run_result_attachment", broken)
    coordinator, _, _, store = _setup()
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert (row["status"], row["completed_step"], row["retryable"]) == ("failed", "discovery", False)
    assert set(store.steps[run_id]) == {"discovery"}  # attachment has no row; enrichment waits


async def test_save_as_failed_never_touches_state_or_checkpoint() -> None:
    routes = FakeRoutesClient()
    routes.fail.append(_service_unavailable_transit())
    coordinator, _, _, store = _setup(routes=routes)
    run_id = await _start(coordinator)
    assert store.runs[run_id]["state"] == store.checkpoint_states[-1]
    assert store.runs[run_id]["completed_step"] == "discovery"
    assert store.runs[run_id]["state"]["state"]["enrichment"] == {}


# --------------------------------------------------------------------------- R2-C3 codec


def _capture_places() -> dict[int, dict[str, CanonicalPlace]]:
    raw = json.loads(_CAPTURE.read_text(encoding="utf-8"))
    return {
        int(category_id): {pid: CanonicalPlace(place_id=pid, place=place) for pid, place in ps.items()}
        for category_id, ps in raw.items()
    }


def _capture_plans() -> list[CategoryMetricPlan]:
    return [
        CategoryMetricPlan(0, "swimming_pool", "operating_details",
                           list(PREDEFINED_METRICS_BY_DEPTH["operating_details"]), []),
        CategoryMetricPlan(1, "bakery", "basic_profile",
                           list(PREDEFINED_METRICS_BY_DEPTH["basic_profile"]), []),
    ]


def _round_trip_state(state: AmenitySearchState) -> AmenitySearchState:
    return load_state(json.loads(json.dumps(dump_state(state))))


def test_initial_after_discovery_and_finished_states_round_trip_with_real_places() -> None:
    initial = AmenitySearchState(ORIGIN, 2.0, _capture_plans())
    assert _round_trip_state(initial) == initial

    after_discovery = AmenitySearchState(ORIGIN, 2.0, _capture_plans(), _capture_places())
    back = _round_trip_state(after_discovery)
    assert back == after_discovery
    assert all(isinstance(category_id, int) for category_id in back.discovered_places)

    finished = AmenitySearchState(ORIGIN, 2.0, _capture_plans(), _capture_places())
    place_id = next(iter(finished.discovered_places[0]))
    finished.enrichment[place_id] = EnrichmentBundle(
        place_id, {"walk": RouteLeg(800, 600), "drive": None, "cycle": RouteLeg(800, 240)},
        TransitLeg(1200, 900, True),
    )
    AmenitySearch(FakePlacesClient(), FakeRoutesClient()).run_result_attachment(finished)
    assert _round_trip_state(finished) == finished

    output = AmenitySearchOutput(
        finished.category_metric_plans, finished.discovered_places, finished.predefined_records
    )
    assert load_output(json.loads(json.dumps(dump_output(output)))) == output
    for step_id, payload in (("discovery", finished.discovered_places),
                             ("enrichment", finished.enrichment)):
        assert load_step_output(step_id, json.loads(json.dumps(dump_step_output(step_id, payload)))) == payload


def test_a_saved_state_of_another_version_is_rejected() -> None:
    data = dump_state(AmenitySearchState(ORIGIN, 2.0, _plans()))
    data["version"] = R2_STATE_SCHEMA_VERSION + 1
    with pytest.raises(StateVersionMismatchError):
        load_state(data)


async def test_version_mismatch_closes_the_run_on_retry_and_reads_as_failed() -> None:
    routes = FakeRoutesClient()
    routes.fail.append(_service_unavailable_transit())
    coordinator, _, _, store = _setup(routes=routes)
    run_id = await _start(coordinator)
    store.runs[run_id]["state"]["version"] = R2_STATE_SCHEMA_VERSION + 1

    writes = store.writes
    view = await coordinator.get_run(USER_A, run_id)
    assert (view.status, view.retryable) == ("failed", False)
    assert store.writes == writes  # the status read writes nothing

    with pytest.raises(RunConflictError) as info:
        await coordinator.retry_run(USER_A, run_id)
    assert (info.value.status, info.value.retryable) == ("failed", False)
    assert store.runs[run_id]["retryable"] is False


# --------------------------------------------------------------------------- R2-C5 guard


async def test_two_concurrent_retries_run_once() -> None:
    routes = FakeRoutesClient()
    routes.fail.append(_service_unavailable_transit())
    coordinator, places, _, store = _setup(routes=routes)
    run_id = await _start(coordinator)
    routing_before = places.calls["routing"]

    results = await asyncio.gather(
        coordinator.retry_run(USER_A, run_id),
        coordinator.retry_run(USER_A, run_id),
        return_exceptions=True,
    )
    await _drain(coordinator)
    conflicts = [r for r in results if isinstance(r, RunConflictError)]
    assert len(conflicts) == 1 and "Another retry" in str(conflicts[0])
    assert store.runs[run_id]["status"] == "finished"
    assert store.runs[run_id]["attempts"] == 1
    assert places.calls["routing"] - routing_before == 3 * len(_plans())  # one execution only


def _seed_running(store: FakeR2RunStore, run_id: str, *, age: timedelta, attempts: int = 0) -> None:
    state = AmenitySearchState(ORIGIN, 2.0, _plans())
    store.runs[run_id] = {
        "run_id": run_id, "user_id": USER_A, "r1_run_id": R1_RUN, "status": "running",
        "state": json.loads(json.dumps(dump_state(state))), "completed_step": None,
        "output": None, "failure_stage": None, "retryable": False, "attempts": attempts,
        "updated_at": datetime.now(timezone.utc) - age,
    }
    store.steps[run_id] = {}


async def test_a_stale_running_run_is_reclaimed_and_a_fresh_one_is_not() -> None:
    coordinator, _, _, store = _setup()
    _seed_running(store, "stale", age=timedelta(minutes=11))
    _seed_running(store, "fresh", age=timedelta(seconds=5))
    _seed_running(store, "stale-used", age=timedelta(minutes=11), attempts=1)

    view = await coordinator.retry_run(USER_A, "stale")
    assert view.status == "running"
    await _drain(coordinator)
    assert (store.runs["stale"]["status"], store.runs["stale"]["attempts"]) == ("finished", 1)

    with pytest.raises(RunConflictError) as fresh:
        await coordinator.retry_run(USER_A, "fresh")
    assert fresh.value.status == "running"
    with pytest.raises(RunConflictError) as used:
        await coordinator.retry_run(USER_A, "stale-used")
    assert used.value.retryable is False


async def test_a_late_older_execution_changes_nothing() -> None:
    places = FakePlacesClient()
    places.gate = asyncio.Event()
    coordinator, _, _, store = _setup(places=places)
    view = await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)
    while places.waiting == 0:
        await asyncio.sleep(0)
    # The first execution looks crashed: no write for longer than stale_after.
    store.runs[view.run_id]["updated_at"] -= timedelta(minutes=11)
    await coordinator.retry_run(USER_A, view.run_id)
    places.gate.set()
    await _drain(coordinator)

    row = store.runs[view.run_id]
    assert (row["status"], row["attempts"]) == ("finished", 1)
    # Only the newer execution's step rows exist, once each.
    assert [(s, st) for _, s, st in store.step_history] == [
        ("discovery", "completed"), ("enrichment", "completed")
    ]


async def test_retry_limit_is_one() -> None:
    routes = FakeRoutesClient()
    routes.fail_always = _service_unavailable_transit()
    coordinator, _, _, store = _setup(routes=routes)
    run_id = await _start(coordinator)
    assert store.runs[run_id]["retryable"] is True
    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert (store.runs[run_id]["status"], store.runs[run_id]["retryable"]) == ("failed", False)
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(USER_A, run_id)


async def test_a_finished_run_cannot_be_retried() -> None:
    coordinator, _, _, _ = _setup()
    run_id = await _start(coordinator)
    with pytest.raises(RunConflictError) as info:
        await coordinator.retry_run(USER_A, run_id)
    assert info.value.status == "finished"


# --------------------------------------------------------------------------- R2-C6 retryable split


@pytest.mark.parametrize(
    ("where", "google_exc", "stage", "retryable"),
    [
        ("discovery", google_exceptions.PermissionDenied("key"), "execute_discovery", False),
        ("discovery", google_exceptions.ServiceUnavailable("down"), "execute_discovery", True),
        ("discovery", google_exceptions.ResourceExhausted("quota"), "execute_discovery", True),
        ("routing", google_exceptions.PermissionDenied("key"), "retrieve_mode_routing", False),
        ("routing", google_exceptions.ServiceUnavailable("down"), "retrieve_mode_routing", True),
        ("transit", google_exceptions.PermissionDenied("off"), "retrieve_transit", False),
        ("transit", google_exceptions.InvalidArgument("bad"), "retrieve_transit", False),
        ("transit", google_exceptions.FailedPrecondition("off"), "retrieve_transit", False),
        ("transit", google_exceptions.ServiceUnavailable("down"), "retrieve_transit", True),
    ],
)
async def test_provider_errors_are_retryable_unless_their_cause_is_a_config_error(
    where, google_exc, stage, retryable, deep_search_caplog
) -> None:
    places, routes = FakePlacesClient(), FakeRoutesClient()
    if where == "transit":
        routes.fail_always = _wrapped(google_exc, RoutesClientError)
    else:
        places.fail_always[where] = _wrapped(google_exc, PlacesClientError)
    coordinator, _, _, store = _setup(places=places, routes=routes)
    run_id = await _start(coordinator)

    row = store.runs[run_id]
    assert (row["status"], row["failure_stage"], row["retryable"]) == ("failed", stage, retryable)
    config_lines = _events(deep_search_caplog, "r2_run.config_error")
    if retryable:
        assert config_lines == []
    else:
        assert config_lines and config_lines[0]["google_error_class"] == type(google_exc).__name__


async def test_a_bad_plan_and_an_unexpected_error_are_not_retryable(monkeypatch) -> None:
    bad_plan = [CategoryMetricPlan(0, "   ", "basic_profile",
                                   list(PREDEFINED_METRICS_BY_DEPTH["basic_profile"]), [])]
    coordinator, _, _, store = _setup(plans=bad_plan)
    run_id = await _start(coordinator)
    assert (store.runs[run_id]["failure_stage"], store.runs[run_id]["retryable"]) == (
        "build_discovery_request", False
    )

    async def boom(self, state):
        raise RuntimeError("bug")

    monkeypatch.setattr(AmenitySearch, "run_place_discovery", boom)
    coordinator, _, _, store = _setup()
    run_id = await _start(coordinator)
    assert (store.runs[run_id]["failure_stage"], store.runs[run_id]["retryable"]) == (
        "unexpected", False
    )


def test_config_error_check_walks_the_cause_chain() -> None:
    try:
        raise PlaceDiscoveryCallError("discovery failed") from _wrapped(
            google_exceptions.PermissionDenied("key"), PlacesClientError
        )
    except PlaceDiscoveryCallError as exc:
        assert is_config_error(exc) is google_exceptions.PermissionDenied
    assert is_config_error(PlaceDiscoveryCallError("no cause")) is None


def test_cancellation_and_a_database_error_are_retryable_while_under_the_limit() -> None:
    split = R2RunCoordinator._retryable_for
    assert split(asyncio.CancelledError(), 0) == ("cancelled", True, None)
    assert split(asyncio.CancelledError(), MAX_RETRY_ATTEMPTS)[1] is False
    store_error = RunStoreError("down", operation="save_checkpoint")
    assert split(store_error, 0) == ("run_store", True, None)
    assert split(store_error, MAX_RETRY_ATTEMPTS)[1] is False


async def test_a_database_error_on_the_checkpoint_is_retryable_and_reruns_discovery() -> None:
    store = FakeR2RunStore()
    store.fail_ops["save_checkpoint"] = 1
    coordinator, places, _, _ = _setup(store=store)
    run_id = await _start(coordinator)
    row = store.runs[run_id]
    assert (row["status"], row["failure_stage"], row["retryable"]) == ("failed", "run_store", True)
    assert row["completed_step"] is None
    assert store.steps[run_id]["discovery"]["status"] == "failed"

    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert store.runs[run_id]["status"] == "finished"
    assert places.calls["discovery"] == 2 * len(_plans())  # the unsaved discovery ran again


async def test_store_down_for_the_fail_write_leaves_the_run_running(deep_search_caplog) -> None:
    store = FakeR2RunStore()
    store.fail_ops.update(save_checkpoint=1, save_failed=1)
    coordinator, _, _, _ = _setup(store=store)
    run_id = await _start(coordinator)
    assert store.runs[run_id]["status"] == "running"  # reclaimable once stale
    assert _events(deep_search_caplog, "r2_run.failed_not_saved")


# --------------------------------------------------------------------------- ownership


async def test_another_users_runs_are_not_found() -> None:
    coordinator, places, _, store = _setup()
    with pytest.raises(RunNotFoundError):
        await coordinator.start_run(USER_B, R1_RUN, ORIGIN, 2.0)  # A's R1 run
    assert store.runs == {}

    places.gate = asyncio.Event()
    view = await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)
    with pytest.raises(RunNotFoundError):
        await coordinator.get_run(USER_B, view.run_id)  # live task, other user
    places.gate.set()
    await _drain(coordinator)
    with pytest.raises(RunNotFoundError):
        await coordinator.get_run(USER_B, view.run_id)
    with pytest.raises(RunNotFoundError):
        await coordinator.retry_run(USER_B, view.run_id)


async def test_an_r1_run_of_another_version_is_not_found() -> None:
    coordinator, _, _, store = _setup()
    coordinator._r1_store.mismatch.add(R1_RUN)
    with pytest.raises(RunNotFoundError):
        await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)
    assert store.runs == {}


# --------------------------------------------------------------------------- step rows


async def test_step_rows_for_a_clean_run_and_a_retried_enrichment() -> None:
    coordinator, _, _, store = _setup()
    clean = await _start(coordinator)
    assert {k: v["status"] for k, v in store.steps[clean].items()} == {
        "discovery": "completed", "enrichment": "completed"
    }

    routes = FakeRoutesClient()
    routes.fail.append(_service_unavailable_transit())
    coordinator, _, _, store = _setup(routes=routes)
    run_id = await _start(coordinator)
    failed = store.steps[run_id]["enrichment"]
    assert (failed["status"], failed["retryable"]) == ("failed", True)
    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert [(s, st) for _, s, st in store.step_history] == [
        ("discovery", "completed"),
        ("enrichment", "failed"),
        ("enrichment", "started"),
        ("enrichment", "completed"),
    ]


async def test_a_failed_finish_write_then_a_retry_adds_enrichment_once() -> None:
    store = FakeR2RunStore()
    store.fail_ops["save_finished"] = 1
    coordinator, places, _, _ = _setup(store=store)
    run_id = await _start(coordinator)
    assert store.runs[run_id]["completed_step"] == "discovery"
    assert set(store.steps[run_id]) == {"discovery"}

    await coordinator.retry_run(USER_A, run_id)
    await _drain(coordinator)
    assert store.runs[run_id]["status"] == "finished"
    assert [s for _, s, st in store.step_history if s == "enrichment"] == ["enrichment"]
    assert places.calls["discovery"] == len(_plans())


# --------------------------------------------------------------------------- background lifecycle


async def test_start_and_retry_return_before_any_step_runs() -> None:
    routes = FakeRoutesClient()
    routes.fail.append(_service_unavailable_transit())
    coordinator, places, _, _ = _setup(routes=routes)
    view = await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)
    assert view.status == "running" and places.calls["discovery"] == 0
    assert view.run_id in coordinator.tasks
    await _drain(coordinator)
    assert coordinator.tasks == {}

    routing = places.calls["routing"]
    retried = await coordinator.retry_run(USER_A, view.run_id)
    assert retried.status == "running" and places.calls["routing"] == routing
    await _drain(coordinator)
    assert coordinator.tasks == {}


async def test_shutdown_mid_run_saves_failed_retryable_before_the_clients_close() -> None:
    places = FakePlacesClient()
    places.gate = asyncio.Event()
    coordinator, _, _, store = _setup(places=places)
    view = await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)
    while places.waiting == 0:
        await asyncio.sleep(0)

    statuses_at_close: list[str] = []
    places.on_close = lambda: statuses_at_close.append(store.runs[view.run_id]["status"])
    await coordinator.shutdown()
    await places.aclose()  # lifespan order: shutdown first, then the shared clients

    row = store.runs[view.run_id]
    assert (row["status"], row["failure_stage"], row["retryable"]) == ("failed", "cancelled", True)
    assert statuses_at_close == ["failed"]
    assert store.steps[view.run_id]["discovery"]["status"] == "failed"
    assert coordinator.tasks == {}


async def test_status_answers_from_memory_while_the_task_is_live() -> None:
    places = FakePlacesClient()
    places.gate = asyncio.Event()
    coordinator, _, _, store = _setup(places=places)
    view = await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)

    polled = await coordinator.get_run(USER_A, view.run_id)
    assert polled.status == "running" and store.reads == 0

    places.gate.set()
    await _drain(coordinator)
    finished = await coordinator.get_run(USER_A, view.run_id)
    assert finished.status == "finished" and store.reads == 1
    assert set(finished.result) == {0, 1}
    assert finished.completed_step == "discovery"


async def test_places_calls_respect_the_run_limit_and_the_global_cap() -> None:
    places = FakePlacesClient(delay=0.01)
    coordinator, _, _, store = _setup(places=places, global_cap=15)
    for _ in range(6):
        await coordinator.start_run(USER_A, R1_RUN, ORIGIN, 2.0)
    await _drain(coordinator)
    assert all(row["status"] == "finished" for row in store.runs.values())
    assert places.max_per_run <= 3
    assert 3 < places.max_in_flight <= 15


async def test_a_per_run_instance_does_not_close_the_shared_clients() -> None:
    coordinator, places, routes, _ = _setup()
    await coordinator._new_amenity_search().aclose()
    assert not places.closed and not routes.closed


# --------------------------------------------------------------------------- HTTP (R2-C7)

_BASE = "/api/amenity-search/runs"


@pytest.fixture
def http_setup():
    coordinator, places, routes, store = _setup()
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    app.dependency_overrides[get_r2_run_coordinator] = lambda: coordinator
    yield coordinator, places, routes, store
    app.dependency_overrides.clear()


async def _client(user_id: str | None = USER_A) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    if user_id is not None:
        client.cookies.set(ACCESS_TOKEN_COOKIE_POLICY.name, mint_access_token(subject=user_id))
    return client


def _start_body(**overrides) -> dict:
    body = {"r1_run_id": R1_RUN, "origin": {"latitude": 48.2082, "longitude": 16.3738}}
    body.update(overrides)
    return body


async def test_every_endpoint_requires_login(http_setup) -> None:
    run = "33333333-3333-4333-8333-333333333333"
    async with await _client(None) as client:
        codes = [
            (await client.post(_BASE, json=_start_body())).status_code,
            (await client.post(f"{_BASE}/{run}/retry")).status_code,
            (await client.get(f"{_BASE}/{run}")).status_code,
        ]
    assert codes == [401, 401, 401]


async def test_bad_input_is_rejected_before_any_row(http_setup) -> None:
    _, _, _, store = http_setup
    nan_body = (
        '{"r1_run_id": "%s", "origin": {"latitude": NaN, "longitude": 16.3}}' % R1_RUN
    )
    async with await _client() as client:
        nan = await client.post(_BASE, content=nan_body, headers={"content-type": "application/json"})
        huge = '{"r1_run_id": "%s", "origin": {"latitude": 1, "longitude": 2}, "radius_km": 1e999}'
        infinite = await client.post(_BASE, content=huge % R1_RUN,
                                     headers={"content-type": "application/json"})
        assert infinite.status_code == 422 and infinite.json()["detail"][0]["input"] == "inf"
        zero = await client.post(_BASE, json=_start_body(radius_km=0))
        extra = await client.post(_BASE, json=_start_body(user_id=USER_B))
        missing = await client.post(_BASE, json={"origin": {"latitude": 1, "longitude": 2}})
    assert [r.status_code for r in (nan, zero, extra, missing)] == [422, 422, 422, 422]
    assert store.runs == {}


async def test_http_start_poll_finish_and_status_codes(http_setup) -> None:
    coordinator, _, _, _ = http_setup
    async with await _client() as client:
        unknown = await client.post(
            _BASE, json=_start_body(r1_run_id="55555555-5555-4555-8555-555555555555")
        )
        assert unknown.status_code == 404
        assert unknown.json() == {"error": "Finished requirement interpretation run not found"}

        started = await client.post(_BASE, json=_start_body(radius_km=1.5))
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        assert started.json() == {"run_id": run_id, "status": "running"}

        await _drain(coordinator)
        status_view = await client.get(f"{_BASE}/{run_id}")
        body = status_view.json()
        assert status_view.status_code == 200 and body["status"] == "finished"
        assert body["completed_step"] == "discovery"
        assert set(body["result"]) == {"0", "1"}
        assert body["result"]["1"]["shared"]["routing"]["walk"]["duration_min"] == 10.0

        again = await client.post(f"{_BASE}/{run_id}/retry")
        assert again.status_code == 409 and again.json()["status"] == "finished"

    async with await _client(USER_B) as other:
        assert (await other.get(f"{_BASE}/{run_id}")).status_code == 404
        assert (await other.post(f"{_BASE}/{run_id}/retry")).status_code == 404


async def test_http_failure_reads_as_failed_with_retryable_and_retry_is_202(http_setup) -> None:
    coordinator, _, routes, _ = http_setup
    routes.fail.append(_service_unavailable_transit())
    async with await _client() as client:
        run_id = (await client.post(_BASE, json=_start_body())).json()["run_id"]
        await _drain(coordinator)
        failed = (await client.get(f"{_BASE}/{run_id}")).json()
        assert failed == {
            "run_id": run_id, "status": "failed", "completed_step": "discovery", "retryable": True
        }
        retried = await client.post(f"{_BASE}/{run_id}/retry")
        assert retried.status_code == 202
        assert retried.json() == {"run_id": run_id, "status": "running", "completed_step": "discovery"}
        await _drain(coordinator)
        assert (await client.get(f"{_BASE}/{run_id}")).json()["status"] == "finished"


async def test_http_store_down_is_503(http_setup) -> None:
    _, _, _, store = http_setup
    store.fail_ops["create_run"] = 1
    store.fail_ops["load_run"] = 1
    async with await _client() as client:
        start = await client.post(_BASE, json=_start_body())
        status_read = await client.get(f"{_BASE}/33333333-3333-4333-8333-333333333333")
    assert start.status_code == 503 and start.json() == {"error": "Run storage is unavailable"}
    assert status_read.status_code == 503


async def test_endpoints_answer_503_when_r2_is_not_configured() -> None:
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    try:
        async with await _client() as client:
            response = await client.get(f"{_BASE}/33333333-3333-4333-8333-333333333333")
        assert response.status_code == 503
        assert response.json() == {"error": "Amenity search is not available"}
    finally:
        app.dependency_overrides.clear()
