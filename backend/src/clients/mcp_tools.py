"""R2 Mechanism 3 Component C3.1.1 — async MCP tool gateway.

A client-boundary capability that exposes two typed operations over two hosted MCP servers:
`search_web` (Parallel `web_search`) and `crawl_site` (Firecrawl `firecrawl_crawl`, read to
completion through `firecrawl_check_crawl_status`). Nothing above this module imports `mcp`; callers
see only the typed result contracts and the `ToolGateway` Protocol.

Ownership notes fixed against the real SDK (`mcp==2.2.0`):
- `mcp.Client` holds an anyio task group, so it must be entered and exited in the same task. Each
  server therefore runs in its own owner task (`_ServerSession`); `open()` and `aclose()` may run
  in different tasks of the caller, but the context enter/exit always happen in the owner task.
- `Client` is one-shot and not re-enterable. The gateway never reconnects or replaces a `Client`:
  a timeout is our side giving up on one wait, so the open session stays in use for the next call.
- The caller-owned HTTP client is `httpx2.AsyncClient`; the default factory attaches the bearer
  header there and omits it when the key is `None`.

Only two conditions raise (`McpConnectionError`, `McpToolUnavailableError`). Every per-call problem
is returned as a `ToolFailure`, so one failed call never aborts a concurrent gather.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# --------------------------------------------------------------------------------------------------
# Composition-root constants. Unmeasured starting values; revisit once a live capture exists.
# --------------------------------------------------------------------------------------------------
SEARCH_TIMEOUT_SECONDS = 30.0
# Each start or status call is bounded by its server's own per-call timeout; this caps the whole
# crawl-plus-poll wait so a stuck job cannot block a run forever.
CRAWL_CALL_TIMEOUT_SECONDS = 60.0
CRAWL_DEADLINE_SECONDS = 180.0
RETRY_BACKOFFS_SECONDS = (2.0, 3.0)
CRAWL_POLL_INTERVAL_SECONDS = 3.0
SEARCH_CONCURRENCY = 4
CRAWL_CONCURRENCY = 2

# MCP tool and argument names required on each server. Checked at connect; a miss raises.
PARALLEL_SEARCH_TOOL = "web_search"
PARALLEL_SEARCH_ARGS = ("objective", "search_queries")
FIRECRAWL_CRAWL_TOOL = "firecrawl_crawl"
FIRECRAWL_CRAWL_ARGS = ("url", "limit", "maxDiscoveryDepth", "allowExternalLinks")
FIRECRAWL_STATUS_TOOL = "firecrawl_check_crawl_status"
# The job-id argument of the status tool. Provisional from the Firecrawl MCP docs; fixed from the
# live capture. Isolated here so the open verification item is a one-line change.
FIRECRAWL_STATUS_JOB_ARG = "id"

# Candidate keys for the crawl job id and the page fields, provisional until the live capture fixes
# the real shapes. Kept as tuples so the parsers tolerate either the documented or captured name.
_JOB_ID_KEYS = ("id", "job_id", "jobId", "crawlId")
_PAGE_LIST_KEYS = ("data", "pages", "results")
_PAGE_TEXT_KEYS = ("markdown", "content", "text", "html")
_PAGE_URL_KEYS = ("url", "sourceURL", "sourceUrl")
_HIT_TEXT_KEYS = ("text", "content", "snippet", "summary")
_HIT_LIST_KEYS = ("results", "excerpts", "items")
_CRAWL_DONE_STATUSES = ("completed", "complete", "done", "success", "finished")
_CRAWL_RUNNING_STATUSES = ("scraping", "pending", "processing", "active", "in_progress", "queued")

_RATE_LIMIT_RE = re.compile(r"rate.?limit|too many requests|429", re.IGNORECASE)

ToolFailureKind = Literal["tool_error", "timeout", "rate_limited", "transport", "unparseable"]

# Transport-level exception types that mean the session link itself failed (as opposed to the tool
# returning an error body). Classified as `transport` so the caller can see a dead session via
# repeated `ToolFailure(transport)` rather than a raised error mid-gather.
_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    httpx2.HTTPError,
    ConnectionError,
    OSError,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _async_sleep(seconds: float) -> None:
    """Indirection for retry and poll waits so tests can replace it without touching real time."""
    await asyncio.sleep(seconds)


# --------------------------------------------------------------------------------------------------
# Data contracts (kept in clients/, since clients/ must not import services/).
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class McpServerConfig:
    """One server's connection settings."""

    name: str
    url: str
    api_key: str | None
    call_timeout_seconds: float


