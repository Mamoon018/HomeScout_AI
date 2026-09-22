"""Manual, stage-by-stage run of R2 Mechanism 1 Component M1.1 (place discovery).

Not a test: it asserts nothing and writes nothing to disk. It seeds an `AmenitySearchState`
as after Responsibility 1 (`category_metric_plans` set, plus a real `origin` and `radius_km`)
so Responsibility 1 is not re-invoked. It then calls the M1.1 stage methods in sequence per
category rather than `run_place_discovery`, so every intermediate object can be printed. The
Places call log is read back off PLACES_LOGGER_NAME with a collecting handler, the same
technique the requirement-interpretation runners use.

From `backend/` (needs GOOGLE_MAPS_API in the environment and network access):
    python -m src.services.deep_search.feature_sample_runs.place_discovery_sample_run
"""

import asyncio
import json
import logging
import sys

from src.core.config import get_settings
from src.core.logging import PLACES_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import PlaceDiscoveryError
from src.services.deep_search.amenity_search import (
    DISCOVERY_REQUEST_EVENT,
    create_amenity_search,
)
from src.services.deep_search.feature_schemas.schemas import (
    DEFAULT_RADIUS_KM,
    PREDEFINED_METRICS_BY_DEPTH,
    AmenitySearchState,
    CategoryMetricPlan,
    GeoPoint,
)

_RULE = "=" * 78

# A real origin with amenities within a 2 km radius. Change freely; this is a sample.
_ORIGIN = GeoPoint(latitude=50.130034, longitude=8.628251)


def _build_sample_state() -> AmenitySearchState:
    plans = [
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
    ]
    return AmenitySearchState(
        origin=_ORIGIN,
        radius_km=DEFAULT_RADIUS_KM,
        category_metric_plans=plans,
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


async def run_sample_place_discovery() -> AmenitySearchState:
    """Run the M1.1 stages in order per category, printing what each one produced."""
    settings = get_settings()
    configure_logging(settings.log_level)

    places_logger = logging.getLogger(PLACES_LOGGER_NAME)
    places_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    places_logger.addHandler(collector)

    search = create_amenity_search(settings)
    try:
        state = _build_sample_state()

        _section("INPUT STATE")
        print(
            json.dumps(
                {
                    "origin": {
                        "latitude": state.origin.latitude,
                        "longitude": state.origin.longitude,
                    },
                    "radius_km": state.radius_km,
                    "plans": [
                        {
                            "category_id": plan.category_id,
                            "taxonomy_node": plan.taxonomy_node,
                            "depth": plan.depth,
                            "predefined_count": len(plan.predefined_metrics),
                        }
                        for plan in state.category_metric_plans
                    ],
                },
                indent=2,
            )
        )
        print("Responsibility 1 was not called. This state is seeded after R1.")

        for plan in state.category_metric_plans:
            _section(f"CATEGORY {plan.category_id} - {plan.taxonomy_node}")

            request = search.build_discovery_request(plan, state.origin, state.radius_km)
            print("DiscoveryRequest:")
            print(
                json.dumps(
                    {
                        "primary_type": request.primary_type,
                        "radius_meters": request.radius_meters,
                        "max_result_count": request.max_result_count,
                        "field_mask": request.field_mask,
                    },
                    indent=2,
                )
            )

            response = await search.execute_discovery(request)
            print(f"\nplaces returned by searchNearby: {len(response.places)}")

            canonical = search.assemble_canonical_places(response)
            state.discovered_places[plan.category_id] = canonical
            print(f"canonical (deduped) place count: {len(canonical)}")
            print("place ids: " + ", ".join(list(canonical)[:10]))

        _section("DISCOVERED PLACES SUMMARY")
        print(
            json.dumps(
                {
                    str(category_id): [
                        canonical_place.place.get("display_name", {}).get("text")
                        for canonical_place in canonical.values()
                    ]
                    for category_id, canonical in state.discovered_places.items()
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        _section("DISCOVERED PLACES (FULL OUTPUT)")
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

        print(
            "\nfield masks used per category: "
            f"{[event['field_mask'] for event in collector.events(DISCOVERY_REQUEST_EVENT)]}"
        )
        return state
    finally:
        await search.aclose()


def main() -> int:
    try:
        asyncio.run(run_sample_place_discovery())
    except PlaceDiscoveryError as exc:
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
