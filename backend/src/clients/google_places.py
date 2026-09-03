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
