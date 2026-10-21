"""Manual, stage-by-stage run of R3.M1.3 — website-URL discovery (Stage 0 gate + Stage 1 search).

Not a test: it asserts via prints and an exit code but writes nothing to disk. It drives the real
R3.M1.3 stage methods on `SpecificMetricResolution` in sequence over dummy handoff state seeded as
after M1.3 (two `PredefinedMetricsRecord`s + their `discovered_places` + one eligible
`CategoryMetricPlan`). No earlier mechanism is called.

Two work items, chosen to exercise both stages with one billed search:
- a gate-`official` item (its Google website passes `official_url_gate`) → NO search runs; and
- a gate-declined item (empty Google website) → one LIVE `web_search` + a LIVE structured
  selection turn → a `discovered` URL or `none`.
The seeded venues are fresh (not reused from any prompt worked pair or the R3.M1.1 runner's seed),
so the live turns are a new judgement, not a replay.

LIVE: the C3.1.1 gateway `open()` + `tools/list`, one billed Parallel `web_search`, and the two
C3.1.2 LLM turns (discovery `call_turn`, selection `call_structured`). If no provider can complete
a turn, the stage method degrades that item to `none` (D5) and the run still completes and reports
it honestly.

From `backend/` (needs PARALLEL_API_KEY for open() + the billed search; OPENAI_API_KEY/GROQ_API_KEY
for the two LLM turns):
    python -m src.services.deep_search.feature_sample_runs.r3_m1_3_website_url_discovery_sample_run
"""

import asyncio
import json
import logging
import sys
from uuid import uuid4

from src.clients.llm_provider import create_structured_llm_caller
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.mcp import McpGatewayError
from src.services.deep_search.specific_metric_resolution import SpecificMetricResolution
from src.clients.mcp_tools import create_mcp_tool_gateway
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    PredefinedMetricsRecord,
)

_RULE = "=" * 78


