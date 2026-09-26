import asyncio
from datetime import timedelta

import pytest
from google.maps import places_v1, routing_v2

from src.exceptions.deep_search import RoutingRetrievalError, TransitRetrievalError
from src.exceptions.places import PlacesTimeoutError
from src.exceptions.routes import RoutesTimeoutError
from src.services.deep_search.amenity_search import AmenitySearch
from src.services.deep_search.feature_schemas.schemas import (
    ROUTING_MODES,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    EnrichmentBundle,
    GeoPoint,
    RouteLeg,
    TransitLeg,
)


# --------------------------------------------------------------------------- helpers


def _plan(category_id: int, node: str) -> CategoryMetricPlan:
    return CategoryMetricPlan(
        category_id=category_id,
        taxonomy_node=node,
        depth="basic_profile",
        predefined_metrics=[],
        specific_metrics=[],
    )


def _canonical(place_id: str, lat: float, lng: float) -> CanonicalPlace:
    return CanonicalPlace(
        place_id=place_id,
        place={"id": place_id, "location": {"latitude": lat, "longitude": lng}},
    )


def _routing_response(legs: dict[str, tuple[int, int]]) -> places_v1.SearchNearbyResponse:
    """Build a searchNearby response whose routing_summaries are parallel to places."""
    places = []
    summaries = []
    for place_id, (distance_m, duration_s) in legs.items():
        places.append(places_v1.Place(id=place_id))
        summaries.append(
            places_v1.RoutingSummary(
                legs=[{"distance_meters": distance_m, "duration": timedelta(seconds=duration_s)}]
            )
        )
    return places_v1.SearchNearbyResponse(places=places, routing_summaries=summaries)


def _matrix_element(
    destination_index: int,
    *,
    distance_m: int = 0,
    duration_s: int = 0,
    condition=routing_v2.RouteMatrixElementCondition.ROUTE_EXISTS,
    fallback: bool = False,
) -> routing_v2.RouteMatrixElement:
    kwargs = dict(
        origin_index=0,
        destination_index=destination_index,
        condition=condition,
        distance_meters=distance_m,
        duration=timedelta(seconds=duration_s),
    )
    if fallback:
        kwargs["fallback_info"] = routing_v2.FallbackInfo(
            routing_mode=routing_v2.FallbackRoutingMode.FALLBACK_ROUTING_MODE_UNSPECIFIED
        )
    return routing_v2.RouteMatrixElement(**kwargs)


class _FakePlacesClient:
    """Async stand-in that returns a per-mode routing response and tracks concurrency."""

    def __init__(self, per_mode: dict[str, places_v1.SearchNearbyResponse]) -> None:
        self._per_mode = per_mode
        self._active = 0
        self.max_active = 0

    async def search_nearby_routing(self, **kwargs) -> places_v1.SearchNearbyResponse:
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        try:
            await asyncio.sleep(0)
            return self._per_mode[kwargs["travel_mode"]]
        finally:
            self._active -= 1

    async def aclose(self) -> None:
        pass


class _FakeRoutesClient:
    """Async stand-in that returns preset matrix elements per batch and tracks concurrency."""

    def __init__(self, batches: list[list[routing_v2.RouteMatrixElement]]) -> None:
        self._batches = list(batches)
        self.batch_sizes: list[int] = []
        self._active = 0
        self.max_active = 0

    async def compute_route_matrix(self, *, origin, destinations, departure_time):
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        try:
            await asyncio.sleep(0)
            self.batch_sizes.append(len(destinations))
            return self._batches.pop(0)
        finally:
            self._active -= 1

    async def aclose(self) -> None:
        pass


def _search(places_client, routes_client, **kwargs) -> AmenitySearch:
    return AmenitySearch(places_client, routes_client, **kwargs)


# --------------------------------------------------------------------------- Stage a


