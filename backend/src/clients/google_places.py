import asyncio
import json
import logging
from datetime import datetime, timezone

from google.api_core import exceptions as google_exceptions
from google.api_core.client_options import ClientOptions
from google.maps import places_v1

from src.core.config import Settings
from src.core.logging import PLACES_LOGGER_NAME
from src.exceptions.places import (
    PlacesClientError,
    PlacesInvalidRequestError,
    PlacesRateLimitError,
    PlacesTimeoutError,
)

logger = logging.getLogger(PLACES_LOGGER_NAME)

# Enterprise SKU mask: Essentials + Pro + Enterprise fields, plus routingSummaries.
# Defined once so every searchNearby call bills at the same tier.
SEARCH_NEARBY_FIELD_MASK = ",".join(
    (
        "places.accessibilityOptions",
        "places.addressComponents",
        "places.addressDescriptor",
        "places.adrFormatAddress",
        "places.attributions",
        "places.businessStatus",
        "places.consumerAlert",
        "places.containingPlaces",
        "places.displayName",
        "places.formattedAddress",
        "places.googleMapsLinks",
        "places.googleMapsTypeLabel",
        "places.googleMapsUri",
        "places.iconBackgroundColor",
        "places.iconMaskBaseUri",
        "places.id",
        "places.location",
        "places.name",
        "places.movedPlace",
        "places.movedPlaceId",
        "places.openingDate",
        "places.photos",
        "places.plusCode",
        "places.postalAddress",
        "places.primaryType",
        "places.primaryTypeDisplayName",
        "places.pureServiceAreaBusiness",
        "places.shortFormattedAddress",
        "places.subDestinations",
        "places.timeZone",
        "places.types",
        "places.utcOffsetMinutes",
        "places.viewport",
        "places.currentOpeningHours",
        "places.currentSecondaryOpeningHours",
        "places.internationalPhoneNumber",
        "places.nationalPhoneNumber",
        "places.priceLevel",
        "places.priceRange",
        "places.rating",
        "places.regularOpeningHours",
        "places.regularSecondaryOpeningHours",
        "places.transitStation",
        "places.userRatingCount",
        "places.websiteUri",
        "places.allowsDogs",
        "places.curbsidePickup",
        "places.delivery",
        "places.dineIn",
        "places.editorialSummary",
        "places.evChargeAmenitySummary",
        "places.evChargeOptions",
        "places.fuelOptions",
        "places.generativeSummary",
        "places.goodForChildren",
        "places.goodForGroups",
        "places.goodForWatchingSports",
        "places.liveMusic",
        "places.menuForChildren",
        "places.neighborhoodSummary",
        "places.parkingOptions",
        "places.paymentOptions",
        "places.outdoorSeating",
        "places.reservable",
        "places.restroom",
        "places.reviews",
        "places.reviewSummary",
        "routingSummaries",
        "places.servesBeer",
        "places.servesBreakfast",
        "places.servesBrunch",
        "places.servesCocktails",
        "places.servesCoffee",
        "places.servesDessert",
        "places.servesDinner",
        "places.servesLunch",
        "places.servesVegetarianFood",
        "places.servesWine",
        "places.takeout",
    )
)

_FIELD_MASK_METADATA = (("x-goog-fieldmask", SEARCH_NEARBY_FIELD_MASK),)


def create_places_client(settings: Settings) -> "GooglePlacesClient":
    """Authenticated Places SDK client wrapped for searchNearby-only use."""
    sdk_client = places_v1.PlacesClient(
        client_options=ClientOptions(api_key=settings.google_maps_api),
    )
    return GooglePlacesClient(sdk_client)


