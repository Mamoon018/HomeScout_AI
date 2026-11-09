"""One log line per HTTP request: method, path, status, duration, and why it failed.

Logged on `homescout.http`. Request bodies are never logged (login carries a password). For a
4xx/5xx response, only the error's safe fields are logged: our error bodies' `error`, `status`,
`retryable` and `run_id`, and for validation errors each field's location and message, never the
submitted value.
"""

import json
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from src.core.logging import HTTP_LOGGER_NAME

logger = logging.getLogger(HTTP_LOGGER_NAME)

# Swagger's own page loads and the container health probe would bury the requests that matter.
_QUIET_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"})
_SAFE_ERROR_FIELDS = ("error", "code", "run_id", "status", "retryable")


async def log_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    if request.url.path in _QUIET_PATHS:
        return await call_next(request)

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(
            json.dumps(
                {
                    "event": "http.request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": _elapsed_ms(started),
                    "error_class": type(exc).__name__,
                }
            )
        )
        raise

    record: dict = {
        "event": "http.request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": _elapsed_ms(started),
    }
    if response.status_code >= 400:
        # The body must be read to explain the failure, then handed back unchanged.
        body = b"".join([chunk async for chunk in response.body_iterator])
        record["error"] = _safe_error(body)
        rebuilt = Response(content=body, status_code=response.status_code)
        # Raw header list, not a dict: a response can carry several Set-Cookie headers.
        rebuilt.raw_headers = list(response.raw_headers)
        response = rebuilt

    level = (
        logging.ERROR
        if response.status_code >= 500
        else logging.WARNING
        if response.status_code >= 400
        else logging.INFO
    )
    logger.log(level, json.dumps(record, default=str))
    return response


def _safe_error(body: bytes) -> object:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"non_json_body_bytes": len(body)}
    if not isinstance(payload, dict):
        return {"body_type": type(payload).__name__}

    detail = payload.get("detail")
    if isinstance(detail, list):  # FastAPI request validation: keep where and why, drop the input
        return [
            {"loc": item.get("loc"), "msg": item.get("msg")}
            for item in detail
            if isinstance(item, dict)
        ]
    safe = {key: payload[key] for key in _SAFE_ERROR_FIELDS if key in payload}
    if isinstance(detail, str):
        safe["detail"] = detail
    return safe


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
