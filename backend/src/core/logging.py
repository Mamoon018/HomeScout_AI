import logging
import sys

AUTH_LOGGER_NAME = "homescout.auth"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_auth_handler: logging.StreamHandler | None = None


def _resolve_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def configure_logging(level_name: str = "INFO") -> None:
    """Attach a dedicated handler to homescout.auth so uvicorn cannot silence it."""
    global _auth_handler

    level = _resolve_level(level_name)
    auth_logger = logging.getLogger(AUTH_LOGGER_NAME)
    auth_logger.setLevel(level)
    auth_logger.propagate = False

    if _auth_handler is None:
        _auth_handler = logging.StreamHandler(sys.stderr)
        _auth_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        auth_logger.addHandler(_auth_handler)
    elif _auth_handler not in auth_logger.handlers:
        auth_logger.addHandler(_auth_handler)

    _auth_handler.setLevel(level)