class _RecordCollector(logging.Handler):
    """Keeps the deep-search structured records so each stage can print its log trail."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except (json.JSONDecodeError, TypeError):
            pass

    def events(self, *names: str) -> list[dict]:
        return [r for r in self.records if r.get("event") in names]


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


def _print_events(collector: _RecordCollector, *names: str) -> None:
    for record in collector.events(*names):
        print(f"  log: {json.dumps(record, ensure_ascii=False)}")


def _rec(category_id, place_id, name, website, address) -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=category_id,
        taxonomy_node="museum",
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


def _seed_state() -> AmenitySearchState:
    """Dummy handoff state as after M1.3: one gate-official venue + one declined (empty website)."""
    plan = CategoryMetricPlan(1, "museum", "specific_attributes", [], [object()])
    place = CanonicalPlace("x", {})
    official = _rec(
        1,
        "rijks",
        "Rijksmuseum",
        "https://www.rijksmuseum.nl",
        "Museumstraat 1, 1071 XX Amsterdam, Netherlands",
    )
    declined = _rec(
        1,
        "sightglass",
        "Sightglass Coffee",
        "",  # empty Google website → gate declines → live discovery
        "270 7th St, San Francisco, CA 94103, USA",
    )
    return AmenitySearchState(
        origin=GeoPoint(52.36, 4.885),
        radius_km=2.0,
        category_metric_plans=[plan],
        discovered_places={1: {"rijks": place, "sightglass": place}},
        predefined_records={1: {"rijks": official, "sightglass": declined}},
    )


async def run(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    settings = get_settings()
    configure_logging(settings.log_level)
    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    gateway = create_mcp_tool_gateway(settings)
    caller = create_structured_llm_caller(settings)
    service = SpecificMetricResolution(
        tool_gateway=gateway, llm_caller=caller, owns_caller=False
    )
    state = _seed_state()
    batch_id = uuid4().hex
    passed = True

    try:
        _section("STAGE: seed state (as after M1.3)")
        for category_id, places in state.predefined_records.items():
            for place_id, rec in places.items():
                print(f"  ({category_id}, {place_id}): name={rec.name!r} website={rec.website!r}")

        _section("STEP 0: open gateway + capture raw tool definitions")
        await gateway.open()
        raw_tool_definitions = gateway.get_tool_definitions()
        _print_events(collector, "mcp.tools_listed")
        print(f"  servers={sorted(raw_tool_definitions)}  "
              f"parallel_tools={sorted(raw_tool_definitions.get('parallel', {}))}")

        _section("STEP 1: build_plan_index")
        plan_index = service._build_plan_index(state)
        print(f"  plan_index keys: {sorted(plan_index)}")

        _section("STEP 2: derive work items (RC7)")
        work_items = service._derive_work_items(state, plan_index)
        for wi in work_items:
            print(f"  work item: ({wi.category_id}, {wi.place_id})  node={wi.taxonomy_node}")

        _section("STEP 3 / STAGE 0: official_url_gate pre-pass (all items)")
        declined = service._discovery_pre_pass(state, work_items, batch_id)
        # Objects finalized in the pre-pass: an OfficialGateRecord for EVERY item, and a
        # WebsiteSearchResult for each gate-`official` (google) and missing-record (none) item.
        _print_events(collector, "r3m1_3.object_finalized", "r3m1_3.discovery_degraded")
        for key, gate in state.official_gate_results.items():
            print(f"  gate ({key[0]}, {key[1]}): verdict={gate.verdict} "
                  f"reason={gate.reason_code} sld={gate.sld} compact_name={gate.compact_name}")
        for key, verdict in state.website_search_results.items():
            print(f"  verdict ({key[0]}, {key[1]}): origin={verdict.website_origin} "
                  f"url={verdict.website_url!r}")
        print(f"  declined (go to Stage 1): {[(w.category_id, w.place_id) for w in declined]}")

        for wi in declined:
            key = (wi.category_id, wi.place_id)
            rec = state.predefined_records[wi.category_id][wi.place_id]

            _section(f"STEP 3 / STAGE 1: discovery for ({key[0]}, {key[1]}) — {rec.name!r}")
            # Drive the real stage method so each R3.M1.3 object is finalized (and logged) exactly
            # where it truly is: catalog → call_turn → guard → search (+retry) → index candidates →
            # select → resolve verdict → build telemetry.
            verdict, telemetry = await service._discover_website_url(
                wi, rec, raw_tool_definitions, batch_id
            )
            # The stage's full trail: catalog + guard (R3.M1.1), provider attempts and the selection
            # raw body (C3.1.2), any search retry (C3.1.1), each finalized R3.M1.3 object, any degrade.
            _print_events(
                collector,
                "r3m1_1.catalog_built",
                "r3m1_1.guard_decision",
                "llm_provider.attempt",
                "llm_provider.raw_body",
                "mcp.call_attempt_failed",
                "r3m1_3.object_finalized",
                "r3m1_3.discovery_degraded",
            )
            # The runner plays the STEP-3 merge: write the returned objects to the state stores.
            state.website_search_results[key] = verdict
            if telemetry is not None:
                state.discovery_search_results[key] = telemetry

            print(f"  verdict: origin={verdict.website_origin} url={verdict.website_url!r}")
            if telemetry is not None:
                print(f"  candidates indexed: {len(telemetry.candidates)}")
                for candidate in telemetry.candidates:
                    print(f"    {candidate.id}: {candidate.url}  | {candidate.title}")
                print(f"  selected_id: {telemetry.selected_id!r}  "
                      f"resolved_url: {telemetry.resolved_url!r}")
            else:
                print("  search gave up before producing candidates (degraded → none)")

        _section("RESULT: final discovery stores")
        for key, verdict in state.website_search_results.items():
            print(f"  website_search_results ({key[0]}, {key[1]}): "
                  f"{verdict.website_origin} {verdict.website_url!r}")
        print(f"  discovery_search_results keys: {sorted(state.discovery_search_results)}")
        print(f"  official_gate_results keys:    {sorted(state.official_gate_results)}")

        # RC8: every work item has a verdict after Stage 1.
        all_covered = all(
            (wi.category_id, wi.place_id) in state.website_search_results for wi in work_items
        )
        print(f"  RC8 (every work item has a verdict): {all_covered}")
        passed = all_covered
    except McpGatewayError as exc:
        _section("FAILED — MCP gateway")
        print(f"exception: {type(exc).__name__}  stage={exc.stage}  message={exc}")
        return 1
    finally:
        _section("TEARDOWN — gateway + caller close")
        await gateway.aclose()
        await caller.aclose()
        print("gateway and caller closed")

    _section("RESULT")
    print(f"all checkpoints passed: {passed}")
    return 0 if passed else 1


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
