"""Dummy-input fixtures for R2 Mechanism 1 Component M1.3 (deterministic result attachment).

No client and no live call: M1.3 is a pure in-memory transform. These assert the code-path rules
the live sample runner cannot prove deterministically (projection null-on-missing, unit conversion
and rounding, the join, the versioned envelope, and the assembly error).
"""

import pytest

from src.exceptions.deep_search import ResultAssemblyError
from src.services.deep_search.amenity_search import AmenitySearch
from src.services.deep_search.feature_schemas.schemas import (
    AMENITY_RECORD_CONTRACT_VERSION,
    ROUTING_MODES,
    AmenityRecordSet,
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


def _search() -> AmenitySearch:
    # M1.3 methods never touch the clients, so None is a safe stand-in.
    return AmenitySearch(places_client=None, routes_client=None)


def _plan(category_id: int, node: str, depth: str) -> CategoryMetricPlan:
    return CategoryMetricPlan(
        category_id=category_id,
        taxonomy_node=node,
        depth=depth,
        predefined_metrics=[],
        specific_metrics=[],
    )


def _canonical(place_id: str, place: dict) -> CanonicalPlace:
    return CanonicalPlace(place_id=place_id, place=place)


_FULL_PLACE = {
    "id": "p1",
    "display_name": {"text": "Central Bakery"},
    "primary_type": "bakery",
    "formatted_address": "1 Main St",
    "website_uri": "https://cb.example",
    "google_maps_uri": "https://maps.example/p1",
    "location": {"latitude": 50.1, "longitude": 8.6},
    "regular_opening_hours": {"open_now": True},
    "international_phone_number": "+49 100",
    "rating": 4.5,
    "user_rating_count": 210,
    "price_level": "PRICE_LEVEL_MODERATE",
    "reviews": [{"text": "good"}],
}


# --------------------------------------------------------------------------- Stage a


def test_projection_extracts_nested_and_keys_snake_case() -> None:
    profile = _search().project_place_profile(_FULL_PLACE)

    assert profile["name"] == "Central Bakery"  # display_name.text
    assert profile["category"] == "bakery"  # primary_type
    assert profile["address"] == "1 Main St"  # formatted_address
    assert profile["google_maps_uri"] == "https://maps.example/p1"
    assert profile["review_volume"] == 210  # user_rating_count
    assert profile["contact_phone"] == "+49 100"  # international_phone_number
    assert profile["coordinates"] == GeoPoint(latitude=50.1, longitude=8.6)
    assert profile["opening_hours"] == {"open_now": True}
    assert profile["reviews"] == [{"text": "good"}]


def test_projection_missing_fields_become_none() -> None:
    profile = _search().project_place_profile(
        {"id": "p2", "display_name": {"text": "Corner Bake"}, "primary_type": "bakery"}
    )

    assert profile["name"] == "Corner Bake"
    assert profile["category"] == "bakery"
    # Every absent field is null, never a default or an empty object.
    for key in (
        "address",
        "website",
        "google_maps_uri",
        "coordinates",
        "opening_hours",
        "contact_phone",
        "rating",
        "review_volume",
        "price_level",
        "reviews",
    ):
        assert profile[key] is None


def test_projection_missing_location_gives_null_coordinates() -> None:
    profile = _search().project_place_profile({"id": "p3", "location": {"latitude": 50.1}})
    assert profile["coordinates"] is None


# --------------------------------------------------------------------------- Stage b


def test_route_conversion_rounds_to_two_decimals() -> None:
    view = _search().convert_route_leg(RouteLeg(distance_m=1234, duration_s=95))
    assert view == RouteView(distance_km=1.23, duration_min=1.58)
    assert isinstance(view.distance_km, float) and isinstance(view.duration_min, float)


def test_none_legs_convert_to_none() -> None:
    search = _search()
    assert search.convert_route_leg(None) is None
    assert search.convert_transit_leg(None) is None


def test_transit_conversion_carries_used_fallback() -> None:
    view = _search().convert_transit_leg(
        TransitLeg(distance_m=2000, duration_s=780, used_fallback=True)
    )
    assert view == TransitView(distance_km=2.0, duration_min=13.0, used_fallback=True)


def test_accessibility_keeps_every_mode_and_maps_none() -> None:
    bundle = EnrichmentBundle(
        place_id="p1",
        routing={
            "walk": RouteLeg(distance_m=500, duration_s=300),
            "drive": RouteLeg(distance_m=1500, duration_s=360),
            "cycle": None,
        },
        transit=None,
    )
    routing_map, transit_view = _search().convert_accessibility(bundle)

    assert set(routing_map) == set(ROUTING_MODES)
    assert routing_map["walk"] == RouteView(distance_km=0.5, duration_min=5.0)
    assert routing_map["cycle"] is None
    assert transit_view is None


def test_accessibility_none_bundle_is_all_null() -> None:
    routing_map, transit_view = _search().convert_accessibility(None)
    assert set(routing_map) == set(ROUTING_MODES)
    assert all(view is None for view in routing_map.values())
    assert transit_view is None


# --------------------------------------------------------------------------- Stage c


def _state_two_places() -> AmenitySearchState:
    return AmenitySearchState(
        origin=GeoPoint(latitude=50.1, longitude=8.6),
        radius_km=2.0,
        category_metric_plans=[
            _plan(0, "bakery", "operating_details"),
            _plan(1, "park", "basic_profile"),
        ],
        discovered_places={
            0: {"p1": _canonical("p1", _FULL_PLACE)},
            1: {"missing": _canonical("missing", {"id": "missing", "primary_type": "park"})},
        },
        enrichment={
            "p1": EnrichmentBundle(
                place_id="p1",
                routing={
                    "walk": RouteLeg(distance_m=300, duration_s=240),
                    "drive": RouteLeg(distance_m=1200, duration_s=300),
                    "cycle": RouteLeg(distance_m=800, duration_s=360),
                },
                transit=TransitLeg(distance_m=1500, duration_s=600, used_fallback=False),
            )
        },
    )


def test_assembly_keys_by_category_then_place() -> None:
    record_set = _search().assemble_amenity_records(_state_two_places())

    assert isinstance(record_set, AmenityRecordSet)
    assert set(record_set.records) == {0, 1}
    assert set(record_set.records[0]) == {"p1"}
    record = record_set.records[0]["p1"]
    assert record.category_id == 0
    assert record.taxonomy_node == "bakery"  # from the plan
    assert record.depth == "operating_details"  # from the plan
    assert record.routing["walk"] == RouteView(distance_km=0.3, duration_min=4.0)
    assert record.transit == TransitView(distance_km=1.5, duration_min=10.0, used_fallback=False)


def test_place_absent_from_enrichment_is_all_null_not_skipped() -> None:
    record_set = _search().assemble_amenity_records(_state_two_places())

    assert "missing" in record_set.records[1]  # record built, not skipped
    record = record_set.records[1]["missing"]
    assert set(record.routing) == set(ROUTING_MODES)
    assert all(view is None for view in record.routing.values())
    assert record.transit is None


def test_envelope_versioned_and_record_has_no_version() -> None:
    record_set = _search().assemble_amenity_records(_state_two_places())
    assert record_set.contract_version == AMENITY_RECORD_CONTRACT_VERSION
    record = record_set.records[0]["p1"]
    assert not hasattr(record, "contract_version")


def test_run_writes_envelope_and_retains_enrichment() -> None:
    state = _state_two_places()
    before = dict(state.enrichment)

    returned = _search().run_result_attachment(state)

    assert returned is state
    assert isinstance(state.amenity_records, AmenityRecordSet)
    assert state.enrichment == before  # retained, not cleared


def test_missing_plan_for_discovered_category_raises() -> None:
    state = _state_two_places()
    # A discovered category with no matching plan.
    state.category_metric_plans = [_plan(0, "bakery", "operating_details")]

    with pytest.raises(ResultAssemblyError) as info:
        _search().assemble_amenity_records(state)
    assert info.value.stage == "assemble_amenity_records"
