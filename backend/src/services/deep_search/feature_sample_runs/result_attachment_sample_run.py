"""Manual, stage-by-stage run of R2 Mechanism 1 Component M1.3 (deterministic result attachment).

Not a test: it asserts nothing and writes nothing to disk. M1.3 is a pure in-memory transform and
makes no external call, so this runner makes none either. It seeds an `AmenitySearchState` as after
M1.2 (a hand-built `discovered_places` + `enrichment` + `category_metric_plans`) so M1.1 and M1.2
are not re-invoked, then calls the M1.3 stage methods in sequence rather than one opaque call, so
every intermediate object can be printed. The completion event is read back off PLACES_LOGGER_NAME
with a collecting handler, the same technique the discovery and enrichment runners use.

The seed exercises each branch: a place with a full profile and full routing/transit; a place
missing optional fields (null projection); a `basic_profile` category (operating fields not
requested); a place present in `discovered_places` but absent from `enrichment` (all-null
accessibility); a routing mode set to None; transit set to None.

From `backend/` (no API key or network needed):
    python -m src.services.deep_search.feature_sample_runs.result_attachment_sample_run
"""

import json
import logging
import sys

from src.core.logging import PLACES_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import ResultAttachmentError
from src.services.deep_search.amenity_search import (
    ATTACHMENT_COMPLETED_EVENT,
    AmenitySearch,
)
from src.services.deep_search.feature_schemas.schemas import (
    DEFAULT_RADIUS_KM,
    AmenityRecord,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    EnrichmentBundle,
    GeoPoint,
    RouteLeg,
    RouteView,
    TransitLeg,
    TransitView,
)

_RULE = "=" * 78

_ORIGIN = GeoPoint(latitude=50.130034, longitude=8.628251)


def _canonical(place_id: str, place: dict) -> CanonicalPlace:
    return CanonicalPlace(place_id=place_id, place=place)


def _build_sample_state() -> AmenitySearchState:
    """Seed state as after M1.2: discovered places, their enrichment, and the plans that produced them."""
    discovered_places = {
        0: {
            "full-1": _canonical(
                "full-1",
                {
                    "id": "full-1",
                    "display_name": {"text": "Central Bakery"},
                    "primary_type": "bakery",
                    "formatted_address": "1 Main St",
                    "website_uri": "https://central-bakery.example",
                    "google_maps_uri": "https://maps.example/full-1",
                    "location": {"latitude": 50.131, "longitude": 8.629},
                    "regular_opening_hours": {"open_now": True},
                    "international_phone_number": "+49 100 000",
                    "rating": 4.5,
                    "user_rating_count": 210,
                    "price_level": "PRICE_LEVEL_MODERATE",
                    "reviews": [{"text": "Great bread."}],
                },
            ),
            "partial-2": _canonical(
                "partial-2",
                {
                    "id": "partial-2",
                    "display_name": {"text": "Corner Bake"},
                    "primary_type": "bakery",
                    "location": {"latitude": 50.132, "longitude": 8.630},
                },
            ),
        },
        1: {
            "basic-3": _canonical(
                "basic-3",
                {
                    "id": "basic-3",
                    "display_name": {"text": "Green Park"},
                    "primary_type": "park",
                    "google_maps_uri": "https://maps.example/basic-3",
                    "location": {"latitude": 50.133, "longitude": 8.631},
                },
            ),
            "no-enrich-4": _canonical(
                "no-enrich-4",
                {
                    "id": "no-enrich-4",
                    "display_name": {"text": "Hidden Park"},
                    "primary_type": "park",
                    "location": {"latitude": 50.134, "longitude": 8.632},
                },
            ),
        },
    }
    # Union of place_ids across categories. no-enrich-4 is deliberately absent.
    enrichment = {
        "full-1": EnrichmentBundle(
            place_id="full-1",
            routing={
                "walk": RouteLeg(distance_m=300, duration_s=240),
                "drive": RouteLeg(distance_m=1200, duration_s=300),
                "cycle": RouteLeg(distance_m=800, duration_s=360),
            },
            transit=TransitLeg(distance_m=1500, duration_s=600, used_fallback=False),
        ),
        "partial-2": EnrichmentBundle(
            place_id="partial-2",
            routing={
                "walk": RouteLeg(distance_m=500, duration_s=420),
                "drive": RouteLeg(distance_m=1500, duration_s=360),
                "cycle": None,
            },
            transit=None,
        ),
        "basic-3": EnrichmentBundle(
            place_id="basic-3",
            routing={
                "walk": RouteLeg(distance_m=650, duration_s=540),
                "drive": RouteLeg(distance_m=1800, duration_s=420),
                "cycle": RouteLeg(distance_m=1100, duration_s=540),
            },
            transit=TransitLeg(distance_m=2000, duration_s=780, used_fallback=True),
        ),
    }
    return AmenitySearchState(
        origin=_ORIGIN,
        radius_km=DEFAULT_RADIUS_KM,
        category_metric_plans=[
            CategoryMetricPlan(
                category_id=0,
                taxonomy_node="bakery",
                depth="operating_details",
                predefined_metrics=[],
                specific_metrics=[],
            ),
            CategoryMetricPlan(
                category_id=1,
                taxonomy_node="park",
                depth="basic_profile",
                predefined_metrics=[],
                specific_metrics=[],
            ),
        ],
        discovered_places=discovered_places,
        enrichment=enrichment,
    )