@dataclass(frozen=True)
class SearchExcerpt:
    """One search hit."""

    url: str | None
    title: str | None
    text: str


@dataclass(frozen=True)
class WebSearchResult:
    """Typed `web_search` outcome. An empty hit list is a valid result, not a failure."""

    objective: str
    search_queries: tuple[str, ...]
    excerpts: tuple[SearchExcerpt, ...]
    retrieved_at: str


@dataclass(frozen=True)
class CrawledPage:
    """One crawled page."""

    url: str
    title: str | None
    text: str


@dataclass(frozen=True)
class CrawlResult:
    """Typed `firecrawl_crawl` outcome."""

    url: str
    job_id: str | None
    pages: tuple[CrawledPage, ...]
    retrieved_at: str


@dataclass(frozen=True)
class ToolFailure:
    """A typed per-call failure, returned not raised, so a gather survives one bad call."""

    tool: str
    kind: ToolFailureKind
    message: str


class _UnparseableResult(Exception):
    """Internal: a tool body in an unrecognised shape; mapped to `ToolFailure(unparseable)`."""


# --------------------------------------------------------------------------------------------------
# Supporting interfaces.
# --------------------------------------------------------------------------------------------------
class ToolGateway(Protocol):
    """The narrow contract `AmenitySearch` and tests depend on; no MCP types leak through it."""

    async def open(self) -> None: ...

    async def search_web(
        self, objective: str, search_queries: Sequence[str]
    ) -> WebSearchResult | ToolFailure: ...

    async def crawl_site(self, url: str, limit: int, depth: int) -> CrawlResult | ToolFailure: ...

    async def aclose(self) -> None: ...


# A factory maps one server config to an async context manager yielding a connected `mcp.Client`.
# Production uses Streamable HTTP; tests inject an in-process server. Entering/exiting the yielded
# client is the owner task's job, so the whole client lifetime stays on one task.
ClientFactory = Callable[[McpServerConfig], AbstractAsyncContextManager[Client]]


def _streamable_http_factory(
    config: McpServerConfig,
) -> AbstractAsyncContextManager[Client]:
    """Default factory: a Streamable HTTP `Client` whose httpx2 client carries the bearer header.

    Both the httpx2 client and the `Client` are opened and closed inside this context, so the owner
    task owns the full lifetime. The header is omitted when the key is `None`.
    """

    @asynccontextmanager
    async def _cm() -> "AbstractAsyncContextManager[Client]":
        headers: dict[str, str] = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        async with httpx2.AsyncClient(headers=headers) as http_client:
            transport = streamable_http_client(config.url, http_client=http_client)
            async with Client(transport, read_timeout_seconds=config.call_timeout_seconds) as client:
                yield client

    return _cm()


