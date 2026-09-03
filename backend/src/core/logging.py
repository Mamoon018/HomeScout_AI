import logging
import sys

AUTH_LOGGER_NAME = "homescout.auth"
PLACES_LOGGER_NAME = "homescout.places"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_shared_handler: logging.StreamHandler | None = None


def _resolve_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def configure_logging(level_name: str = "INFO") -> None:
    """Attach a dedicated stderr handler to app loggers so uvicorn cannot silence them."""
    global _shared_handler

    level = _resolve_level(level_name)

    if _shared_handler is None:
        _shared_handler = logging.StreamHandler(sys.stderr)
        _shared_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    _shared_handler.setLevel(level)

    for name in (AUTH_LOGGER_NAME, PLACES_LOGGER_NAME):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        if _shared_handler not in logger.handlers:
            logger.addHandler(_shared_handler)
