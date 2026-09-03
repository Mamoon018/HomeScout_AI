class PlacesClientError(Exception):
    """Base error for the Google Places client wrapper."""


class PlacesTimeoutError(PlacesClientError):
    """Raised when a Places call times out or exhausts its retry deadline."""


class PlacesRateLimitError(PlacesClientError):
    """Raised when Places rejects a call for quota or rate limiting."""


class PlacesInvalidRequestError(PlacesClientError):
    """Raised when Places rejects the request shape or parameters."""
