import asyncio
import json
import logging
import math
from datetime import datetime, timezone

from google.maps import places_v1

from src.clients.google_places import (
    GooglePlacesAsyncClient,
    create_places_async_client,
)
from src.core.config import Settings
from src.core.logging import PLACES_LOGGER_NAME
from src.exceptions.deep_search import (
    PlaceDiscoveryCallError,
    PlaceDiscoveryRequestError,
)
from src.exceptions.places import PlacesClientError
from src.services.deep_search.feature_schemas.schemas import (
    DISCOVERY_MAX_RESULTS,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    DiscoveryRequest,
    GeoPoint,
)

logger = logging.getLogger(PLACES_LOGGER_NAME)

DEFAULT_DISCOVERY_CONCURRENCY = 3
_METERS_PER_KM = 1000.0
_PLACES_FIELD_PREFIX = "places."

# The sample runner reads these events back off PLACES_LOGGER_NAME to print the stage trail.
DISCOVERY_REQUEST_EVENT = "discovery.request_built"
DISCOVERY_CATEGORY_EVENT = "discovery.category_completed"


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
        *,
        max_concurrency: int = DEFAULT_DISCOVERY_CONCURRENCY,
    ) -> None:
        self._places_client = places_client
        # Independent per-category searches overlap their I/O waits; the semaphore caps how
        # many are in flight so the tool's rate limit is not overrun.
        self._semaphore = asyncio.Semaphore(max_concurrency)

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

    async def aclose(self) -> None:
        """Close the async Places transport after a run."""
        await self._places_client.aclose()


def create_amenity_search(settings: Settings) -> AmenitySearch:
    """Composition root: build the async Places client and inject it."""
    return AmenitySearch(create_places_async_client(settings))