async def test_routing_matched_by_place_id() -> None:
    per_mode = {
        "walk": _routing_response({"p1": (100, 120), "p2": (200, 240)}),
        "drive": _routing_response({"p1": (150, 60), "p2": (250, 90)}),
        "cycle": _routing_response({"p1": (120, 90), "p2": (220, 130)}),
    }
    search = _search(_FakePlacesClient(per_mode), _FakeRoutesClient([[]]))
    state = AmenitySearchState(
        origin=GeoPoint(1.0, 2.0),
        radius_km=2.0,
        category_metric_plans=[_plan(0, "bakery")],
    )
    index = {"p1": GeoPoint(1.1, 2.1), "p2": GeoPoint(1.2, 2.2)}

    routing = await search.retrieve_mode_routing(state, index)

    assert routing["p1"]["walk"] == RouteLeg(distance_m=100, duration_s=120)
    assert routing["p2"]["drive"] == RouteLeg(distance_m=250, duration_s=90)
    assert set(routing["p1"]) == set(ROUTING_MODES)


async def test_missing_mode_becomes_none_in_bundle() -> None:
    # p2 only appears in the walk result, so drive/cycle are None (no leg) for it.
    per_mode = {
        "walk": _routing_response({"p1": (100, 120), "p2": (200, 240)}),
        "drive": _routing_response({"p1": (150, 60)}),
        "cycle": _routing_response({"p1": (120, 90)}),
    }
    search = _search(_FakePlacesClient(per_mode), _FakeRoutesClient([[]]))
    state = AmenitySearchState(
        origin=GeoPoint(1.0, 2.0),
        radius_km=2.0,
        category_metric_plans=[_plan(0, "bakery")],
    )
    index = {"p1": GeoPoint(1.1, 2.1), "p2": GeoPoint(1.2, 2.2)}

    routing = await search.retrieve_mode_routing(state, index)
    bundles = search.assemble_enrichment_bundles(list(index), routing, {})

    assert bundles["p2"].routing["walk"] == RouteLeg(distance_m=200, duration_s=240)
    assert bundles["p2"].routing["drive"] is None
    assert bundles["p2"].routing["cycle"] is None


async def test_routing_failure_raises_typed() -> None:
    class _Boom:
        async def search_nearby_routing(self, **kwargs):
            raise PlacesTimeoutError("boom")

        async def aclose(self) -> None:
            pass

    search = _search(_Boom(), _FakeRoutesClient([[]]))
    state = AmenitySearchState(
        origin=GeoPoint(1.0, 2.0),
        radius_km=2.0,
        category_metric_plans=[_plan(0, "bakery")],
    )
    with pytest.raises(RoutingRetrievalError) as info:
        await search.retrieve_mode_routing(state, {"p1": GeoPoint(1.1, 2.1)})
    assert info.value.stage == "retrieve_mode_routing"


# --------------------------------------------------------------------------- Stage b


async def test_transit_batches_and_maps_by_destination_index() -> None:
    # 150 places → two batches (100 + 50); each element maps back by destination_index.
    index = {f"p{i}": GeoPoint(1.0 + i / 1000, 2.0 + i / 1000) for i in range(150)}
    batch1 = [_matrix_element(i, distance_m=i, duration_s=i * 2) for i in range(100)]
    batch2 = [_matrix_element(i, distance_m=1000 + i, duration_s=i) for i in range(50)]
    routes = _FakeRoutesClient([batch1, batch2])
    search = _search(_FakePlacesClient({}), routes)

    transit = await search.retrieve_transit(index, GeoPoint(1.0, 2.0))

    assert routes.batch_sizes == [100, 50]
    assert transit["p0"] == TransitLeg(distance_m=0, duration_s=0, used_fallback=False)
    assert transit["p149"] == TransitLeg(distance_m=1049, duration_s=49, used_fallback=False)
    assert len(transit) == 150