class GooglePlacesClient:
    """Single entry point for Places searchNearby with routing and field mask."""

    def __init__(self, client: places_v1.PlacesClient) -> None:
        self._client = client

    def search_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_meters: float,
        included_types: list[str],
        travel_mode: places_v1.TravelMode,
        max_result_count: int = 20,
        language_code: str | None = None,
    ) -> places_v1.SearchNearbyResponse:
        origin = {"latitude": latitude, "longitude": longitude}
        request = places_v1.SearchNearbyRequest(
            included_types=included_types,
            max_result_count=max_result_count,
            location_restriction=places_v1.SearchNearbyRequest.LocationRestriction(
                circle=places_v1.types.Circle(
                    center=origin,
                    radius=radius_meters,
                ),
            ),
            rank_preference=places_v1.SearchNearbyRequest.RankPreference.DISTANCE,
            routing_parameters=places_v1.RoutingParameters(
                origin=origin,
                travel_mode=travel_mode,
            ),
        )
        if language_code:
            request.language_code = language_code

        logger.info(
            json.dumps(
                {
                    "endpoint": "places.searchNearby",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_meters": radius_meters,
                    "included_types": included_types,
                    "travel_mode": travel_mode.name,
                    "max_result_count": max_result_count,
                }
            )
        )

        try:
            return self._client.search_nearby(
                request=request,
                metadata=_FIELD_MASK_METADATA,
            )
        except (google_exceptions.DeadlineExceeded, google_exceptions.RetryError) as exc:
            raise PlacesTimeoutError("Places searchNearby timed out") from exc
        except google_exceptions.ResourceExhausted as exc:
            raise PlacesRateLimitError("Places searchNearby was rate limited") from exc
        except (
            google_exceptions.InvalidArgument,
            google_exceptions.FailedPrecondition,
        ) as exc:
            raise PlacesInvalidRequestError(
                "Places searchNearby rejected the request"
            ) from exc
        except google_exceptions.GoogleAPIError as exc:
            raise PlacesClientError("Places searchNearby failed") from exc


# ---------------------------------------------------------------------------------
# Responsibility 2, Mechanism 1, Component M1.1 — async discovery client
# ---------------------------------------------------------------------------------

# Discovery is a no-routing searchNearby: the caller supplies a narrow field mask built from
# the category's pre-defined metrics, so routingSummaries is never requested and no
# routingParameters are attached. Routing enrichment (M1.2.a) re-issues the same search per mode
# WITH routingParameters and a minimal mask. Retry is explicit here because the generated
# searchNearby method carries no default retry: up to two re-issues on a transient failure with a
# 2s then 3s backoff, each attempt bounded by a 15s call timeout, then the mapped error.
_DISCOVERY_CALL_TIMEOUT_SECONDS = 15.0
_DISCOVERY_RETRY_BACKOFFS_SECONDS = (2.0, 3.0)
_DISCOVERY_TRANSIENT_ERRORS = (
    google_exceptions.DeadlineExceeded,
    google_exceptions.ServiceUnavailable,
    google_exceptions.ResourceExhausted,
    google_exceptions.RetryError,
)

# Routing re-search returns only place identity plus the routing legs; the profile fields
# already live on the canonical CanonicalPlace, so this mask stays minimal.
ROUTING_FIELD_MASK = "places.id,routingSummaries"

# walk/drive/cycle map onto the Places TravelMode enum (transit is not a Places mode; it comes
# from the Routes API in M1.2.b).
_ROUTING_TRAVEL_MODES = {
    "walk": places_v1.TravelMode.WALK,
    "drive": places_v1.TravelMode.DRIVE,
    "cycle": places_v1.TravelMode.BICYCLE,
}


def create_places_async_client(settings: Settings) -> "GooglePlacesAsyncClient":
    """Authenticated async Places client for no-routing discovery searchNearby."""
    sdk_client = places_v1.PlacesAsyncClient(
        client_options=ClientOptions(api_key=settings.google_maps_api),
    )
    return GooglePlacesAsyncClient(sdk_client)


