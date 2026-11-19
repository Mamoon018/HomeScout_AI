"""Manual, stage-by-stage run of R3's finished output with each amenity's website verdict.

Not a test: it asserts nothing. It is fully offline: no LLM, no MCP gateway, no Supabase, no
settings or keys, and nothing is written to disk. This change sits between STEP 5 and the HTTP
body and makes no provider call of its own, so nothing here needs one.

The seed is R3's state as STEP 5 leaves it: `website_search_results` (STEP 3's verdicts) and
`resolution_results` (STEP 5's records). No earlier mechanism is called. The places are made up
for this runner and reuse none of the R3 prompt worked pairs (Northgate Branch Library, Northside
Bouldering Hall, Lantern Street Coworking Cafe), the R3.M2.2 runner seed (Elmstead ice rink,
Brackley allotments), the lifecycle runner seed (Brentanobad, Baeckerei Schaan) or the test places:
- category 3, Riverside Tennis Club: verdict `google`, completed;
- category 3, Saltmarsh Leisure Centre: verdict `discovered`, completed;
- category 5, Saltmarsh Leisure Centre again (same place_id, second category): verdict `none`;
- category 5, Old Mill Farmers Market: verdict `none`, research failed (`pipeline_error`);
- category 5, Kestrel Lane Dance Studio: no verdict at all, to exercise the `none` fallback.

The rows live in an in-memory holder with `R3RunStore`'s method names and fence; every state,
output and step payload goes through the real codecs and JSON. The runner calls the real
coordinator's finish write and status read, and the real controller's body builder.

From `backend/` (no keys, no network):
    python -m src.services.deep_search.feature_sample_runs.r3_result_website_sample_run
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from src.app.api.controllers.specific_metric_resolution import _run_response
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.services.deep_search.feature_schemas.schemas import (
    AmenityResolutionRecord,
    R3RunRecord,
    R3StepRecord,
    SpecificMetricResolutionState,
    WebsiteSearchResult,
)
from src.services.deep_search.r3_run_coordinator import R3RunCoordinator, _Execution, _Progress
from src.services.deep_search.r3_run_store import (
    dump_output,
    dump_state,
    dump_step_output,
    load_output,
    load_state,
)

_RULE = "=" * 78
_RUN_ID = "7e41a0c2-0000-4000-8000-00000000f501"
_USER_ID = "7e41a0c2-0000-4000-8000-0000000000a5"
_R2_RUN_ID = "7e41a0c2-0000-4000-8000-00000000b501"

_TENNIS = (3, "seed-riverside-tennis-club")
_SALTMARSH_SPORT = (3, "seed-saltmarsh-leisure-centre")
_SALTMARSH_FITNESS = (5, "seed-saltmarsh-leisure-centre")
_MARKET = (5, "seed-old-mill-farmers-market")
_DANCE = (5, "seed-kestrel-lane-dance-studio")

_NAMES = {
    _TENNIS[1]: "Riverside Tennis Club",
    _SALTMARSH_SPORT[1]: "Saltmarsh Leisure Centre",
    _MARKET[1]: "Old Mill Farmers Market",
    _DANCE[1]: "Kestrel Lane Dance Studio",
}

_VERDICTS = {
    _TENNIS: WebsiteSearchResult("https://riversidetennis.example", "google"),
    _SALTMARSH_SPORT: WebsiteSearchResult("https://saltmarshleisure.example/centre", "discovered"),
    _SALTMARSH_FITNESS: WebsiteSearchResult(None, "none"),
    _MARKET: WebsiteSearchResult(None, "none"),
    # _DANCE has no verdict on purpose.
}


def _record(key: tuple[int, str], outcome: str, labels: list[str]) -> AmenityResolutionRecord:
    # As `_failed_record` writes a crashed pipeline: every label `resolution_call_failed`.
    reason = "resolution_call_failed" if outcome == "pipeline_error" else "no_evidence"
    return AmenityResolutionRecord(
        category_id=key[0],
        place_id=key[1],
        outcome=outcome,  # type: ignore[arg-type]
        kept={},
        unresolved={label: reason for label in labels},  # type: ignore[misc]
        phase1=None,
    )


def _seed_state() -> SpecificMetricResolutionState:
    racket = ["floodlit_evening_courts", "coaching_for_adults"]
    fitness = ["women_only_sessions", "early_morning_crowding"]
    return SpecificMetricResolutionState(
        category_metric_plans=[],
        website_search_results=dict(_VERDICTS),
        resolution_results={
            _TENNIS: _record(_TENNIS, "completed", racket),
            _SALTMARSH_SPORT: _record(_SALTMARSH_SPORT, "completed", racket),
            _SALTMARSH_FITNESS: _record(_SALTMARSH_FITNESS, "completed", fitness),
            _MARKET: _record(_MARKET, "pipeline_error", fitness),
            _DANCE: _record(_DANCE, "completed", fitness),
        },
    )


def _json(value: object) -> object:
    return json.loads(json.dumps(value))


class _MemoryRunRows:
    """`r3_runs` + `r3_run_steps` in memory, with `R3RunStore`'s method names, fence and codecs."""

    def __init__(self, state: SpecificMetricResolutionState) -> None:
        # As the run is during STEP 4: running, attempts 0, STEP 3 checkpointed.
        self.run: dict = {
            "run_id": _RUN_ID,
            "user_id": _USER_ID,
            "r2_run_id": _R2_RUN_ID,
            "status": "running",
            "state": _json(dump_state(state)),
            "completed_step": "discovery_batch",
            "output": None,
            "failure_stage": None,
            "retryable": False,
            "attempts": 0,
            "updated_at": datetime.now(timezone.utc),
        }
        self.steps: dict[str, dict] = {
            "discovery_batch": {
                "status": "completed",
                "output": _json(dump_step_output("discovery_batch", state)),
            }
        }
        self.writes: list[str] = []

    def _owned(self, run_id: str, user_id: str) -> bool:
        return self.run["run_id"] == run_id and self.run["user_id"] == user_id

    async def save_finished(self, run_id, user_id, *, attempts, state, output) -> bool:
        # WHERE run_id AND user_id AND status = 'running' AND attempts = <mine>
        if not self._owned(run_id, user_id):
            return False
        if self.run["status"] != "running" or self.run["attempts"] != attempts:
            return False
        self.run.update(
            status="finished",
            state=_json(dump_state(state)),
            output=_json(dump_output(output)),
            retryable=False,
            failure_stage=None,
            updated_at=datetime.now(timezone.utc),
        )
        self.writes.append(f"r3_runs: running -> finished, output {len(json.dumps(self.run['output']))} chars")
        return True

    async def insert_step(self, run_id, step_id, state) -> bool:
        if step_id in self.steps:
            return False
        self.steps[step_id] = {"status": "completed", "output": _json(dump_step_output(step_id, state))}
        self.writes.append(f"r3_run_steps[{step_id}]: inserted completed")
        return True

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
            output=load_output(self.run["output"]) if self.run["output"] is not None else None,
            failure_stage=self.run["failure_stage"],
            steps={
                step_id: R3StepRecord(step_id, row["status"], row.get("error_type"), row.get("retryable"))
                for step_id, row in self.steps.items()
            },
        )


