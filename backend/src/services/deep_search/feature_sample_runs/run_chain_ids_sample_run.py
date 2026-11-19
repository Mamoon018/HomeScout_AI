"""Manual, stage-by-stage run of the run chain: every R3 and R2 body names its parent run.

Not a test: it asserts nothing. It is fully offline: no LLM, no MCP gateway, no Places or Routes
call, no Supabase, no settings or keys, and nothing is written to disk. The change sits between
the run row and the HTTP body and makes no provider call of its own, so nothing here needs one.

The seed is the rows as the previous mechanisms leave them; no earlier mechanism is called:
- one finished `r2_runs` row, `r1_run_id` = a runner-defined R1 id, origin (51.4545, -2.5879),
  `radius_km` 1.5, one category (rowing) with one place, Quayside Rowing Club;
- one finished `r3_runs` row started from that R2 run, one result row for the same place.
The place and ids are made up for this runner and reuse none of the R3 prompt worked pairs
(Northgate Branch Library, Northside Bouldering Hall, Lantern Street Coworking Cafe), the R3.M2.2
seed (Elmstead ice rink, Brackley allotments), the lifecycle or website runner seeds (Brentanobad,
Baeckerei Schaan, Riverside Tennis Club, Saltmarsh Leisure Centre) or the test places.

The rows live in in-memory holders with each store's `load_run` name and user scoping; every
state and output goes through the real codecs and JSON. The runner calls the real coordinators'
`get_run` (stored and live paths) and the real controllers' body builders.

From `backend/` (no keys, no network):
    python -m src.services.deep_search.feature_sample_runs.run_chain_ids_sample_run
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from src.app.api.controllers.amenity_search import _run_response as r2_run_response
from src.app.api.controllers.specific_metric_resolution import _run_response as r3_run_response
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import RunNotFoundError
from src.services.deep_search import r2_run_coordinator, r3_run_coordinator
from src.services.deep_search import r2_run_store, r3_run_store
from src.services.deep_search.feature_schemas.schemas import (
    AmenityResolutionRecord,
    AmenitySearchOutput,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    PredefinedMetricsRecord,
    R2RunRecord,
    R3RunRecord,
    SpecificMetricResolutionState,
    WebsiteSearchResult,
)

_RULE = "=" * 78
_USER = "c4a1e9d0-0000-4000-8000-0000000000c1"
_OTHER_USER = "c4a1e9d0-0000-4000-8000-0000000000c2"
_R1_RUN = "c4a1e9d0-0000-4000-8000-0000000001a1"
_R2_RUN = "c4a1e9d0-0000-4000-8000-0000000002a1"
_R3_RUN = "c4a1e9d0-0000-4000-8000-0000000003a1"
_R2_LIVE = "c4a1e9d0-0000-4000-8000-0000000002b1"
_R3_LIVE = "c4a1e9d0-0000-4000-8000-0000000003b1"

_ORIGIN = GeoPoint(latitude=51.4545, longitude=-2.5879)
_RADIUS_KM = 1.5
_CATEGORY = 7
_PLACE = "seed-quayside-rowing-club"
_KEY = (_CATEGORY, _PLACE)


def _json(value: object) -> object:
    return json.loads(json.dumps(value))


def _place_record() -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=_CATEGORY,
        taxonomy_node="rowing_club",
        depth="specific_attributes",
        place_id=_PLACE,
        name="Quayside Rowing Club",
        category=None,
        address="2 Harbour Steps, Quayside",
        website="https://quaysiderowing.example",
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


def _r2_rows() -> tuple[AmenitySearchState, AmenitySearchOutput]:
    plan = CategoryMetricPlan(_CATEGORY, "rowing_club", "specific_attributes", [], [])
    records = {_CATEGORY: {_PLACE: _place_record()}}
    state = AmenitySearchState(
        origin=_ORIGIN, radius_km=_RADIUS_KM, category_metric_plans=[plan], predefined_records=records
    )
    output = AmenitySearchOutput(
        category_metric_plans=[plan],
        discovered_places={_CATEGORY: {_PLACE: CanonicalPlace(_PLACE, {"id": _PLACE})}},
        predefined_records=records,
    )
    return state, output


def _r3_state() -> SpecificMetricResolutionState:
    return SpecificMetricResolutionState(
        category_metric_plans=[],
        website_search_results={_KEY: WebsiteSearchResult("https://quaysiderowing.example", "google")},
        resolution_results={
            _KEY: AmenityResolutionRecord(
                category_id=_CATEGORY,
                place_id=_PLACE,
                outcome="completed",
                kept={},
                unresolved={"novice_learn_to_row_course": "no_evidence"},  # type: ignore[dict-item]
                phase1=None,
            )
        },
    )


class _MemoryR2Rows:
    """One finished `r2_runs` row in memory, read through R2's real codecs and user scoping."""

    def __init__(self) -> None:
        state, output = _r2_rows()
        self.row = {
            "run_id": _R2_RUN,
            "user_id": _USER,
            "r1_run_id": _R1_RUN,
            "state": _json(r2_run_store.dump_state(state)),
            "output": _json(r2_run_store.dump_output(output)),
        }

    async def load_run(self, run_id: str, user_id: str) -> R2RunRecord | None:
        if (run_id, user_id) != (self.row["run_id"], self.row["user_id"]):
            return None
        return R2RunRecord(
            run_id=run_id,
            user_id=user_id,
            r1_run_id=self.row["r1_run_id"],
            status="finished",
            state=r2_run_store.load_state(self.row["state"]),
            completed_step="discovery",
            attempts=0,
            retryable=False,
            updated_at=datetime.now(timezone.utc).isoformat(),
            output=r2_run_store.load_output(self.row["output"]),
        )


