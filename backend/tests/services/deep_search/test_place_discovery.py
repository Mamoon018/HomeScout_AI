import math

import pytest
from google.api_core import exceptions as google_exceptions
from google.maps import places_v1

from src.clients import google_places
from src.exceptions.deep_search import (
    PlaceDiscoveryCallError,
    PlaceDiscoveryRequestError,
)
from src.exceptions.places import PlacesTimeoutError
from src.services.deep_search.amenity_search import AmenitySearch
from src.services.deep_search.feature_schemas.schemas import (
    DISCOVERY_MAX_RESULTS,
    AmenitySearchState,
    CategoryMetricPlan,
    GeoPoint,
    PREDEFINED_METRICS_BY_DEPTH,
)


def _plan(category_id: int = 0, node: str = "bakery", depth: str = "operating_details") -> CategoryMetricPlan:
    return CategoryMetricPlan(
        category_id=category_id,
        taxonomy_node=node,
        depth=depth,
        predefined_metrics=list(PREDEFINED_METRICS_BY_DEPTH[depth]),
        specific_metrics=[],
    )


def _response(place_ids: list[str]) -> places_v1.SearchNearbyResponse:
    return places_v1.SearchNearbyResponse(
        places=[places_v1.Place(id=place_id) for place_id in place_ids]
    )


class _FakePlacesClient:
    """Async stand-in for GooglePlacesAsyncClient; records calls and tracks concurrency."""

    def __init__(self, response: places_v1.SearchNearbyResponse | None = None) -> None:
        self._response = response if response is not None else _response(["p1"])
        self.calls: list[dict] = []
        self._active = 0
        self.max_active = 0

    async def search_nearby_discovery(self, **kwargs) -> places_v1.SearchNearbyResponse:
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        self.calls.append(kwargs)
        try:
            import asyncio

            await asyncio.sleep(0)
            return self._response
        finally:
            self._active -= 1

    async def aclose(self) -> None:
        pass


def test_field_mask_excludes_routing_and_transit() -> None:
    search = AmenitySearch(_FakePlacesClient())
    request = search.build_discovery_request(_plan(depth="operating_details"), GeoPoint(1.0, 2.0), 2.0)

    assert "places.displayName" in request.field_mask
    assert "places.id" in request.field_mask
    assert "places.rating" in request.field_mask  # operating_details band field
    assert "routingSummaries" not in request.field_mask
    assert "Routes API" not in request.field_mask
    assert request.radius_meters == 2000.0
    assert request.max_result_count == DISCOVERY_MAX_RESULTS
    assert request.primary_type == "bakery"


def test_basic_profile_mask_has_no_operating_fields() -> None:
    search = AmenitySearch(_FakePlacesClient())
    request = search.build_discovery_request(_plan(depth="basic_profile"), GeoPoint(1.0, 2.0), 2.0)

    assert "places.id" in request.field_mask
    assert "places.rating" not in request.field_mask
    assert "places.regularOpeningHours" not in request.field_mask


def test_build_rejects_bad_inputs() -> None:
    search = AmenitySearch(_FakePlacesClient())
    with pytest.raises(PlaceDiscoveryRequestError):
        search.build_discovery_request(_plan(), GeoPoint(math.nan, 2.0), 2.0)
    with pytest.raises(PlaceDiscoveryRequestError):
        search.build_discovery_request(_plan(), GeoPoint(1.0, 2.0), 0.0)
    with pytest.raises(PlaceDiscoveryRequestError):
        search.build_discovery_request(_plan(node="   "), GeoPoint(1.0, 2.0), 2.0)


@pytest.mark.asyncio
async def test_dedup_within_category() -> None:
    search = AmenitySearch(_FakePlacesClient(_response(["p1", "p1", "p2"])))
    request = search.build_discovery_request(_plan(), GeoPoint(1.0, 2.0), 2.0)
    response = await search.execute_discovery(request)
    canonical = search.assemble_canonical_places(response)

    assert set(canonical) == {"p1", "p2"}
    assert canonical["p1"].place_id == "p1"


@pytest.mark.asyncio
async def test_call_failure_raises_typed() -> None:
    class _Boom:
        async def search_nearby_discovery(self, **kwargs) -> places_v1.SearchNearbyResponse:
            raise PlacesTimeoutError("boom")

        async def aclose(self) -> None:
            pass

    search = AmenitySearch(_Boom())
    request = search.build_discovery_request(_plan(), GeoPoint(1.0, 2.0), 2.0)
    with pytest.raises(PlaceDiscoveryCallError) as info:
        await search.execute_discovery(request)
    assert info.value.stage == "execute_discovery"


@pytest.mark.asyncio
async def test_concurrency_bounded() -> None:
    fake = _FakePlacesClient()
    search = AmenitySearch(fake, max_concurrency=3)
    plans = [_plan(category_id=index) for index in range(10)]
    state = AmenitySearchState(
        origin=GeoPoint(1.0, 2.0),
        radius_km=2.0,
        category_metric_plans=plans,
    )

    await search.run_place_discovery(state)

    assert fake.max_active <= 3
    assert len(state.discovered_places) == 10


@pytest.mark.asyncio
async def test_client_retries_transient_then_succeeds(monkeypatch) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(google_places.asyncio, "sleep", _fake_sleep)

    class _SDK:
        def __init__(self) -> None:
            self.attempts = 0

        async def search_nearby(self, **kwargs) -> places_v1.SearchNearbyResponse:
            self.attempts += 1
            if self.attempts < 3:
                raise google_exceptions.ServiceUnavailable("try again")
            return _response(["p1"])

    client = google_places.GooglePlacesAsyncClient(_SDK())
    response = await client.search_nearby_discovery(
        latitude=1.0,
        longitude=2.0,
        radius_meters=2000.0,
        primary_type="bakery",
        field_mask="places.id",
        max_result_count=3,
    )

    assert [place.id for place in response.places] == ["p1"]
    assert sleeps == [2.0, 3.0]


@pytest.mark.asyncio
async def test_client_exhausts_to_timeout(monkeypatch) -> None:
    async def _fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(google_places.asyncio, "sleep", _fake_sleep)

    class _SDK:
        async def search_nearby(self, **kwargs) -> places_v1.SearchNearbyResponse:
            raise google_exceptions.ServiceUnavailable("down")

    client = google_places.GooglePlacesAsyncClient(_SDK())
    with pytest.raises(PlacesTimeoutError):
        await client.search_nearby_discovery(
            latitude=1.0,
            longitude=2.0,
            radius_meters=2000.0,
            primary_type="bakery",
            field_mask="places.id",
            max_result_count=3,
        )