class _NoR2Reads:
    """The status read and the finish write never read R2; reaching this is a runner bug."""

    async def get_finished_output(self, run_id: str, user_id: str):
        raise AssertionError("R2 is not read in this runner")


class _RecordCollector(logging.Handler):
    """Keeps the coordinator's structured records so this script can print them."""

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


def _label(key: tuple[int, str]) -> str:
    return f"cat {key[0]} · {_NAMES[key[1]]}"


def _print_event(event: dict) -> None:
    fields = {k: v for k, v in event.items() if k not in ("timestamp", "user_id")}
    print(json.dumps(fields, default=str))


async def run_sample() -> bool:
    configure_logging("INFO")
    collector = _RecordCollector()
    logging.getLogger(DEEP_SEARCH_LOGGER_NAME).addHandler(collector)

    state = _seed_state()
    rows = _MemoryRunRows(state)
    coordinator = R3RunCoordinator(rows, _NoR2Reads(), service_factory=_no_service)

    _section("1. SEEDED STATE (as STEP 5 leaves it)")
    for key, record in state.resolution_results.items():
        verdict = state.website_search_results.get(key)
        shown = "no verdict" if verdict is None else f"{verdict.website_origin} {verdict.website_url!r}"
        print(f"{_label(key):<38} outcome={record.outcome:<15} website: {shown}")

    _section("2. PAIRING (_result_rows) + FINISH WRITE (_save_finished)")
    paired, missing = R3RunCoordinator._result_rows(state)
    for key, row in paired.items():
        print(f"{_label(key):<38} -> url={row.website.website_url!r} origin={row.website.website_origin}")
    print(f"fallback keys: {missing}")
    execution = _Execution(_RUN_ID, _USER_ID, 0, frozenset(), path="start")
    await coordinator._save_finished(execution, state, _Progress(in_flight="pipelines"))
    for line in rows.writes:
        print(line)
    for event in collector.events("r3_run.website_missing", "r3_run.finished"):
        _print_event(event)

    _section("3. STORED OUTPUT (r3_runs.output)")
    stored = rows.run["output"]
    print(f"version={stored['version']} rows={len(stored['output'])}")
    for entry in stored["output"]:
        print(f"{list(entry)}  category_id={entry['category_id']} place_id={entry['place_id']} "
              f"website={json.dumps(entry['website'])}")

    _section("4. LOAD_OUTPUT ROUND TRIP")
    loaded = load_output(stored)
    for key, row in paired.items():
        print(f"{_label(key):<38} equal={loaded.get(key) == row}")

    _section("5. STATUS READ (get_run)")
    view = await coordinator.get_run(_USER_ID, _RUN_ID)
    print(f"status={view.status} completed_step={view.completed_step} rows={len(view.result or [])}")
    for entry in view.result or []:
        print(f"place_id={entry['place_id']:<34} website={json.dumps(entry['website'])}")

    _section("6. HTTP BODY (_run_response, value shortened to its outcome)")
    response = _run_response(view, 200)
    body = json.loads(response.body)
    for entry in body["result"]:
        entry["value"] = {"outcome": entry["value"]["outcome"], "...": "..."}
    print(json.dumps(body, indent=2))

    _section("7. A RUN FINISHED BEFORE THIS CHANGE (output version 1)")
    rows.run["output"]["version"] = 1
    old_view = await coordinator.get_run(_USER_ID, _RUN_ID)
    print(f"status={old_view.status} retryable={old_view.retryable} result={old_view.result}")
    for event in collector.events("r3_run.status_degraded"):
        _print_event(event)
    return True


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
