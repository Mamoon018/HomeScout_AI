"""R2 Mechanism 3 Component C3.1.1 — async MCP tool gateway.

A client-boundary capability that exposes typed operations over two hosted MCP servers:
`search_web` (Parallel `web_search`), `map_site` (Firecrawl `firecrawl_map`) and `scrape_page`
(Firecrawl `firecrawl_scrape`), which M3 drives, plus `crawl_site` (Firecrawl `firecrawl_crawl`, read
to completion through `firecrawl_check_crawl_status`), retained but unused by M3. Nothing above this
module imports `mcp`; callers see only the typed result contracts and the `ToolGateway` Protocol.

Ownership notes fixed against the real SDK (`mcp==2.2.0`):
- `mcp.Client` holds an anyio task group, so it must be entered and exited in the same task. Each
  server therefore runs in its own owner task (`_ServerSession`); `open()` and `aclose()` may run
  in different tasks of the caller, but the context enter/exit always happen in the owner task.
- `Client` is one-shot and not re-enterable. The gateway never reconnects or replaces a `Client`:
  a timeout is our side giving up on one wait, so the open session stays in use for the next call.
- The caller-owned HTTP client is `httpx2.AsyncClient`; the default factory attaches the bearer
  header there and omits it when the key is `None`.

Only two conditions raise (`McpConnectionError`, `McpToolUnavailableError`): a session cannot be
opened, or a required tool or argument is missing at connect. Every per-call problem is returned as
a `ToolFailure`, so one failed call never aborts a concurrent gather. A wrong Firecrawl output shape,
if it ever recurs, surfaces per-call as `ToolFailure(unparseable)` on the first real map/scrape.
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
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult

from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# --------------------------------------------------------------------------------------------------
# Composition-root constants. Unmeasured starting values; revisit once a live capture exists.
# --------------------------------------------------------------------------------------------------
SEARCH_TIMEOUT_SECONDS = 30.0
# Map and scrape are single requests with no job id, so each has its own per-call bound; they are
# not tied to the crawl timeout below. Raised to 60 s (M10) so the budget covers a short queue
# behind the 2-browser limit; Firecrawl's one clock counts queue wait against the job (OV-10).
MAP_TIMEOUT_SECONDS = 60.0
SCRAPE_TIMEOUT_SECONDS = 60.0
# Each start or status call is bounded by its server's own per-call timeout; this caps the whole
# crawl-plus-poll wait so a stuck job cannot block a run forever.
CRAWL_CALL_TIMEOUT_SECONDS = 60.0
CRAWL_DEADLINE_SECONDS = 180.0
# Transient backoff for timeout/transport blips: retry fast on the same session.
RETRY_BACKOFFS_SECONDS = (2.0, 3.0)
# Rate-limited backoff (M8): a per-minute window needs a wait approaching 60 s, so two short waits
# would both fall inside the same throttled minute. Honor a response Retry-After when present
# (OV-8); the window figure is confirmed from Firecrawl's limits page.
RATE_LIMIT_BACKOFFS_SECONDS = (30.0, 60.0)
CRAWL_POLL_INTERVAL_SECONDS = 3.0
SEARCH_CONCURRENCY = 4
# One slot pool for every Firecrawl call (map, scrape, crawl, and the scrape_pages fan-out). Sized
# to the plan's concurrent-browser limit (Free = 2) so the gateway does not self-induce 429s (M9).
FIRECRAWL_CONCURRENCY = 2
# Proactive per-minute cap for the Firecrawl path (A7). Firecrawl Free allows 10 /scrape requests
# per minute per key (team-shared); the gateway paces itself to that so a scrape_pages fan-out does
# not burst past it and churn on reactive 429 backoff. Applies to every Firecrawl call; the Parallel
# web_search path is excluded (separate server/key). Starting value; confirm the window shape (OV-13).
FIRECRAWL_RATE_PER_MINUTE = 10
# Retained Settings field; no longer used for a connect-time probe (the probe was removed once a
# live run confirmed the 3.x JSON output shape). Kept so re-adding a probe needs no config change.
FIRECRAWL_PROBE_URL_DEFAULT = "https://example.com"

# MCP tool and argument names required on each server. Checked at connect; a miss raises.
PARALLEL_SEARCH_TOOL = "web_search"
PARALLEL_SEARCH_ARGS = ("objective", "search_queries")
FIRECRAWL_MAP_TOOL = "firecrawl_map"
FIRECRAWL_MAP_ARGS = ("url",)
FIRECRAWL_SCRAPE_TOOL = "firecrawl_scrape"
FIRECRAWL_SCRAPE_ARGS = ("url", "formats")
# The crawl and status tools are retained for crawl_site, but M3 does not use them, so they are not
# part of the connect-time requirement.
FIRECRAWL_CRAWL_TOOL = "firecrawl_crawl"
FIRECRAWL_STATUS_TOOL = "firecrawl_check_crawl_status"
# The job-id argument of the status tool. Provisional from the Firecrawl MCP docs; fixed from the
# live capture. Isolated here so the open verification item is a one-line change.
FIRECRAWL_STATUS_JOB_ARG = "id"
# (Iteration 5, R2/R3) The hosted /v2 endpoint exposes no batch tool, so scrape_pages fans out
# firecrawl_scrape; the former batch tool-name candidates and batch-job constants were removed.

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

_RATE_LIMIT_RE = re.compile(r"rate.?limit|too many requests|429|retry.?after", re.IGNORECASE)
# An MCPError whose message is the Streamable-HTTP SSE disconnect (the stream dropped and the SDK's
# GET-based resume was exhausted). Classified `transport` (M6) so it retries, rather than `tool_error`
# which would surface as a misleading tool error instead of retrying. Matched on the message, not the
# type alone, so a genuine tool error wrapped as MCPError is not retried forever.
_SSE_DISCONNECT_RE = re.compile(r"sse stream ended|reconnection attempts", re.IGNORECASE)

# Failure kinds that mean a call could not complete, as opposed to returning a wrong body. Search,
# map and scrape are idempotent reads, so these are the kinds they retry on the same session.
_TRANSIENT_KINDS = ("timeout", "transport", "rate_limited")

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
class MapLink:
    """One candidate page of a mapped site."""

    url: str
    title: str | None
    description: str | None


@dataclass(frozen=True)
class MapResult:
    """Typed `firecrawl_map` outcome. An empty link list is a valid result, not a failure."""

    url: str
    links: tuple[MapLink, ...]
    retrieved_at: str


@dataclass(frozen=True)
class ScrapeResult:
    """Typed `firecrawl_scrape` outcome. `url` is `metadata.sourceURL` as the server reports it.

    Per Firecrawl's API docs `sourceURL` is the URL that was requested; the post-redirect URL is the
    separate `metadata.url`, which this contract does not carry. Callers key evidence by this value
    and should not assume it differs from the request (not verified against a live response).
    Empty `text` with a source URL is a valid result, not a failure.
    """

    url: str
    text: str
    retrieved_at: str


@dataclass(frozen=True)
class ScrapeResults:
    """Typed outcome of `scrape_pages`: a concurrent `scrape_page` fan-out over many URLs (M13).

    `pages` is one `ScrapeResult` per URL that scraped successfully, each keyed by its own
    `metadata.sourceURL`. A URL whose scrape failed is recorded in `failed_urls` (a signalled
    degrade), not as a whole-call `ToolFailure`. An empty `pages` tuple is a valid result, not a
    failure. There is no server job: the aggregate is built from N single-page scrapes.
    """

    pages: tuple[ScrapeResult, ...]
    total: int
    completed: int
    failed_urls: tuple[str, ...]
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

    async def map_site(self, url: str) -> MapResult | ToolFailure: ...

    async def scrape_page(self, url: str) -> ScrapeResult | ToolFailure: ...

    async def scrape_pages(
        self, urls: Sequence[str], *, formats: Sequence[str] = ("markdown",)
    ) -> ScrapeResults | ToolFailure: ...

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
        # read=None leaves the long-lived SSE response stream unbounded at the transport (M5), so a
        # slow-but-live map/scrape/batch is not severed by httpx's 5 s read default. Duration is
        # bounded in one place: the per-call asyncio.timeout and the SDK read_timeout_seconds.
        # connect/write/pool stay bounded so a dead TCP connect still fails fast.
        timeout = httpx2.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client:
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
# Per-minute rate limiter (A7).
# --------------------------------------------------------------------------------------------------
class _TokenBucket:
    """A per-minute throttle: at most `per_minute` acquisitions per `window_seconds` (A7).

    `acquire()` awaits until a token is free, then takes one; it never drops a call, it paces it.
    Tokens refill continuously at `per_minute / window` so starts are spread smoothly rather than
    released in a burst at the top of each minute. One instance is shared by every Firecrawl call
    on the gateway, so the concurrent `scrape_pages` fan-out and any map/scrape/crawl contend for
    the same budget. The counter is guarded by a lock and read off the monotonic loop clock; the
    wait is an on-loop sleep, so callers acquire a token *outside* a call's own timeout (waiting for
    the window is not the call being slow).
    """

    def __init__(self, per_minute: int, *, window_seconds: float = 60.0) -> None:
        self._capacity = float(max(1, per_minute))
        self._window = window_seconds
        self._rate = self._capacity / window_seconds  # tokens per second
        self._tokens = self._capacity
        self._updated: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = asyncio.get_event_loop().time()
                if self._updated is None:
                    self._updated = now
                elapsed = now - self._updated
                if elapsed > 0:
                    self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                    self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            # Released the lock before sleeping so other coroutines can refill/take in the meantime.
            await _async_sleep(wait)


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
        firecrawl_concurrency: int = FIRECRAWL_CONCURRENCY,
        firecrawl_rate_per_minute: int = FIRECRAWL_RATE_PER_MINUTE,
        firecrawl_probe_url: str = FIRECRAWL_PROBE_URL_DEFAULT,
        client_factory: ClientFactory = _streamable_http_factory,
    ) -> None:
        self._parallel_config = parallel
        self._firecrawl_config = firecrawl
        self._parallel = _ServerSession(parallel, client_factory)
        self._firecrawl = _ServerSession(firecrawl, client_factory)
        # Retained from Settings; no longer used (the connect-time probe was removed, R4).
        self._probe_url = firecrawl_probe_url
        # Per-server bounds: a slow Firecrawl call must not starve searches, so each server has its
        # own slot pool. The Firecrawl pool is shared by map, scrape, the scrape_pages fan-out and
        # the retained crawl path. The per-minute bucket (A7) is a second, shared Firecrawl gate.
        self._search_sem = asyncio.Semaphore(search_concurrency)
        self._firecrawl_sem = asyncio.Semaphore(firecrawl_concurrency)
        self._firecrawl_rate = _TokenBucket(firecrawl_rate_per_minute)

    async def open(self) -> None:
        """Start both sessions together, then verify both catalogs.

        Any non-local exit — a start failure, a verify failure, or a cancellation of the caller
        mid-open — tears both sessions down before leaving, so a partially-opened gateway never
        leaks an owner task or its client. (The connect-time Firecrawl shape probe was removed in
        iteration 5, R4: a live run confirmed the 3.x JSON shape, so `open()` runs the capability
        check only; a wrong shape would surface per-call as `ToolFailure(unparseable)`.)
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
        """List tools on both servers (cache bypassed) and match the required names and arguments.

        Search, map and scrape are required by exact name. No batch tool is checked or required:
        `scrape_pages` calls no MCP batch tool (it fans out `firecrawl_scrape`, already required).
        The crawl and status tools stay available through `crawl_site` but are not checked: a later
        crawl call would surface a missing one as a per-call `ToolFailure`.
        """
        parallel_tools, firecrawl_tools = await asyncio.gather(
            self._list_tools(self._parallel),
            self._list_tools(self._firecrawl),
        )
        self._require(
            parallel_tools, PARALLEL_SEARCH_TOOL, PARALLEL_SEARCH_ARGS, self._parallel_config.name
        )
        self._require(
            firecrawl_tools, FIRECRAWL_MAP_TOOL, FIRECRAWL_MAP_ARGS, self._firecrawl_config.name
        )
        self._require(
            firecrawl_tools,
            FIRECRAWL_SCRAPE_TOOL,
            FIRECRAWL_SCRAPE_ARGS,
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
        # Boundary crossing: the exact catalog the server returned is external, non-deterministic,
        # and unrecoverable after the fact, so it is recorded. It answers "which tools exist here,
        # and is a batch tool among them?" without re-running. `tools` lists every name; `args`
        # carries each tool's argument names so a name/arg mismatch is visible in one line.
        logger.info(
            json.dumps(
                {
                    "event": "mcp.tools_listed",
                    "timestamp": _timestamp(),
                    "server": session._config.name,
                    "tool_count": len(catalog),
                    "tools": sorted(catalog),
                    "args": {name: sorted(catalog[name]) for name in sorted(catalog)},
                }
            )
        )
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

    async def map_site(self, url: str) -> MapResult | ToolFailure:
        """Run `firecrawl_map` on a site homepage with transient retry and parse the link set.

        The URL is app-injected; the LLM never supplies it. The gateway does not host-filter or cap
        the result: candidate shaping belongs to the caller (C3.1.6).
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError("map url must be an http(s) URL")
        client = self._firecrawl.client()
        retrieved_at = _timestamp()
        outcome = await self._call_with_retry(
            self._firecrawl_sem,
            client,
            FIRECRAWL_MAP_TOOL,
            {"url": url},
            timeout=MAP_TIMEOUT_SECONDS,
            retry_kinds=set(_TRANSIENT_KINDS),
            target=url,
            rate=self._firecrawl_rate,
        )
        if isinstance(outcome, ToolFailure):
            return outcome
        try:
            return _parse_map_result(outcome, url, retrieved_at)
        except _UnparseableResult as exc:
            return ToolFailure(FIRECRAWL_MAP_TOOL, "unparseable", str(exc))

    async def scrape_page(self, url: str) -> ScrapeResult | ToolFailure:
        """Run `firecrawl_scrape` for one page as markdown with transient retry and parse it.

        The URL is app-resolved upstream (C3.1.3). The returned `ScrapeResult.url` is the source
        URL the server reports and may differ from the URL requested.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError("scrape url must be an http(s) URL")
        client = self._firecrawl.client()
        retrieved_at = _timestamp()
        arguments = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
        outcome = await self._call_with_retry(
            self._firecrawl_sem,
            client,
            FIRECRAWL_SCRAPE_TOOL,
            arguments,
            timeout=SCRAPE_TIMEOUT_SECONDS,
            retry_kinds=set(_TRANSIENT_KINDS),
            target=url,
            rate=self._firecrawl_rate,
        )
        if isinstance(outcome, ToolFailure):
            return outcome
        try:
            return _parse_scrape_result(outcome, retrieved_at)
        except _UnparseableResult as exc:
            return ToolFailure(FIRECRAWL_SCRAPE_TOOL, "unparseable", str(exc))

    async def scrape_pages(
        self, urls: Sequence[str], *, formats: Sequence[str] = ("markdown",)
    ) -> ScrapeResults | ToolFailure:
        """Scrape many app-shortlisted URLs by fanning out one `scrape_page` per URL (M13).

        The hosted endpoint exposes no batch tool, so this runs N concurrent single-page scrapes,
        each bounded by the shared Firecrawl semaphore and the per-minute token bucket, gathered
        with `return_exceptions=True` so one URL's failure does not fail the rest. A URL whose
        scrape returns a `ToolFailure` (or, unexpectedly, raises) rides `failed_urls`; the successes
        populate `pages`. The URL list is app-resolved upstream (C3.1.6); the LLM never supplies it.
        `formats` is accepted for contract parity; `scrape_page` returns markdown, which is all M3 reads.
        """
        page_urls = [u for u in urls]
        if not page_urls:
            raise ValueError("scrape_pages urls must be a non-empty sequence")
        for u in page_urls:
            if not u.startswith(("http://", "https://")):
                raise ValueError("every scrape_pages url must be an http(s) URL")
        retrieved_at = _timestamp()
        # gather, not a per-page serial loop: scraping is independent per URL, and the shared
        # _firecrawl_sem + _firecrawl_rate pace it to ≤2 in-flight and ≤10/min automatically.
        results = await asyncio.gather(
            *(self.scrape_page(u) for u in page_urls), return_exceptions=True
        )
        pages: list[ScrapeResult] = []
        failed: list[str] = []
        for url, result in zip(page_urls, results):
            if isinstance(result, ScrapeResult):
                pages.append(result)
            else:
                # A per-URL ToolFailure (returned) or an unexpected exception (gather collected it):
                # this URL failed and rides failed_urls while the rest complete.
                failed.append(url)
        if failed:
            # A degrade raises nothing, so this WARN is the only evidence some URLs were dropped.
            logger.warning(
                json.dumps(
                    {
                        "event": "mcp.scrape_pages_partial",
                        "timestamp": _timestamp(),
                        "total": len(page_urls),
                        "completed": len(pages),
                        "failed": len(failed),
                    }
                )
            )
        return ScrapeResults(
            pages=tuple(pages),
            total=len(page_urls),
            completed=len(pages),
            failed_urls=tuple(failed),
            retrieved_at=retrieved_at,
        )

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
            self._firecrawl_sem,
            client,
            FIRECRAWL_CRAWL_TOOL,
            arguments,
            timeout=self._firecrawl_config.call_timeout_seconds,
            retry_kinds={"rate_limited"},
            rate=self._firecrawl_rate,
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
        target: str | None = None,
        rate: _TokenBucket | None = None,
    ) -> "object | ToolFailure":
        """One bounded call with transient retry; reuses the same `Client` on every attempt.

        `target` is the page a map or scrape call is for; it is carried only into the failure log
        so a failed attempt can be tied to its page. `rate` is the per-minute bucket for the
        Firecrawl path (A7); each attempt takes a token (a retry is another real call), and the
        Parallel path passes `None`.
        """
        failure: ToolFailure | None = None
        max_retries = len(RETRY_BACKOFFS_SECONDS)
        for attempt in range(max_retries + 1):
            outcome = await self._single_call(semaphore, client, tool, arguments, timeout, rate)
            if not isinstance(outcome, ToolFailure):
                return outcome
            failure = outcome
            _log_attempt(tool, attempt, outcome, target)
            if outcome.kind in retry_kinds and attempt < max_retries:
                # Backoff by kind (M8): a rate limit needs a wait that clears the per-minute window,
                # while a timeout/transport blip retries fast. Both sequences are the same length.
                backoffs = (
                    RATE_LIMIT_BACKOFFS_SECONDS
                    if outcome.kind == "rate_limited"
                    else RETRY_BACKOFFS_SECONDS
                )
                await _async_sleep(backoffs[attempt])
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
        rate: _TokenBucket | None = None,
    ) -> "object | ToolFailure":
        """Issue one `call_tool` under a semaphore slot and a timeout; classify any failure.

        The slot is held only across the live call, not across backoff sleeps, so the number of
        in-flight calls never exceeds the semaphore size. A `rate` bucket (A7, Firecrawl path) is
        acquired *before* the slot and *outside* the per-call timeout — waiting for the per-minute
        window is pacing, not the call being slow, so it must not count against the call's budget.
        """
        try:
            if rate is not None:
                await rate.acquire()
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
                self._firecrawl_sem,
                client,
                FIRECRAWL_STATUS_TOOL,
                arguments,
                timeout=min(self._firecrawl_config.call_timeout_seconds, remaining),
                retry_kinds={"rate_limited"},
                rate=self._firecrawl_rate,
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
    # M7: a 429 counts as rate_limited whether it arrives as a status code/response or buried in
    # the exception text (including an MCPError's message), so this is checked before the generic
    # MCPError disconnect branch below.
    if status == 429 or _RATE_LIMIT_RE.search(str(exc)):
        return "rate_limited"
    # M6: the SDK's own SSE-ended / reconnection-exhausted MCPError is a transport fault, so it is
    # retried on the same session; other MCPError messages stay tool_error (de-mask on the message).
    if isinstance(exc, MCPError) and _SSE_DISCONNECT_RE.search(str(exc)):
        return "transport"
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


