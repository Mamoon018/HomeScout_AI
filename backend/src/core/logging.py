import logging


def configure_logging() -> None:
    """Configure process-wide logs so cookie send/receive can be verified in the terminal."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