async def test_transit_no_route_and_fallback() -> None:
    index = {"p1": GeoPoint(1.1, 2.1), "p2": GeoPoint(1.2, 2.2), "p3": GeoPoint(1.3, 2.3)}
    elements = [
        _matrix_element(0, distance_m=500, duration_s=600),
        _matrix_element(1, condition=routing_v2.RouteMatrixElementCondition.ROUTE_NOT_FOUND),
        _matrix_element(2, distance_m=800, duration_s=900, fallback=True),
    ]
    search = _search(_FakePlacesClient({}), _FakeRoutesClient([elements]))

    transit = await search.retrieve_transit(index, GeoPoint(1.0, 2.0))

    assert transit["p1"] == TransitLeg(distance_m=500, duration_s=600, used_fallback=False)
    assert transit["p2"] is None
    assert transit["p3"] == TransitLeg(distance_m=800, duration_s=900, used_fallback=True)


async def test_transit_failure_raises_typed() -> None:
    class _Boom:
        async def compute_route_matrix(self, **kwargs):
            raise RoutesTimeoutError("boom")

        async def aclose(self) -> None:
            pass

    search = _search(_FakePlacesClient({}), _Boom())
    with pytest.raises(TransitRetrievalError) as info:
        await search.retrieve_transit({"p1": GeoPoint(1.1, 2.1)}, GeoPoint(1.0, 2.0))
    assert info.value.stage == "retrieve_transit"


# --------------------------------------------------------------------------- Stage 0 / c


def test_unique_index_dedups_shared_place_across_categories() -> None:
    search = _search(_FakePlacesClient({}), _FakeRoutesClient([[]]))
    discovered = {
        0: {"shared": _canonical("shared", 1.1, 2.1), "a": _canonical("a", 1.2, 2.2)},
        1: {"shared": _canonical("shared", 1.1, 2.1), "b": _canonical("b", 1.3, 2.3)},
    }

    index = search.build_unique_place_index(discovered)

    assert set(index) == {"shared", "a", "b"}
    assert index["shared"] == GeoPoint(1.1, 2.1)


def test_place_missing_location_is_dropped() -> None:
    search = _search(_FakePlacesClient({}), _FakeRoutesClient([[]]))
    discovered = {0: {"p1": CanonicalPlace(place_id="p1", place={"id": "p1"})}}

    assert search.build_unique_place_index(discovered) == {}


async def test_shared_place_yields_one_bundle_with_all_modes() -> None:
    per_mode = {mode: _routing_response({"shared": (10, 20)}) for mode in ROUTING_MODES}
    routes = _FakeRoutesClient([[_matrix_element(0, distance_m=1, duration_s=2)]])
    search = _search(_FakePlacesClient(per_mode), routes)
    state = AmenitySearchState(
        origin=GeoPoint(1.0, 2.0),
        radius_km=2.0,
        category_metric_plans=[_plan(0, "bakery"), _plan(1, "cafe")],
        discovered_places={
            0: {"shared": _canonical("shared", 1.1, 2.1)},
            1: {"shared": _canonical("shared", 1.1, 2.1)},
        },
    )

    await search.run_accessibility_enrichment(state)

    assert list(state.enrichment) == ["shared"]
    bundle = state.enrichment["shared"]
    assert isinstance(bundle, EnrichmentBundle)
    assert set(bundle.routing) == set(ROUTING_MODES)
    assert isinstance(bundle.transit, TransitLeg)


# --------------------------------------------------------------------------- concurrency


async def test_per_service_concurrency_bounds() -> None:
    # 5 categories × 3 modes = 15 routing calls, plus 3 transit batches, all gathered together.
    per_mode = {mode: _routing_response({"p1": (1, 1)}) for mode in ROUTING_MODES}
    places = _FakePlacesClient(per_mode)
    routes = _FakeRoutesClient([[_matrix_element(0)] for _ in range(3)])
    search = _search(places, routes, places_concurrency=3, routes_concurrency=2)

    index = {f"p{i}": GeoPoint(1.0, 2.0) for i in range(250)}  # 3 batches of ≤100
    state = AmenitySearchState(
        origin=GeoPoint(1.0, 2.0),
        radius_km=2.0,
        category_metric_plans=[_plan(i, "bakery") for i in range(5)],
    )

    await asyncio.gather(
        search.retrieve_mode_routing(state, index),
        search.retrieve_transit(index, state.origin),
    )

    assert places.max_active <= 3
    assert routes.max_active <= 2