class _MemoryR3Rows:
    """One finished `r3_runs` row in memory, read through R3's real codecs and user scoping."""

    def __init__(self) -> None:
        state = _r3_state()
        rows, _ = r3_run_coordinator.R3RunCoordinator._result_rows(state)
        self.row = {
            "run_id": _R3_RUN,
            "user_id": _USER,
            "r2_run_id": _R2_RUN,
            "state": _json(r3_run_store.dump_state(state)),
            "output": _json(r3_run_store.dump_output(rows)),
        }

    async def load_run(self, run_id: str, user_id: str) -> R3RunRecord | None:
        if (run_id, user_id) != (self.row["run_id"], self.row["user_id"]):
            return None
        return R3RunRecord(
            run_id=run_id,
            user_id=user_id,
            r2_run_id=self.row["r2_run_id"],
            status="finished",
            state=r3_run_store.load_state(self.row["state"]),
            completed_step="discovery_batch",
            attempts=0,
            retryable=False,
            updated_at=datetime.now(timezone.utc).isoformat(),
            output=r3_run_store.load_output(self.row["output"]),
        )


class _NoReads:
    """Neither status read touches the parent's store; reaching this is a runner bug."""

    async def get_finished_output(self, run_id: str, user_id: str):
        raise AssertionError("no parent store is read in this runner")


class _RecordCollector(logging.Handler):
    """Keeps the coordinators' structured records so this script can print them."""

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


def _no_service():
    raise AssertionError("no R3 instance is built in this runner")


def _body(response) -> dict:
    return json.loads(response.body)


def _short(body: dict) -> dict:
    """The body with `result` reduced to its size, so the parent fields stay readable."""
    shown = dict(body)
    if "result" in shown:
        shown["result"] = f"<{len(shown['result'])} entries>"
    return shown


def _check(label: str, ok: bool) -> bool:
    print(f"{'PASS' if ok else 'MISMATCH'}: {label}")
    return ok


