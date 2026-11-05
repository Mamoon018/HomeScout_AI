import logging
import sys
from contextvars import ContextVar

AUTH_LOGGER_NAME = "homescout.auth"
PLACES_LOGGER_NAME = "homescout.places"
DEEP_SEARCH_LOGGER_NAME = "homescout.deep_search"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] run=%(run_id)s %(message)s"
_shared_handler: logging.StreamHandler | None = None

# The R1 run a log line belongs to. Set by the run coordinator for the duration of one run step,
# so R1's own stage lines (which know nothing about runs) can be tied back to their run.
run_id_var: ContextVar[str] = ContextVar("run_id", default="-")


class _RunIdFilter(logging.Filter):
    """Stamp every record with the current run id ('-' outside a run)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get()
        return True


def _resolve_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def configure_logging(level_name: str = "INFO") -> None:
    """Attach a dedicated stderr handler to app loggers so uvicorn cannot silence them."""
    global _shared_handler

    level = _resolve_level(level_name)

    if _shared_handler is None:
        _shared_handler = logging.StreamHandler(sys.stderr)
        _shared_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        _shared_handler.addFilter(_RunIdFilter())

    _shared_handler.setLevel(level)

    for name in (AUTH_LOGGER_NAME, PLACES_LOGGER_NAME, DEEP_SEARCH_LOGGER_NAME):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        if _shared_handler not in logger.handlers:
            logger.addHandler(_shared_handler)