# --------------------------------------------------------------------------------------------------
# One owner task per server.
# --------------------------------------------------------------------------------------------------
class _ServerSession:
    """Owns one server's `Client` lifetime on a single task.

    The owner task opens the factory context, publishes the ready `Client`, waits for a release
    signal, then exits the context on the same task. There is no replace step: if a start fails it
    re-raises as `McpConnectionError`; a later timeout leaves the session untouched.
    """

    def __init__(
        self,
        config: McpServerConfig,
        client_factory: ClientFactory,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._client: Client | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._start_error: BaseException | None = None

    async def start(self) -> None:
        """Launch the owner task and wait until the `Client` is ready or the start failed."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._run(), name=f"mcp-session-{self._config.name}"
        )
        await self._ready.wait()
        if self._start_error is not None:
            # The task has already unwound its context; await it so nothing is left running.
            await self._await_task()
            raise McpConnectionError(
                f"could not open MCP session for server '{self._config.name}'",
                stage="open",
            ) from self._start_error
        logger.info(
            json.dumps(
                {
                    "event": "mcp.session_opened",
                    "timestamp": _timestamp(),
                    "server": self._config.name,
                    "authenticated": self._config.api_key is not None,
                }
            )
        )

    async def _run(self) -> None:
        try:
            async with self._client_factory(self._config) as client:
                self._client = client
                self._ready.set()
                await self._stop.wait()
        except BaseException as exc:  # noqa: BLE001 - surfaced to start() as McpConnectionError
            self._client = None
            self._start_error = exc
            self._ready.set()

    def client(self) -> Client:
        if self._client is None:
            raise McpConnectionError(
                f"MCP session for server '{self._config.name}' is not open",
                stage="open",
            )
        return self._client

    async def stop(self) -> None:
        """Release the owner task and await it. Idempotent.

        A ready session is parked on `_stop` and closes gracefully. A task that never reached
        readiness (still connecting, or failing) is not waiting on `_stop`, so it is cancelled to
        unwind the half-open connect promptly instead of blocking on the HTTP client's timeout.
        """
        task = self._task
        if task is None:
            return
        self._stop.set()
        if self._client is None and not task.done():
            task.cancel()
        await self._await_task()

    async def _await_task(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        with suppress(asyncio.CancelledError):
            await task
        self._client = None


# --------------------------------------------------------------------------------------------------
# The gateway.
# --------------------------------------------------------------------------------------------------
class McpToolGateway:
    """Concrete `ToolGateway`: owns sessions, per-server semaphores, retry, timeouts, parsing."""

    def __init__(
        self,
        parallel: McpServerConfig,
        firecrawl: McpServerConfig,
        *,
        search_concurrency: int = SEARCH_CONCURRENCY,
        crawl_concurrency: int = CRAWL_CONCURRENCY,
        client_factory: ClientFactory = _streamable_http_factory,
    ) -> None:
        self._parallel_config = parallel
        self._firecrawl_config = firecrawl
        self._parallel = _ServerSession(parallel, client_factory)
        self._firecrawl = _ServerSession(firecrawl, client_factory)
        # Per-server bounds: a slow crawl must not starve searches, so each has its own slot pool.
        self._search_sem = asyncio.Semaphore(search_concurrency)
        self._crawl_sem = asyncio.Semaphore(crawl_concurrency)

    async def open(self) -> None:
        """Start both sessions together, then verify both catalogs.

        Any non-local exit — a start failure, a verify failure, or a cancellation of the caller
        mid-open — tears both sessions down before leaving, so a partially-opened gateway never
        leaks an owner task or its client.
        """
        try:
            await self._start_sessions()
            await self.verify_capabilities()
        except BaseException:
            await self.aclose()
            raise

    async def _start_sessions(self) -> None:
        results = await asyncio.gather(
            self._parallel.start(), self._firecrawl.start(), return_exceptions=True
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            # Cleanup is centralized in `open`; here we only translate the failure.
            first = errors[0]
            if isinstance(first, McpConnectionError):
                raise first
            raise McpConnectionError(
                "could not open one or more MCP sessions", stage="open"
            ) from first

    async def verify_capabilities(self) -> None:
        """List tools on both servers (cache bypassed) and match the required names and arguments."""
        parallel_tools, firecrawl_tools = await asyncio.gather(
            self._list_tools(self._parallel),
            self._list_tools(self._firecrawl),
        )
        self._require(
            parallel_tools, PARALLEL_SEARCH_TOOL, PARALLEL_SEARCH_ARGS, self._parallel_config.name
        )
        self._require(
            firecrawl_tools, FIRECRAWL_CRAWL_TOOL, FIRECRAWL_CRAWL_ARGS, self._firecrawl_config.name
        )
        # The status tool is required because every crawl result is read through it; a keyless
        # Firecrawl is missing the crawl tool above, which already fails this check.
        self._require(
            firecrawl_tools,
            FIRECRAWL_STATUS_TOOL,
            (FIRECRAWL_STATUS_JOB_ARG,),
            self._firecrawl_config.name,
        )

    async def _list_tools(self, session: _ServerSession) -> dict[str, set[str]]:
        try:
            listing = await session.client().list_tools(cache_mode="bypass")
        except McpConnectionError:
            raise
        except _TRANSPORT_ERRORS as exc:
            raise McpConnectionError(
                f"could not list tools on server '{session._config.name}'",
                stage="verify_capabilities",
            ) from exc
        catalog: dict[str, set[str]] = {}
        for tool in listing.tools:
            schema = getattr(tool, "input_schema", None) or {}
            properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
            catalog[tool.name] = set(properties)
        return catalog

    @staticmethod
    def _require(
        catalog: dict[str, set[str]],
        tool: str,
        arguments: Sequence[str],
        server: str,
    ) -> None:
        if tool not in catalog:
            raise McpToolUnavailableError(
                f"server '{server}' is missing required tool '{tool}'",
                stage="verify_capabilities",
            )
        missing = [arg for arg in arguments if arg not in catalog[tool]]
        if missing:
            raise McpToolUnavailableError(
                f"tool '{tool}' on server '{server}' is missing arguments {sorted(missing)}",
                stage="verify_capabilities",
            )

    async def search_web(
        self, objective: str, search_queries: Sequence[str]
    ) -> WebSearchResult | ToolFailure:
        """Run `web_search` with transient retry and parse the excerpts."""
        if not objective.strip():
            raise ValueError("search objective must be a non-empty string")
        if not any(query.strip() for query in search_queries):
            raise ValueError("search_queries must contain at least one non-empty query")
        client = self._parallel.client()
        retrieved_at = _timestamp()
        arguments = {"objective": objective, "search_queries": list(search_queries)}
        outcome = await self._call_with_retry(
            self._search_sem,
            client,
            PARALLEL_SEARCH_TOOL,
            arguments,
            timeout=self._parallel_config.call_timeout_seconds,
            retry_kinds={"timeout", "transport", "rate_limited"},
        )
        if isinstance(outcome, ToolFailure):
            return outcome
        try:
            return _parse_search_result(
                outcome, objective, tuple(search_queries), retrieved_at
            )
        except _UnparseableResult as exc:
            return ToolFailure(PARALLEL_SEARCH_TOOL, "unparseable", str(exc))

    async def crawl_site(
        self, url: str, limit: int, depth: int
    ) -> CrawlResult | ToolFailure:
        """Start `firecrawl_crawl`, then read the job to completion by its id."""
        if limit < 1:
            raise ValueError("crawl limit must be >= 1")
        if depth < 0:
            raise ValueError("crawl depth must be >= 0")
        if not url.startswith(("http://", "https://")):
            raise ValueError("crawl url must be an http(s) URL")

        client = self._firecrawl.client()
        retrieved_at = _timestamp()
        arguments = {
            "url": url,
            "limit": limit,
            "maxDiscoveryDepth": depth,
            "allowExternalLinks": False,
        }
        # The start call is never re-issued after a timeout or transport error: the job may already
        # exist and be billed. Only a rate-limited start retries.
        start = await self._call_with_retry(
            self._crawl_sem,
            client,
            FIRECRAWL_CRAWL_TOOL,
            arguments,
            timeout=self._firecrawl_config.call_timeout_seconds,
            retry_kinds={"rate_limited"},
        )
        if isinstance(start, ToolFailure):
            return start
        try:
            parsed = _parse_crawl_result(start, url, retrieved_at)
        except _UnparseableResult as exc:
            return ToolFailure(FIRECRAWL_CRAWL_TOOL, "unparseable", str(exc))
        if isinstance(parsed, CrawlResult):
            return parsed
        # `parsed` is a job id; read it to completion on the same Client.
        return await self._read_crawl_job(client, parsed, url, retrieved_at)

    async def aclose(self) -> None:
        """Idempotent: end every owner task in its own task."""
        await asyncio.gather(self._parallel.stop(), self._firecrawl.stop())

    # ---- internal ----------------------------------------------------------------------------
    async def _call_with_retry(
        self,
        semaphore: asyncio.Semaphore,
        client: Client,
        tool: str,
        arguments: dict,
        *,
        timeout: float,
        retry_kinds: set[str],
    ) -> "object | ToolFailure":
        """One bounded call with transient retry; reuses the same `Client` on every attempt."""
        failure: ToolFailure | None = None
        for attempt in range(len(RETRY_BACKOFFS_SECONDS) + 1):
            outcome = await self._single_call(semaphore, client, tool, arguments, timeout)
            if not isinstance(outcome, ToolFailure):
                return outcome
            failure = outcome
            _log_attempt(tool, attempt, outcome)
            if outcome.kind in retry_kinds and attempt < len(RETRY_BACKOFFS_SECONDS):
                await _async_sleep(RETRY_BACKOFFS_SECONDS[attempt])
                continue
            break
        assert failure is not None
        return failure

    async def _single_call(
        self,
        semaphore: asyncio.Semaphore,
        client: Client,
        tool: str,
        arguments: dict,
        timeout: float,
    ) -> "object | ToolFailure":
        """Issue one `call_tool` under a semaphore slot and a timeout; classify any failure.

        The slot is held only across the live call, not across backoff sleeps, so the number of
        in-flight calls never exceeds the semaphore size.
        """
        try:
            async with semaphore:
                async with asyncio.timeout(timeout):
                    result = await client.call_tool(
                        tool, arguments, read_timeout_seconds=timeout
                    )
        except (asyncio.TimeoutError, TimeoutError):
            return ToolFailure(tool, "timeout", "call exceeded timeout")
        except Exception as exc:  # noqa: BLE001 - mapped to a typed kind, never re-raised here
            kind = _classify_failure(exc)
            return ToolFailure(tool, kind, _FAILURE_MESSAGES[kind])
        if result.is_error:
            kind = _classify_failure(result)
            message = _FAILURE_MESSAGES[kind]
            if kind == "tool_error":
                message = f"{message}: {_result_text(result)}" if _result_text(result) else message
            return ToolFailure(tool, kind, message)
        return result

    async def _read_crawl_job(
        self,
        client: Client,
        job_id: str,
        url: str,
        retrieved_at: str,
    ) -> CrawlResult | ToolFailure:
        """Poll `firecrawl_check_crawl_status` by id until complete or the crawl deadline.

        The id belongs to the job on Firecrawl's side, so a timed-out status read is simply asked
        again with the same id on the same `Client`. `firecrawl_crawl` is never sent a second time.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + CRAWL_DEADLINE_SECONDS
        arguments = {FIRECRAWL_STATUS_JOB_ARG: job_id}
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return ToolFailure(
                    FIRECRAWL_STATUS_TOOL,
                    "timeout",
                    f"crawl deadline reached while polling; job_id={job_id}",
                )
            outcome = await self._call_with_retry(
                self._crawl_sem,
                client,
                FIRECRAWL_STATUS_TOOL,
                arguments,
                timeout=min(self._firecrawl_config.call_timeout_seconds, remaining),
                retry_kinds={"rate_limited"},
            )
            if isinstance(outcome, ToolFailure):
                if outcome.kind == "timeout":
                    # Our wait timed out, not the job. Ask again with the same id, bounded by the
                    # overall deadline checked at the top of the loop.
                    continue
                return outcome
            try:
                parsed = _parse_crawl_status(outcome, url, job_id, retrieved_at)
            except _UnparseableResult as exc:
                return ToolFailure(FIRECRAWL_STATUS_TOOL, "unparseable", str(exc))
            if isinstance(parsed, CrawlResult):
                return parsed
            # Still running; wait a poll interval without exceeding the deadline.
            await _async_sleep(min(CRAWL_POLL_INTERVAL_SECONDS, max(0.0, deadline - loop.time())))


# --------------------------------------------------------------------------------------------------
# Pure helpers (tested from fixtures).
# --------------------------------------------------------------------------------------------------
_FAILURE_MESSAGES: dict[str, str] = {
    "tool_error": "tool returned an error",
    "timeout": "call exceeded timeout",
    "rate_limited": "server rate limited the call",
    "transport": "transport error on the session",
    "unparseable": "tool returned an unrecognised body",
}


def _classify_failure(error_or_result: object) -> ToolFailureKind:
    """Map an exception type or an `is_error` result to a failure kind."""
    if isinstance(error_or_result, CallToolResult):
        text = _result_text(error_or_result)
        return "rate_limited" if _RATE_LIMIT_RE.search(text) else "tool_error"
    exc = error_or_result
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status == 429 or _RATE_LIMIT_RE.search(str(exc)):
        return "rate_limited"
    if isinstance(exc, _TRANSPORT_ERRORS):
        return "transport"
    return "tool_error"


def _result_text(result: object) -> str:
    """Concatenate the text blocks of a CallToolResult (empty string when there are none)."""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _decode_body(result: object) -> object:
    """Prefer structured_content, then JSON-decode the text blocks; raise if neither parses."""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    text = _result_text(result)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise _UnparseableResult("tool body was neither structured nor JSON") from exc


def _first_key(data: dict, keys: Sequence[str]) -> object:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _excerpt_text(item: dict) -> str:
    value = _first_key(item, _HIT_TEXT_KEYS)
    if isinstance(value, str):
        return value
    # Some shapes carry the body as a list of excerpt strings.
    excerpts = item.get("excerpts")
    if isinstance(excerpts, list):
        return "\n".join(str(part) for part in excerpts if part)
    return ""


def _parse_search_result(
    result: object,
    objective: str,
    queries: tuple[str, ...],
    retrieved_at: str,
) -> WebSearchResult:
    """Turn a `web_search` body into typed excerpts. An empty body yields zero excerpts."""
    data = _decode_body(result)
    if data is None:
        return WebSearchResult(objective, queries, (), retrieved_at)
    if isinstance(data, dict):
        hits = _first_key(data, _HIT_LIST_KEYS)
        if hits is None:
            # De-mask: a dict with no recognised hit-list key is an unreadable shape, not an empty
            # search. Failing honestly surfaces a real shape mismatch instead of returning a
            # confident empty result (the hit-list key names are an open verification item).
            raise _UnparseableResult("search body had no recognised hit-list key")
    elif isinstance(data, list):
        hits = data
    else:
        raise _UnparseableResult("search body was neither an object nor a list")
    if not isinstance(hits, list):
        raise _UnparseableResult("search hits were not a list")

    excerpts: list[SearchExcerpt] = []
    for hit in hits:
        if not isinstance(hit, dict):
            raise _UnparseableResult("a search hit was not an object")
        excerpts.append(
            SearchExcerpt(
                url=hit.get("url"),
                title=hit.get("title"),
                text=_excerpt_text(hit),
            )
        )
    return WebSearchResult(objective, queries, tuple(excerpts), retrieved_at)


def _extract_pages(data: object) -> list[CrawledPage]:
    if not isinstance(data, dict):
        return []
    raw_pages = _first_key(data, _PAGE_LIST_KEYS)
    if not isinstance(raw_pages, list):
        return []
    pages: list[CrawledPage] = []
    for raw in raw_pages:
        if not isinstance(raw, dict):
            continue
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        url = _first_key(raw, _PAGE_URL_KEYS) or _first_key(metadata, _PAGE_URL_KEYS) or ""
        title = raw.get("title") or (metadata.get("title") if metadata else None)
        text_value = _first_key(raw, _PAGE_TEXT_KEYS)
        pages.append(
            CrawledPage(
                url=str(url),
                title=title,
                text=str(text_value) if text_value is not None else "",
            )
        )
    return pages


def _extract_job_id(data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    value = _first_key(data, _JOB_ID_KEYS)
    return str(value) if value is not None else None


def _status_of(data: object) -> str:
    if isinstance(data, dict):
        status = data.get("status")
        if isinstance(status, str):
            return status.lower()
    return ""


def _parse_crawl_result(
    result: object,
    url: str,
    retrieved_at: str,
) -> "CrawlResult | str":
    """Read the start response: final pages (accepted if returned), or a job id to poll."""
    data = _decode_body(result)
    pages = _extract_pages(data)
    status = _status_of(data)
    job_id = _extract_job_id(data)
    if pages and status not in _CRAWL_RUNNING_STATUSES:
        return CrawlResult(url, job_id, tuple(pages), retrieved_at)
    if job_id:
        return job_id
    if pages:
        return CrawlResult(url, job_id, tuple(pages), retrieved_at)
    raise _UnparseableResult("crawl start had neither pages nor a job id")


def _parse_crawl_status(
    result: object,
    url: str,
    job_id: str,
    retrieved_at: str,
) -> CrawlResult | None:
    """Read a status response: a `CrawlResult` when complete, None while running.

    De-mask: a body that is neither a recognised running state nor a recognised terminal state, and
    carries no pages, is an unreadable shape — surfaced as `_UnparseableResult` rather than polled on
    until the deadline (which would mislabel a shape mismatch as a timeout). The status vocabularies
    are an open verification item, so an unlisted word fails loudly here on first contact.
    """
    data = _decode_body(result)
    pages = _extract_pages(data)
    status = _status_of(data)
    if status in _CRAWL_RUNNING_STATUSES:
        return None
    if status in _CRAWL_DONE_STATUSES:
        return CrawlResult(url, job_id, tuple(pages), retrieved_at)
    # Some servers return pages without a terminal status word; accept them.
    if pages:
        return CrawlResult(url, job_id, tuple(pages), retrieved_at)
    raise _UnparseableResult(
        f"crawl status body had an unrecognised status {status!r} and no pages"
    )


def _log_attempt(tool: str, attempt: int, failure: ToolFailure) -> None:
    """Record one failed attempt; no secret ever enters the record."""
    logger.info(
        json.dumps(
            {
                "event": "mcp.call_attempt_failed",
                "timestamp": _timestamp(),
                "tool": tool,
                "attempt": attempt,
                "kind": failure.kind,
                "message": failure.message,
            }
        )
    )


# --------------------------------------------------------------------------------------------------
# Composition root.
# --------------------------------------------------------------------------------------------------
def _normalize_key(value: str | None) -> str | None:
    """Treat a blank or whitespace-only env value as no key, so keyless handling stays `is None`."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def create_mcp_tool_gateway(settings: Settings) -> McpToolGateway:
    """Build the gateway from settings. Opens nothing: no I/O, no session until `open()`."""
    parallel = McpServerConfig(
        name="parallel",
        url=settings.parallel_mcp_url,
        api_key=_normalize_key(settings.parallel_api_key),
        call_timeout_seconds=SEARCH_TIMEOUT_SECONDS,
    )
    firecrawl = McpServerConfig(
        name="firecrawl",
        url=settings.firecrawl_mcp_url,
        api_key=_normalize_key(settings.firecrawl_api_key),
        call_timeout_seconds=CRAWL_CALL_TIMEOUT_SECONDS,
    )
    return McpToolGateway(parallel, firecrawl)
