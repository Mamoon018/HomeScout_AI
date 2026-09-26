class RoutesClientError(Exception):
    """Base error for the Google Routes client wrapper."""


class RoutesTimeoutError(RoutesClientError):
    """Raised when a Routes call times out or exhausts its retry deadline."""


class RoutesRateLimitError(RoutesClientError):
    """Raised when Routes rejects a call for quota or rate limiting."""


class RoutesInvalidRequestError(RoutesClientError):
    """Raised when Routes rejects the request shape or parameters."""
