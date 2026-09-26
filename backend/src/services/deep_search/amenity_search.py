import asyncio
import json
import logging
import math
from datetime import datetime, timezone

from google.maps import places_v1, routing_v2

from src.clients.google_places import (
    GooglePlacesAsyncClient,
    create_places_async_client,
)
from src.clients.google_routes import (
    GoogleRoutesAsyncClient,
    create_routes_async_client,
)
from src.core.config import Settings
from src.core.logging import PLACES_LOGGER_NAME
from src.exceptions.deep_search import (
    PlaceDiscoveryCallError,
    PlaceDiscoveryRequestError,
    RoutingRetrievalError,
    TransitRetrievalError,
)
from src.exceptions.places import PlacesClientError
from src.exceptions.routes import RoutesClientError
from src.services.deep_search.feature_schemas.schemas import (
    DISCOVERY_MAX_RESULTS,
    ROUTING_MODES,
    TRANSIT_MATRIX_MAX_DESTINATIONS,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    DiscoveryRequest,
    EnrichmentBundle,
    GeoPoint,
    RouteLeg,
    TransitLeg,
    TravelModeName,
)

logger = logging.getLogger(PLACES_LOGGER_NAME)

DEFAULT_DISCOVERY_CONCURRENCY = 3
DEFAULT_ROUTES_CONCURRENCY = 3
_METERS_PER_KM = 1000.0
_PLACES_FIELD_PREFIX = "places."

# The sample runner reads these events back off PLACES_LOGGER_NAME to print the stage trail.
DISCOVERY_REQUEST_EVENT = "discovery.request_built"
DISCOVERY_CATEGORY_EVENT = "discovery.category_completed"
ENRICHMENT_MODE_EVENT = "enrichment.mode_completed"
ENRICHMENT_TRANSIT_EVENT = "enrichment.transit_batch_completed"


