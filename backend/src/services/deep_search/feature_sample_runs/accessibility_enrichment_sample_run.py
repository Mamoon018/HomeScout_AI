"""Manual, stage-by-stage run of R2 Mechanism 1 Component M1.2 (accessibility enrichment).

Not a test: it asserts nothing and writes nothing to disk. It seeds an `AmenitySearchState`
as after Component M1.1 by loading a real M1.1 `discovered_places` capture
(`data/m1_1_discovered_places.json`, byte-identical to the discovery sample run's output,
including full reviews) so M1.1 is not re-invoked. Because M1.2.a re-issues the same category
search near the same origin and joins routing back by `place_id`, the seed reproduces that exact
discovery: the same origin (50.130034, 8.628251), radius (2 km), and the two plans
(swimming_pool / operating_details and bakery / basic_profile) that produced the frozen set. The
runner then calls the M1.2 stage methods in sequence rather than `run_accessibility_enrichment`,
so every intermediate object can be printed. The Google call log is read back off
PLACES_LOGGER_NAME with a collecting handler, the same technique the discovery runner uses.

From `backend/` (needs GOOGLE_MAPS_API in the environment and network access):
    python -m src.services.deep_search.feature_sample_runs.accessibility_enrichment_sample_run
"""

import asyncio
import json
import logging
import pathlib
import sys

from src.core.config import get_settings
from src.core.logging import PLACES_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import AccessibilityEnrichmentError
from src.services.deep_search.amenity_search import (
    ENRICHMENT_MODE_EVENT,
    ENRICHMENT_TRANSIT_EVENT,
    create_amenity_search,
)
from src.services.deep_search.feature_schemas.schemas import (
    DEFAULT_RADIUS_KM,
    PREDEFINED_METRICS_BY_DEPTH,
    Absence,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    RouteLeg,
    TransitLeg,
)

_RULE = "=" * 78

# The exact origin the M1.1 discovery sample used to produce data/m1_1_discovered_places.json.
# It MUST match, or the M1.2.a re-search returns a different place set and the join by place_id
# finds nothing.
_ORIGIN = GeoPoint(latitude=50.130034, longitude=8.628251)

_DISCOVERED_PLACES_PATH = (
    pathlib.Path(__file__).parent / "data" / "m1_1_discovered_places.json"
)


def _load_discovered_places() -> dict[int, dict[str, CanonicalPlace]]:
    """Load the real M1.1 output capture into the frozen `discovered_places` shape."""
    raw = json.loads(_DISCOVERED_PLACES_PATH.read_text(encoding="utf-8"))
    return {
        int(category_id): {
            place_id: CanonicalPlace(place_id=place_id, place=place)
            for place_id, place in places.items()
        }
        for category_id, places in raw.items()
    }


def _build_sample_state() -> AmenitySearchState:
    """Seed state as after M1.1: the real discovered set plus the plans/origin that produced it."""
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
        discovered_places=_load_discovered_places(),
    )


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


def _describe_route(value: RouteLeg | Absence) -> dict:
    if isinstance(value, RouteLeg):
        return {"distance_m": value.distance_m, "duration_s": value.duration_s}
    return {"absent": value.reason}


def _describe_transit(value: TransitLeg | Absence) -> dict:
    if isinstance(value, TransitLeg):
        return {
            "distance_m": value.distance_m,
            "duration_s": value.duration_s,
            "used_fallback": value.used_fallback,
        }
    return {"absent": value.reason}


def _describe_bundle(bundle) -> dict:
    return {
        "routing": {mode: _describe_route(leg) for mode, leg in bundle.routing.items()},
        "transit": _describe_transit(bundle.transit),
    }


async def run_sample_enrichment() -> AmenitySearchState:
    """Run the M1.2 stages in order, printing what each one produced."""
    settings = get_settings()
    configure_logging(settings.log_level)

    places_logger = logging.getLogger(PLACES_LOGGER_NAME)
    places_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    places_logger.addHandler(collector)

    search = create_amenity_search(settings)
    try:
        state = _build_sample_state()

        _section("INPUT STATE (seeded from a real M1.1 capture)")
        print(
            json.dumps(
                {
                    "origin": {"latitude": state.origin.latitude, "longitude": state.origin.longitude},
                    "radius_km": state.radius_km,
                    "plans": [
                        {"category_id": plan.category_id, "taxonomy_node": plan.taxonomy_node, "depth": plan.depth}
                        for plan in state.category_metric_plans
                    ],
                    "discovered_place_ids": {
                        str(category_id): list(canonical)
                        for category_id, canonical in state.discovered_places.items()
                    },
                },
                indent=2,
            )
        )
        print("M1.1 was not called; discovered_places was loaded from the M1.1 capture.")

        _section("INPUT STATE - discovered_places (FULL CanonicalPlace)")
        print(
            json.dumps(
                {
                    str(category_id): {
                        place_id: canonical_place.place
                        for place_id, canonical_place in canonical.items()
                    }
                    for category_id, canonical in state.discovered_places.items()
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        _section("STAGE 0 - build_unique_place_index")
        place_index = search.build_unique_place_index(state.discovered_places)
        print(
            json.dumps(
                {
                    place_id: {"latitude": point.latitude, "longitude": point.longitude}
                    for place_id, point in place_index.items()
                },
                indent=2,
            )
        )
        print(f"unique place count (deduped union): {len(place_index)}")

        _section("STAGE a - retrieve_mode_routing (walk / drive / cycle)")
        routing = await search.retrieve_mode_routing(state, place_index)
        print(
            json.dumps(
                {
                    place_id: {mode: _describe_route(leg) for mode, leg in modes.items()}
                    for place_id, modes in routing.items()
                },
                indent=2,
            )
        )
        print(
            "per (category, mode) re-search leg counts: "
            f"{[(e['category_id'], e['mode'], e['leg_count']) for e in collector.events(ENRICHMENT_MODE_EVENT)]}"
        )

        _section("STAGE b - retrieve_transit (computeRouteMatrix TRANSIT)")
        transit = await search.retrieve_transit(place_index, state.origin)
        print(
            json.dumps(
                {place_id: _describe_transit(value) for place_id, value in transit.items()},
                indent=2,
            )
        )
        print(
            "transit batch element counts: "
            f"{[e['element_count'] for e in collector.events(ENRICHMENT_TRANSIT_EVENT)]}"
        )

        _section("STAGE c - assemble_enrichment_bundles")
        bundles = search.assemble_enrichment_bundles(list(place_index), routing, transit)
        state.enrichment.update(bundles)
        print(
            json.dumps(
                {place_id: _describe_bundle(bundle) for place_id, bundle in bundles.items()},
                indent=2,
            )
        )
        print(f"bundle count (one per unique place_id): {len(bundles)}")

        _section("STATE.ENRICHMENT (FINAL - written onto the handoff state)")
        print(
            json.dumps(
                {place_id: _describe_bundle(bundle) for place_id, bundle in state.enrichment.items()},
                indent=2,
            )
        )
        print(f"state.enrichment entries: {len(state.enrichment)}")
        return state
    finally:
        await search.aclose()


def main() -> int:
    try:
        asyncio.run(run_sample_enrichment())
    except AccessibilityEnrichmentError as exc:
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {exc.stage}")
        print(f"message:   {exc}")
        return 1
    return 0


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


if __name__ == "__main__":
    sys.exit(main())