class _RecordCollector(logging.Handler):
    """Keeps the service's structured records so this script can print the completion event."""

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


def _describe_coordinates(point: GeoPoint | None) -> dict | None:
    if point is None:
        return None
    return {"latitude": point.latitude, "longitude": point.longitude}


def _describe_profile(profile: dict) -> dict:
    described = dict(profile)
    described["coordinates"] = _describe_coordinates(profile["coordinates"])
    return described


def _describe_route(view: RouteView | None) -> dict | None:
    if view is None:
        return None
    return {"distance_km": view.distance_km, "duration_min": view.duration_min}


def _describe_transit(view: TransitView | None) -> dict | None:
    if view is None:
        return None
    return {
        "distance_km": view.distance_km,
        "duration_min": view.duration_min,
        "used_fallback": view.used_fallback,
    }


def _describe_record(record: AmenityRecord) -> dict:
    return {
        "category_id": record.category_id,
        "taxonomy_node": record.taxonomy_node,
        "depth": record.depth,
        "place_id": record.place_id,
        "name": record.name,
        "category": record.category,
        "address": record.address,
        "website": record.website,
        "google_maps_uri": record.google_maps_uri,
        "coordinates": _describe_coordinates(record.coordinates),
        "opening_hours": record.opening_hours,
        "contact_phone": record.contact_phone,
        "rating": record.rating,
        "review_volume": record.review_volume,
        "price_level": record.price_level,
        "reviews": record.reviews,
        "routing": {mode: _describe_route(view) for mode, view in record.routing.items()},
        "transit": _describe_transit(record.transit),
    }


def run_sample_result_attachment() -> AmenitySearchState:
    """Run the M1.3 stages in order, printing what each one produced."""
    configure_logging("INFO")

    places_logger = logging.getLogger(PLACES_LOGGER_NAME)
    places_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    places_logger.addHandler(collector)

    # M1.3 uses no client and no MCP gateway, so none are built.
    search = AmenitySearch(places_client=None, routes_client=None, tool_gateway=None)
    state = _build_sample_state()

    _section("INPUT STATE (seeded as after M1.2)")
    print(
        json.dumps(
            {
                "plans": [
                    {"category_id": plan.category_id, "taxonomy_node": plan.taxonomy_node, "depth": plan.depth}
                    for plan in state.category_metric_plans
                ],
                "discovered_place_ids": {
                    str(category_id): list(canonical)
                    for category_id, canonical in state.discovered_places.items()
                },
                "enriched_place_ids": list(state.enrichment),
            },
            indent=2,
        )
    )
    print("M1.1/M1.2 were not called; discovered_places and enrichment were seeded.")

    _section("STAGE a - project_place_profile (per discovered place)")
    for category_id, canonical in state.discovered_places.items():
        for place_id, canonical_place in canonical.items():
            profile = search.project_place_profile(canonical_place.place)
            print(f"[category {category_id}] {place_id}:")
            print(json.dumps(_describe_profile(profile), indent=2, ensure_ascii=False))

    _section("STAGE b - convert_accessibility (per enrichment bundle)")
    for place_id, bundle in state.enrichment.items():
        routing_map, transit_view = search.convert_accessibility(bundle)
        print(f"{place_id}:")
        print(
            json.dumps(
                {
                    "routing": {mode: _describe_route(view) for mode, view in routing_map.items()},
                    "transit": _describe_transit(transit_view),
                },
                indent=2,
            )
        )
    print("no-enrich-4 is absent here; M1.3.c gives it an all-null routing map and null transit.")

    _section("STAGE c - run_result_attachment (assemble, join, write envelope)")
    search.run_result_attachment(state)
    record_set = state.amenity_records
    print(f"contract_version: {record_set.contract_version}")
    print(
        json.dumps(
            {
                str(category_id): {
                    place_id: _describe_record(record)
                    for place_id, record in records.items()
                }
                for category_id, records in record_set.records.items()
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    _section("COMPLETION EVENT and RETAINED ENRICHMENT")
    print("completion events: " + json.dumps(collector.events(ATTACHMENT_COMPLETED_EVENT)))
    print(f"state.enrichment still has {len(state.enrichment)} entries (retained, not cleared).")
    return state


def main() -> int:
    try:
        run_sample_result_attachment()
    except ResultAttachmentError as exc:
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