class GooglePlacesAsyncClient:
    """Async searchNearby for place discovery: no routing, caller-supplied field mask."""

    def __init__(self, client: places_v1.PlacesAsyncClient) -> None:
        self._client = client

    async def search_nearby_discovery(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_meters: float,
        primary_type: str,
        field_mask: str,
        max_result_count: int,
    ) -> places_v1.SearchNearbyResponse:
        origin = {"latitude": latitude, "longitude": longitude}
        request = places_v1.SearchNearbyRequest(
            included_primary_types=[primary_type],
            max_result_count=max_result_count,
            location_restriction=places_v1.SearchNearbyRequest.LocationRestriction(
                circle=places_v1.types.Circle(center=origin, radius=radius_meters),
            ),
            rank_preference=places_v1.SearchNearbyRequest.RankPreference.DISTANCE,
        )
        metadata = (("x-goog-fieldmask", field_mask),)

        logger.info(
            json.dumps(
                {
                    "endpoint": "places.searchNearby.discovery",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_meters": radius_meters,
                    "primary_type": primary_type,
                    "max_result_count": max_result_count,
                }
            )
        )
        return await self._search_with_retry(request, metadata, "discovery")

    async def search_nearby_routing(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_meters: float,
        primary_type: str,
        travel_mode: str,
        max_result_count: int,
    ) -> places_v1.SearchNearbyResponse:
        """Routing re-search: the discovery search re-issued with routingParameters for one mode.

        `travel_mode` is one of "walk", "drive", "cycle" (mapped to the Places TravelMode enum).
        The response carries `routing_summaries` parallel to `places`; the caller matches by index.
        """
        sdk_travel_mode = _ROUTING_TRAVEL_MODES[travel_mode]
        origin = {"latitude": latitude, "longitude": longitude}
        request = places_v1.SearchNearbyRequest(
            included_primary_types=[primary_type],
            max_result_count=max_result_count,
            location_restriction=places_v1.SearchNearbyRequest.LocationRestriction(
                circle=places_v1.types.Circle(center=origin, radius=radius_meters),
            ),
            rank_preference=places_v1.SearchNearbyRequest.RankPreference.DISTANCE,
            routing_parameters=places_v1.RoutingParameters(
                origin=origin,
                travel_mode=sdk_travel_mode,
            ),
        )
        metadata = (("x-goog-fieldmask", ROUTING_FIELD_MASK),)

        logger.info(
            json.dumps(
                {
                    "endpoint": "places.searchNearby.routing",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_meters": radius_meters,
                    "primary_type": primary_type,
                    "travel_mode": travel_mode,
                    "max_result_count": max_result_count,
                }
            )
        )
        return await self._search_with_retry(request, metadata, "routing")

    async def _search_with_retry(
        self,
        request: places_v1.SearchNearbyRequest,
        metadata: tuple,
        call_kind: str,
    ) -> places_v1.SearchNearbyResponse:
        """Issue one searchNearby with explicit retry: 2s then 3s backoff, 15s per attempt."""
        last_exc: Exception | None = None
        for attempt in range(len(_DISCOVERY_RETRY_BACKOFFS_SECONDS) + 1):
            try:
                return await self._client.search_nearby(
                    request=request,
                    metadata=metadata,
                    timeout=_DISCOVERY_CALL_TIMEOUT_SECONDS,
                )
            except (
                google_exceptions.InvalidArgument,
                google_exceptions.FailedPrecondition,
            ) as exc:
                raise PlacesInvalidRequestError(
                    _places_error(call_kind, "rejected the request", exc)
                ) from exc
            except _DISCOVERY_TRANSIENT_ERRORS as exc:
                last_exc = exc
                _log_places_failure(call_kind, "transient failure", exc, attempt)
                if attempt < len(_DISCOVERY_RETRY_BACKOFFS_SECONDS):
                    await asyncio.sleep(_DISCOVERY_RETRY_BACKOFFS_SECONDS[attempt])
                    continue
            except google_exceptions.GoogleAPIError as exc:
                raise PlacesClientError(_places_error(call_kind, "failed", exc)) from exc
            break

        if isinstance(last_exc, google_exceptions.ResourceExhausted):
            raise PlacesRateLimitError(
                _places_error(call_kind, "was rate limited", last_exc)
            ) from last_exc
        raise PlacesTimeoutError(
            _places_error(call_kind, "timed out after retries", last_exc)
        ) from last_exc

    async def aclose(self) -> None:
        """Close the async transport channel opened by the SDK client."""
        await self._client.transport.close()


def _log_places_failure(
    call_kind: str, context: str, exc: Exception, attempt: int | None = None
) -> None:
    """Log the real underlying cause of a Places call failure so it is not swallowed."""
    record = {
        "event": "places.call_failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": f"places.searchNearby.{call_kind}",
        "context": context,
        "error_type": type(exc).__name__,
        "error_detail": str(exc),
    }
    code = getattr(exc, "code", None)
    if code is not None:
        record["error_code"] = str(code)
    if attempt is not None:
        record["attempt"] = attempt
    logger.error(json.dumps(record))


def _places_error(call_kind: str, context: str, exc: Exception | None) -> str:
    """Log the cause and return a message that carries the underlying error detail."""
    if exc is None:
        return f"Places searchNearby {call_kind} {context}"
    _log_places_failure(call_kind, context, exc)
    return f"Places searchNearby {call_kind} {context}: {type(exc).__name__}: {exc}"