def _opt_str(value: object) -> str | None:
    """A stripped non-empty string, else None."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_map_result(result: object, url: str, retrieved_at: str) -> MapResult:
    """Turn a `firecrawl_map` body into typed candidate links.

    The body must be an object with a `links` list of `{url, title?, description?}` objects (a plain
    string entry is tolerated). An empty list is a valid, genuinely empty site. A body with no
    `links` list, or a non-empty list with no usable entry, is an unreadable shape (de-mask), not
    an empty result.
    """
    data = _decode_body(result)
    if not isinstance(data, dict):
        raise _UnparseableResult("map body was not an object")
    raw_links = data.get("links")
    if not isinstance(raw_links, list):
        raise _UnparseableResult("map body had no links list")
    links: list[MapLink] = []
    skipped = 0
    for raw in raw_links:
        link_url = _opt_str(raw if isinstance(raw, str) else raw.get("url") if isinstance(raw, dict) else None)
        if link_url is None:
            skipped += 1
            continue
        if isinstance(raw, dict):
            links.append(
                MapLink(
                    url=link_url,
                    title=_opt_str(raw.get("title")),
                    description=_opt_str(raw.get("description")),
                )
            )
        else:
            links.append(MapLink(url=link_url, title=None, description=None))
    if raw_links and not links:
        raise _UnparseableResult("map body had links but none were usable")
    if skipped:
        # A degrade raises nothing, so this line is the only evidence candidates were dropped.
        logger.warning(
            json.dumps(
                {
                    "event": "mcp.map_links_skipped",
                    "timestamp": _timestamp(),
                    "url": url,
                    "skipped": skipped,
                    "kept": len(links),
                }
            )
        )
    return MapResult(url, tuple(links), retrieved_at)


def _parse_scrape_result(result: object, retrieved_at: str) -> ScrapeResult:
    """Turn a `firecrawl_scrape` body into one typed page keyed by its source URL.

    The body must be an object with a top-level string `markdown` and a non-empty string
    `metadata.sourceURL`. Empty markdown with a source URL is a valid empty page. A wrapped
    (`data`) envelope, or a missing key, is an unreadable shape; no older-shape tolerance is built —
    a wrong (older-version) shape fails loudly here as `_UnparseableResult` → `ToolFailure(unparseable)`
    on first contact, rather than yielding blank evidence.
    """
    data = _decode_body(result)
    if not isinstance(data, dict):
        raise _UnparseableResult("scrape body was not an object")
    markdown = data.get("markdown")
    if not isinstance(markdown, str):
        raise _UnparseableResult("scrape body had no markdown text")
    metadata = data.get("metadata")
    source_url = _opt_str(metadata.get("sourceURL")) if isinstance(metadata, dict) else None
    if source_url is None:
        raise _UnparseableResult("scrape body had no metadata.sourceURL")
    return ScrapeResult(source_url, markdown, retrieved_at)


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


def _log_attempt(
    tool: str, attempt: int, failure: ToolFailure, target: str | None = None
) -> None:
    """Record one failed attempt as WARN; no secret ever enters the record.

    A failed attempt that is retried is a handled drift (it raises nothing), so it logs at WARN.
    `target` is the page for a map or scrape call, a URL and never a secret.
    """
    record = {
        "event": "mcp.call_attempt_failed",
        "timestamp": _timestamp(),
        "tool": tool,
        "attempt": attempt,
        "kind": failure.kind,
        "message": failure.message,
    }
    if target is not None:
        record["target"] = target
    logger.warning(json.dumps(record))


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
    return McpToolGateway(
        parallel,
        firecrawl,
        firecrawl_probe_url=_normalize_key(settings.firecrawl_probe_url)
        or FIRECRAWL_PROBE_URL_DEFAULT,
    )