def _duration_seconds(duration: object) -> int:
    """Read whole seconds from a proto Duration, exposed by proto-plus as a timedelta."""
    total = getattr(duration, "total_seconds", None)
    if callable(total):
        return int(total())
    return int(getattr(duration, "seconds", 0))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class AmenitySearch:
    """Responsibility 2 entry; Mechanism 1 Component M1.1 (place discovery).

    Later mechanisms (M1.2 enrichment, M1.3 attachment, M2 onward) add methods here; they read
    the same `AmenitySearchState` and the same injected Places client.
    """

    def __init__(
        self,
        places_client: GooglePlacesAsyncClient,
        routes_client: GoogleRoutesAsyncClient,
        *,
        places_concurrency: int = DEFAULT_DISCOVERY_CONCURRENCY,
        routes_concurrency: int = DEFAULT_ROUTES_CONCURRENCY,
    ) -> None:
        self._places_client = places_client
        self._routes_client = routes_client
        # Places (discovery + routing re-search) and Routes (transit) hit two services with
        # independent rate limits and run concurrently in M1.2, so each has its own bound.
        # Independent calls overlap their I/O waits; each semaphore caps how many are in flight.
        self._semaphore = asyncio.Semaphore(places_concurrency)
        self._routes_semaphore = asyncio.Semaphore(routes_concurrency)

    async def run_place_discovery(self, state: AmenitySearchState) -> AmenitySearchState:
        """M1.1 workflow: discover a frozen canonical place set per category.

        Category pipelines are independent, so they are scheduled together and gathered; each
        is bounded by the shared semaphore. Results are merged into `state.discovered_places`
        after the tasks resolve, so no two tasks write shared state at once.
        """
        results = await asyncio.gather(
            *(
                self._discover_one_category(plan, state.origin, state.radius_km)
                for plan in state.category_metric_plans
            )
        )
        for category_id, canonical in results:
            state.discovered_places[category_id] = canonical

        logger.info(
            json.dumps(
                {
                    "event": "discovery.completed",
                    "timestamp": _timestamp(),
                    "category_count": len(results),
                    "place_counts": {
                        str(category_id): len(canonical)
                        for category_id, canonical in results
                    },
                }
            )
        )
        return state

    async def _discover_one_category(
        self,
        plan: CategoryMetricPlan,
        origin: GeoPoint,
        radius_km: float,
    ) -> tuple[int, dict[str, CanonicalPlace]]:
        """Drive the three M1.1 stages for one category and return its canonical set."""
        request = self.build_discovery_request(plan, origin, radius_km)
        response = await self.execute_discovery(request)
        canonical = self.assemble_canonical_places(response)
        logger.info(
            json.dumps(
                {
                    "event": DISCOVERY_CATEGORY_EVENT,
                    "timestamp": _timestamp(),
                    "category_id": plan.category_id,
                    "taxonomy_node": plan.taxonomy_node,
                    "place_count": len(canonical),
                }
            )
        )
        return plan.category_id, canonical

    def build_discovery_request(
        self,
        plan: CategoryMetricPlan,
        origin: GeoPoint,
        radius_km: float,
    ) -> DiscoveryRequest:
        """M1.1.a: validate inputs, build the per-category field mask, assemble the call spec."""
        if not _is_finite(origin.latitude) or not _is_finite(origin.longitude):
            raise PlaceDiscoveryRequestError(
                f"origin is not a finite coordinate for category {plan.category_id}",
                stage="build_discovery_request",
            )
        if not _is_finite(radius_km) or radius_km <= 0:
            raise PlaceDiscoveryRequestError(
                f"radius_km must be a positive number for category {plan.category_id}",
                stage="build_discovery_request",
            )
        primary_type = plan.taxonomy_node.strip()
        if not primary_type:
            raise PlaceDiscoveryRequestError(
                f"taxonomy_node is empty for category {plan.category_id}",
                stage="build_discovery_request",
            )

        # Discovery mask is exactly the category's pre-defined `places.*` targets (basic, plus
        # operating for deeper depths) including places.id. Routing (routingSummaries.*) and
        # transit (Routes API) targets are not places.* fields, so they fall out here and stay
        # with M1.2.
        field_targets = [
            metric.resolution_source.target
            for metric in plan.predefined_metrics
            if metric.resolution_source.target.startswith(_PLACES_FIELD_PREFIX)
        ]
        field_mask = ",".join(dict.fromkeys(field_targets))
        if not field_mask:
            raise PlaceDiscoveryRequestError(
                f"no places.* field targets for category {plan.category_id}",
                stage="build_discovery_request",
            )

        request = DiscoveryRequest(
            category_id=plan.category_id,
            primary_type=primary_type,
            latitude=origin.latitude,
            longitude=origin.longitude,
            radius_meters=radius_km * _METERS_PER_KM,
            field_mask=field_mask,
            max_result_count=DISCOVERY_MAX_RESULTS,
        )
        logger.info(
            json.dumps(
                {
                    "event": DISCOVERY_REQUEST_EVENT,
                    "timestamp": _timestamp(),
                    "category_id": request.category_id,
                    "primary_type": request.primary_type,
                    "radius_meters": request.radius_meters,
                    "max_result_count": request.max_result_count,
                    "field_mask": request.field_mask,
                }
            )
        )
        return request

    async def execute_discovery(
        self,
        request: DiscoveryRequest,
    ) -> places_v1.SearchNearbyResponse:
        """M1.1.b: run the bounded, no-routing searchNearby; map a failed call to a typed error."""
        async with self._semaphore:
            try:
                return await self._places_client.search_nearby_discovery(
                    latitude=request.latitude,
                    longitude=request.longitude,
                    radius_meters=request.radius_meters,
                    primary_type=request.primary_type,
                    field_mask=request.field_mask,
                    max_result_count=request.max_result_count,
                )
            except PlacesClientError as exc:
                logger.info(
                    json.dumps(
                        {
                            "event": "discovery.call_failed",
                            "timestamp": _timestamp(),
                            "category_id": request.category_id,
                            "detail": str(exc),
                        }
                    )
                )
                raise PlaceDiscoveryCallError(
                    f"searchNearby discovery failed for category {request.category_id}: {exc}",
                    stage="execute_discovery",
                ) from exc

    def assemble_canonical_places(
        self,
        response: places_v1.SearchNearbyResponse,
    ) -> dict[str, CanonicalPlace]:
        """M1.1.c: dedup by place_id within the category, freeze, fields as returned."""
        canonical: dict[str, CanonicalPlace] = {}
        for place in response.places:
            place_id = place.id
            if not place_id:
                logger.info(
                    json.dumps(
                        {
                            "event": "discovery.place_dropped",
                            "timestamp": _timestamp(),
                            "reason": "missing_place_id",
                        }
                    )
                )
                continue
            if place_id in canonical:
                continue
            canonical[place_id] = CanonicalPlace(
                place_id=place_id,
                place=places_v1.Place.to_dict(place),
            )
        return canonical

    # -----------------------------------------------------------------------------
    # Mechanism 1, Component M1.2 — Accessibility Enrichment.
    # -----------------------------------------------------------------------------

    async def run_accessibility_enrichment(
        self,
        state: AmenitySearchState,
    ) -> AmenitySearchState:
        """M1.2 workflow: enrich the frozen discovered set with routing + transit.

        Stage a (per-mode routing) and Stage b (transit matrix) hit two independent services and
        have no data dependency, so they are dispatched together and gathered; Stage c assembles
        after both resolve. `state.enrichment` is written once, so no two tasks write it at once.
        """
        place_index = self.build_unique_place_index(state.discovered_places)
        if not place_index:
            logger.info(
                json.dumps(
                    {
                        "event": "enrichment.completed",
                        "timestamp": _timestamp(),
                        "place_count": 0,
                    }
                )
            )
            return state

        routing, transit = await asyncio.gather(
            self.retrieve_mode_routing(state, place_index),
            self.retrieve_transit(place_index, state.origin),
        )
        bundles = self.assemble_enrichment_bundles(list(place_index), routing, transit)
        state.enrichment.update(bundles)

        logger.info(
            json.dumps(
                {
                    "event": "enrichment.completed",
                    "timestamp": _timestamp(),
                    "place_count": len(bundles),
                }
            )
        )
        return state

    def build_unique_place_index(
        self,
        discovered_places: dict[int, dict[str, CanonicalPlace]],
    ) -> dict[str, GeoPoint]:
        """M1.2 Stage 0: dedup union of place_ids across categories → each place's location."""
        index: dict[str, GeoPoint] = {}
        for canonical in discovered_places.values():
            for place_id, canonical_place in canonical.items():
                if place_id in index:
                    continue
                location = canonical_place.place.get("location") or {}
                latitude = location.get("latitude")
                longitude = location.get("longitude")
                if latitude is None or longitude is None:
                    logger.info(
                        json.dumps(
                            {
                                "event": "enrichment.place_dropped",
                                "timestamp": _timestamp(),
                                "reason": "missing_location",
                                "place_id": place_id,
                            }
                        )
                    )
                    continue
                index[place_id] = GeoPoint(latitude=latitude, longitude=longitude)
        return index

    async def retrieve_mode_routing(
        self,
        state: AmenitySearchState,
        place_index: dict[str, GeoPoint],
    ) -> dict[str, dict[str, RouteLeg]]:
        """M1.2.a: re-search each category per mode; legs matched by place_id across categories."""
        results = await asyncio.gather(
            *(
                self._route_one_mode(plan, mode, state.origin, state.radius_km)
                for plan in state.category_metric_plans
                for mode in ROUTING_MODES
            )
        )
        routing_by_place: dict[str, dict[str, RouteLeg]] = {}
        for mode, legs in results:
            for place_id, leg in legs.items():
                # A place that appears in more than one category routes into a single bundle;
                # the first result for a (place_id, mode) pair is kept.
                routing_by_place.setdefault(place_id, {}).setdefault(mode, leg)
        return routing_by_place

    async def _route_one_mode(
        self,
        plan: CategoryMetricPlan,
        mode: TravelModeName,
        origin: GeoPoint,
        radius_km: float,
    ) -> tuple[str, dict[str, RouteLeg]]:
        """One category × mode routing re-search; return the mode and its place_id → RouteLeg map."""
        async with self._semaphore:
            try:
                response = await self._places_client.search_nearby_routing(
                    latitude=origin.latitude,
                    longitude=origin.longitude,
                    radius_meters=radius_km * _METERS_PER_KM,
                    primary_type=plan.taxonomy_node,
                    travel_mode=mode,
                    max_result_count=DISCOVERY_MAX_RESULTS,
                )
            except PlacesClientError as exc:
                raise RoutingRetrievalError(
                    f"routing re-search failed for category {plan.category_id} mode {mode}: {exc}",
                    stage="retrieve_mode_routing",
                ) from exc

        legs: dict[str, RouteLeg] = {}
        for place, summary in zip(response.places, response.routing_summaries):
            place_id = place.id
            if not place_id or not summary.legs:
                continue
            leg = summary.legs[0]
            legs[place_id] = RouteLeg(
                distance_m=int(leg.distance_meters),
                duration_s=_duration_seconds(leg.duration),
            )
        logger.info(
            json.dumps(
                {
                    "event": ENRICHMENT_MODE_EVENT,
                    "timestamp": _timestamp(),
                    "category_id": plan.category_id,
                    "mode": mode,
                    "leg_count": len(legs),
                }
            )
        )
        return mode, legs

    async def retrieve_transit(
        self,
        place_index: dict[str, GeoPoint],
        origin: GeoPoint,
    ) -> dict[str, TransitLeg | None]:
        """M1.2.b: batched TRANSIT computeRouteMatrix; each element mapped back to its place_id."""
        place_ids = list(place_index)
        departure_time = datetime.now(timezone.utc)
        batches = [
            place_ids[start : start + TRANSIT_MATRIX_MAX_DESTINATIONS]
            for start in range(0, len(place_ids), TRANSIT_MATRIX_MAX_DESTINATIONS)
        ]
        results = await asyncio.gather(
            *(
                self._transit_one_batch(batch, place_index, origin, departure_time)
                for batch in batches
            )
        )
        transit_by_place: dict[str, TransitLeg | None] = {}
        for partial in results:
            transit_by_place.update(partial)
        return transit_by_place

    async def _transit_one_batch(
        self,
        batch_ids: list[str],
        place_index: dict[str, GeoPoint],
        origin: GeoPoint,
        departure_time: datetime,
    ) -> dict[str, TransitLeg | None]:
        """One matrix batch (≤ cap destinations); map each element back to its place_id."""
        destinations = [
            (place_index[place_id].latitude, place_index[place_id].longitude)
            for place_id in batch_ids
        ]
        async with self._routes_semaphore:
            try:
                elements = await self._routes_client.compute_route_matrix(
                    origin=(origin.latitude, origin.longitude),
                    destinations=destinations,
                    departure_time=departure_time,
                )
            except RoutesClientError as exc:
                raise TransitRetrievalError(
                    f"transit matrix failed for a batch of {len(batch_ids)} places: {exc}",
                    stage="retrieve_transit",
                ) from exc

        result: dict[str, TransitLeg | None] = {}
        for element in elements:
            if not 0 <= element.destination_index < len(batch_ids):
                continue
            place_id = batch_ids[element.destination_index]
            if _element_has_route(element):
                result[place_id] = TransitLeg(
                    distance_m=int(element.distance_meters),
                    duration_s=_duration_seconds(element.duration),
                    used_fallback=_element_used_fallback(element),
                )
            else:
                result[place_id] = None
        # A place whose element never arrived is recorded null rather than dropped.
        for place_id in batch_ids:
            result.setdefault(place_id, None)
        logger.info(
            json.dumps(
                {
                    "event": ENRICHMENT_TRANSIT_EVENT,
                    "timestamp": _timestamp(),
                    "batch_size": len(batch_ids),
                    "element_count": len(elements),
                }
            )
        )
        return result

    def assemble_enrichment_bundles(
        self,
        place_ids: list[str],
        routing: dict[str, dict[str, RouteLeg]],
        transit: dict[str, TransitLeg | None],
    ) -> dict[str, EnrichmentBundle]:
        """M1.2.c: merge routing + transit into one frozen bundle per unique place_id.

        A mode with no leg, or a place with no transit result, is stored as None; the reason for
        absence is not recorded (M1.3 derives it from the record's depth).
        """
        bundles: dict[str, EnrichmentBundle] = {}
        for place_id in place_ids:
            place_routing = routing.get(place_id, {})
            mode_map: dict[str, RouteLeg | None] = {
                mode: place_routing.get(mode) for mode in ROUTING_MODES
            }
            bundles[place_id] = EnrichmentBundle(
                place_id=place_id,
                routing=mode_map,
                transit=transit.get(place_id),
            )
        return bundles

    async def aclose(self) -> None:
        """Close the async Places and Routes transports after a run."""
        await self._places_client.aclose()
        await self._routes_client.aclose()


def _element_has_route(element: routing_v2.RouteMatrixElement) -> bool:
    """True when the matrix element reports a routable transit result."""
    return element.condition == routing_v2.RouteMatrixElementCondition.ROUTE_EXISTS


def _element_used_fallback(element: routing_v2.RouteMatrixElement) -> bool:
    """True when the element carried fallbackInfo (a degraded but kept result)."""
    try:
        return element._pb.HasField("fallback_info")
    except (ValueError, AttributeError):
        return False


def create_amenity_search(settings: Settings) -> AmenitySearch:
    """Composition root: build the async Places and Routes clients and inject them."""
    return AmenitySearch(
        create_places_async_client(settings),
        create_routes_async_client(settings),
    )