async def run_sample() -> bool:
    configure_logging("INFO")
    collector = _RecordCollector()
    logging.getLogger(DEEP_SEARCH_LOGGER_NAME).addHandler(collector)
    ok = True

    r2_rows, r3_rows = _MemoryR2Rows(), _MemoryR3Rows()
    r2 = r2_run_coordinator.R2RunCoordinator(
        r2_rows,  # type: ignore[arg-type]
        _NoReads(),  # type: ignore[arg-type]
        places_client=None,  # type: ignore[arg-type]
        routes_client=None,  # type: ignore[arg-type]
        global_places_semaphore=None,
    )
    r3 = r3_run_coordinator.R3RunCoordinator(
        r3_rows,  # type: ignore[arg-type]
        _NoReads(),  # type: ignore[arg-type]
        service_factory=_no_service,
    )

    _section("1. SEEDED ROWS (as R2 and R3 leave them when finished)")
    print(f"r2_runs {_R2_RUN}: r1_run_id={_R1_RUN} origin=({_ORIGIN.latitude}, {_ORIGIN.longitude})"
          f" radius_km={_RADIUS_KM}")
    print(f"r3_runs {_R3_RUN}: r2_run_id={_R2_RUN} rows=1 (Quayside Rowing Club)")

    _section("2. R3 STORED FINISHED BODY (get_run -> _run_response)")
    body = _body(r3_run_response(await r3.get_run(_USER, _R3_RUN), 200))
    print(json.dumps(_short(body), indent=2))
    ok &= _check("r2_run_id names the seeded R2 run", body.get("r2_run_id") == _R2_RUN)

    # A parked task stands in for a running execution, so the live path answers without a row.
    parked = [asyncio.create_task(asyncio.Event().wait()) for _ in range(2)]
    try:
        _section("3. R3 LIVE RUNNING BODY (answered from the live task, no row read)")
        r3.tasks[_R3_LIVE] = r3_run_coordinator._LiveRun(parked[0], _USER, _R2_RUN)
        body = _body(r3_run_response(await r3.get_run(_USER, _R3_LIVE), 200))
        print(json.dumps(body, indent=2))
        ok &= _check("live R3 body carries r2_run_id", body.get("r2_run_id") == _R2_RUN)

        _section("4. R2 STORED FINISHED BODY (get_run -> _run_response)")
        body = _body(r2_run_response(await r2.get_run(_USER, _R2_RUN), 200))
        print(json.dumps(_short(body), indent=2))
        expected = (_R1_RUN, {"latitude": 51.4545, "longitude": -2.5879}, _RADIUS_KM)
        ok &= _check(
            "r1_run_id, origin and radius_km match the seed",
            (body.get("r1_run_id"), body.get("origin"), body.get("radius_km")) == expected,
        )

        _section("5. R2 LIVE RUNNING BODY (answered from the live task, no row read)")
        r2.tasks[_R2_LIVE] = r2_run_coordinator._LiveRun(
            parked[1], _USER, _R1_RUN, _ORIGIN, _RADIUS_KM
        )
        body = _body(r2_run_response(await r2.get_run(_USER, _R2_LIVE), 200))
        print(json.dumps(body, indent=2))
        ok &= _check(
            "live R2 body carries r1_run_id, origin and radius_km",
            (body.get("r1_run_id"), body.get("origin"), body.get("radius_km")) == expected,
        )

        _section("6. ANOTHER USER READS EACH RUN (stays not found)")
        for name, coordinator, run_id in (
            ("R3 stored", r3, _R3_RUN),
            ("R3 live", r3, _R3_LIVE),
            ("R2 stored", r2, _R2_RUN),
            ("R2 live", r2, _R2_LIVE),
        ):
            try:
                await coordinator.get_run(_OTHER_USER, run_id)
                ok &= _check(f"{name}: not found for another user", False)
            except RunNotFoundError as exc:
                ok &= _check(f"{name}: RunNotFoundError ({exc})", True)
    finally:
        for task in parked:
            task.cancel()
        await asyncio.gather(*parked, return_exceptions=True)
        r3.tasks.clear()
        r2.tasks.clear()

    _section("7. LOGGED BOUNDARY EVENTS (r3_run.loaded / r2_run.loaded)")
    for event in collector.events("r3_run.loaded", "r2_run.loaded"):
        print(json.dumps({k: event.get(k) for k in ("event", "run_id", "r1_run_id", "r2_run_id",
                                                    "status") if k in event}))
    loaded = collector.events("r3_run.loaded", "r2_run.loaded")
    ok &= _check(
        "each loaded event names its parent",
        bool(loaded)
        and all(e.get("r2_run_id") == _R2_RUN for e in loaded if e["event"] == "r3_run.loaded")
        and all(e.get("r1_run_id") == _R1_RUN for e in loaded if e["event"] == "r2_run.loaded"),
    )
    return ok


def main() -> int:
    try:
        ok = asyncio.run(run_sample())
    except Exception as exc:  # a manual runner: show what broke and exit non-zero
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {getattr(exc, 'stage', '-')}")
        print(f"message:   {exc}")
        return 1
    return 0 if ok else 1


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


if __name__ == "__main__":
    sys.exit(main())
