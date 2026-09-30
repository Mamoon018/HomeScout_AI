import asyncio
import json
import logging
from datetime import datetime, timezone

from google.api_core import exceptions as google_exceptions
from google.api_core.client_options import ClientOptions
from google.maps import routing_v2
from google.type import latlng_pb2

from src.core.config import Settings
from src.core.logging import PLACES_LOGGER_NAME
from src.exceptions.routes import (
    RoutesClientError,
    RoutesInvalidRequestError,
    RoutesRateLimitError,
    RoutesTimeoutError,
)

logger = logging.getLogger(PLACES_LOGGER_NAME)

# Transit distance/duration only; step-level transit details are not requested (M1.2 scope).
TRANSIT_MATRIX_FIELD_MASK = (
    "originIndex,destinationIndex,status,condition,distanceMeters,duration,fallbackInfo"
)

# The Routes computeRouteMatrix call carries no default retry, mirroring the Places discovery
# client: up to two re-issues on a transient failure with a 2s then 3s backoff, each attempt
# bounded by a 15s timeout, then the mapped error.
_MATRIX_CALL_TIMEOUT_SECONDS = 15.0
_MATRIX_RETRY_BACKOFFS_SECONDS = (2.0, 3.0)
_MATRIX_TRANSIENT_ERRORS = (
    google_exceptions.DeadlineExceeded,
    google_exceptions.ServiceUnavailable,
    google_exceptions.ResourceExhausted,
    google_exceptions.RetryError,
)


def create_routes_async_client(settings: Settings) -> "GoogleRoutesAsyncClient":
    """Authenticated async Routes client for transit computeRouteMatrix."""
    sdk_client = routing_v2.RoutesAsyncClient(
        client_options=ClientOptions(api_key=settings.google_maps_api),
    )
    return GoogleRoutesAsyncClient(sdk_client)


class GoogleRoutesAsyncClient:
    """Async computeRouteMatrix for transit travel: one origin, many destinations, one batch."""

    def __init__(self, client: routing_v2.RoutesAsyncClient) -> None:
        self._client = client

    async def compute_route_matrix(
        self,
        *,
        origin: tuple[float, float],
        destinations: list[tuple[float, float]],
        departure_time: datetime,
    ) -> list[routing_v2.RouteMatrixElement]:
        """One TRANSIT matrix batch from `origin` to `destinations` (each `(latitude, longitude)`).

        Returns the streamed `RouteMatrixElement`s collected into a list; the caller maps each
        element back to a place by its `destination_index`. `destinations` must not exceed the
        100-element transit cap (the caller batches).
        """
        request = routing_v2.ComputeRouteMatrixRequest(
            origins=[_matrix_origin(origin)],
            destinations=[_matrix_destination(point) for point in destinations],
            travel_mode=routing_v2.RouteTravelMode.TRANSIT,
            departure_time=departure_time,
        )
        metadata = (("x-goog-fieldmask", TRANSIT_MATRIX_FIELD_MASK),)

        logger.info(
            json.dumps(
                {
                    "endpoint": "routes.computeRouteMatrix.transit",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "origin": {"latitude": origin[0], "longitude": origin[1]},
                    "destination_count": len(destinations),
                }
            )
        )

        last_exc: Exception | None = None
        for attempt in range(len(_MATRIX_RETRY_BACKOFFS_SECONDS) + 1):
            try:
                stream = await self._client.compute_route_matrix(
                    request=request,
                    metadata=metadata,
                    timeout=_MATRIX_CALL_TIMEOUT_SECONDS,
                )
                return [element async for element in stream]
            except (
                google_exceptions.InvalidArgument,
                google_exceptions.FailedPrecondition,
            ) as exc:
                raise RoutesInvalidRequestError(
                    _routes_error("rejected the transit request", exc)
                ) from exc
            except _MATRIX_TRANSIENT_ERRORS as exc:
                last_exc = exc
                _log_routes_failure("transient failure", exc, attempt)
                if attempt < len(_MATRIX_RETRY_BACKOFFS_SECONDS):
                    await asyncio.sleep(_MATRIX_RETRY_BACKOFFS_SECONDS[attempt])
                    continue
            except google_exceptions.GoogleAPIError as exc:
                raise RoutesClientError(_routes_error("failed", exc)) from exc
            break

        if isinstance(last_exc, google_exceptions.ResourceExhausted):
            raise RoutesRateLimitError(
                _routes_error("was rate limited", last_exc)
            ) from last_exc
        raise RoutesTimeoutError(
            _routes_error("timed out after retries", last_exc)
        ) from last_exc

    async def aclose(self) -> None:
        """Close the async transport channel opened by the SDK client."""
        await self._client.transport.close()


def _log_routes_failure(context: str, exc: Exception, attempt: int | None = None) -> None:
    """Log the real underlying cause of a Routes call failure so it is not swallowed."""
    record = {
        "event": "routes.call_failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": "routes.computeRouteMatrix.transit",
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


def _routes_error(context: str, exc: Exception | None) -> str:
    """Log the cause and return a message that carries the underlying error detail."""
    if exc is None:
        return f"Routes computeRouteMatrix transit {context}"
    _log_routes_failure(context, exc)
    return f"Routes computeRouteMatrix transit {context}: {type(exc).__name__}: {exc}"


def _waypoint(point: tuple[float, float]) -> routing_v2.Waypoint:
    return routing_v2.Waypoint(
        location=routing_v2.Location(
            lat_lng=latlng_pb2.LatLng(latitude=point[0], longitude=point[1]),
        )
    )


def _matrix_origin(point: tuple[float, float]) -> routing_v2.RouteMatrixOrigin:
    return routing_v2.RouteMatrixOrigin(waypoint=_waypoint(point))


def _matrix_destination(point: tuple[float, float]) -> routing_v2.RouteMatrixDestination:
    return routing_v2.RouteMatrixDestination(waypoint=_waypoint(point))
