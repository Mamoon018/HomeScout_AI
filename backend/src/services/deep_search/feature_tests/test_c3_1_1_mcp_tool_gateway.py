"""Behavior tests for R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

Plan: `C3_1_1_mcp_tool_gateway_test_plan.md` (same folder). Test ids (T1..) match the plan.

No live calls and no keys. The hosted Parallel and Firecrawl servers are the only thing faked: each
is an in-process `MCPServer` wired in through the gateway's `client_factory` seam, so the real
gateway (owner tasks, capability check, shape probe, retry, timeout, parsing, semaphores, close) and
the real `mcp.Client` run against a deterministic vendor. The real-HTTP tests (T48, T49, T61) go
further and run the production `_streamable_http_factory` over real loopback HTTP, because every
other test bypasses that factory. Iteration-3 tests (T50-T61) cover fixes M5-M10 and A4.

Because `open()` probes Firecrawl once (one map and one scrape of the probe URL), every Firecrawl
fixture serves MCP server 3.x JSON-shaped map and scrape bodies by default; a handler that fails on purpose is
wrapped with `_except_probe` so the probe still passes and only the page under test fails.

Run from `backend/`:
    python -m pytest src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py -q
"""

import asyncio
import json
import logging
import socket
import threading
import time
from contextlib import asynccontextmanager

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from mcp.shared.exceptions import MCPError

from src.clients import mcp_tools
from src.clients.mcp_tools import (
    BatchScrapeResult,
    CrawlResult,
    MapResult,
    McpServerConfig,
    McpToolGateway,
    ScrapeResult,
    ToolFailure,
    WebSearchResult,
    _classify_failure,
    create_mcp_tool_gateway,
)
from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError

_PROBE_URL = "https://example.com"
_SITE = "https://x.test"
_DEFAULT_SEARCH_BODY = {"results": [{"url": "http://a", "title": "A", "excerpts": ["body"]}]}
_DEFAULT_MAP_BODY = {
    "links": [{"url": "https://example.com/a", "title": "A", "description": "page a"}]
}
_DEFAULT_SCRAPE_BODY = {"markdown": "page text", "metadata": {"sourceURL": _PROBE_URL}}
_DEFAULT_CRAWL_PAGES = {
    "status": "completed",
    "data": [{"url": "http://p/1", "title": "P1", "markdown": "page one"}],
}
_HANG = object()  # factory target: the connect never completes


# ------------------------------------------------------------------------------------- handlers
def _static(value):
    async def handler(*_args, **_kwargs):
        return value

    return handler


def _except_probe(handler, default):
    """Answer the connect-time probe URL with `default`; send every other URL to `handler`."""

    async def wrapped(url, *rest):
        if url == _PROBE_URL:
            return default
        return await handler(url, *rest)

    return wrapped


def _rate_limited_after_probe(counter: dict | None = None):
    async def handler(*_args):
        if counter is not None:
            counter["n"] += 1
        raise ToolError("rate limit exceeded")

    return handler


def _text_result(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=False)


# ------------------------------------------------------------------------------------- servers
def _parallel_server(handler=None, *, include_queries_arg: bool = True) -> MCPServer:
    server = MCPServer(name="parallel-srv")
    handler = handler or _static(_DEFAULT_SEARCH_BODY)
    if include_queries_arg:

        @server.tool()
        async def web_search(objective: str, search_queries: list[str]):  # noqa: D401
            return await handler(objective, search_queries)

    else:

        @server.tool()
        async def web_search(objective: str):  # noqa: D401, F811
            return await handler(objective)

    return server


_DEFAULT_BATCH_START = {"id": "batch-1"}
_DEFAULT_BATCH_STATUS = {
    "status": "completed",
    "total": 2,
    "completed": 2,
    "data": [
        {"markdown": "page one", "metadata": {"sourceURL": "https://x.test/1"}},
        {"markdown": "page two", "metadata": {"sourceURL": "https://x.test/2"}},
    ],
}


def _firecrawl_server(
    *,
    crawl_handler=None,
    status_handler=None,
    map_handler=None,
    scrape_handler=None,
    batch_handler=None,
    batch_status_handler=None,
    include_crawl: bool = True,
    include_status: bool = True,
    include_map: bool = True,
    include_scrape: bool = True,
    include_batch: bool = True,
    include_formats_arg: bool = True,
) -> MCPServer:
    """In-process Firecrawl. Every tool is toggleable; map and scrape default to 3.x JSON bodies."""
    server = MCPServer(name="firecrawl-srv")
    crawl_handler = crawl_handler or _static({"id": "job-1"})
    status_handler = status_handler or _static(_DEFAULT_CRAWL_PAGES)
    map_handler = map_handler or _static(_DEFAULT_MAP_BODY)
    scrape_handler = scrape_handler or _static(_DEFAULT_SCRAPE_BODY)
    batch_handler = batch_handler or _static(_DEFAULT_BATCH_START)
    batch_status_handler = batch_status_handler or _static(_DEFAULT_BATCH_STATUS)
    if include_batch:

        @server.tool()
        async def firecrawl_batch_scrape(
            urls: list[str], formats: list[str], onlyMainContent: bool = True,  # noqa: N803
            maxConcurrency: int = 2,  # noqa: N803
        ):
            return await batch_handler(urls, formats, onlyMainContent, maxConcurrency)

        @server.tool()
        async def firecrawl_check_batch_scrape_status(id: str, skip: int = 0):  # noqa: A002
            return await batch_status_handler(id, skip)

    if include_crawl:

        @server.tool()
        async def firecrawl_crawl(
            url: str, limit: int, maxDiscoveryDepth: int, allowExternalLinks: bool  # noqa: N803
        ):
            return await crawl_handler(url, limit, maxDiscoveryDepth, allowExternalLinks)

    if include_status:

        @server.tool()
        async def firecrawl_check_crawl_status(id: str):  # noqa: A002
            return await status_handler(id)

    if include_map:

        @server.tool()
        async def firecrawl_map(url: str):
            return await map_handler(url)

    if include_scrape:
        if include_formats_arg:

            @server.tool()
            async def firecrawl_scrape(
                url: str, formats: list[str], onlyMainContent: bool = True  # noqa: N803
            ):
                return await scrape_handler(url, formats, onlyMainContent)

        else:

            @server.tool()
            async def firecrawl_scrape(url: str):  # noqa: F811
                return await scrape_handler(url, None, None)

    return server


# ------------------------------------------------------------------------------------- factory
class _FlakyClient:
    """Wraps a connected `Client` and raises the queued exceptions on `call_tool`.

    Models the network edge (a dropped connection) that an in-process server cannot produce. Only
    `call_tool` is flaky; the capability listing passes straight through.
    """

    def __init__(self, inner: Client, failures: list[BaseException]) -> None:
        self._inner = inner
        self.failures = list(failures)

    async def list_tools(self, **kwargs):
        return await self._inner.list_tools(**kwargs)

    async def call_tool(self, name, arguments, **kwargs):
        if self.failures:
            raise self.failures.pop(0)
        return await self._inner.call_tool(name, arguments, **kwargs)


def _factory(targets: dict, events: list | None = None, flaky: dict | None = None):
    """Map config.name -> an MCPServer (or an exception/_HANG for a failing connect).

    `events` receives ("open", name) when a session is ready and ("close", name) when its context
    exits, so tests can see that a client was built once and released.
    """

    def factory(config: McpServerConfig):
        @asynccontextmanager
        async def cm():
            target = targets[config.name]
            if isinstance(target, BaseException):
                raise target
            if target is _HANG:
                await asyncio.sleep(3600)
            async with Client(target) as client:
                if events is not None:
                    events.append(("open", config.name))
                try:
                    if flaky and config.name in flaky:
                        yield _FlakyClient(client, flaky[config.name])
                    else:
                        yield client
                finally:
                    if events is not None:
                        events.append(("close", config.name))

        return cm()

    return factory


def _gateway(
    parallel_target,
    firecrawl_target,
    *,
    parallel_timeout: float = 5.0,
    firecrawl_timeout: float = 5.0,
    search_concurrency: int = 4,
    firecrawl_concurrency: int = 2,
    probe_url: str = _PROBE_URL,
    api_key: str | None = None,
    events: list | None = None,
    flaky: dict | None = None,
) -> McpToolGateway:
    parallel = McpServerConfig("parallel", "http://parallel", api_key, parallel_timeout)
    firecrawl = McpServerConfig("firecrawl", "http://firecrawl", api_key, firecrawl_timeout)
    factory = _factory(
        {"parallel": parallel_target, "firecrawl": firecrawl_target}, events, flaky
    )
    return McpToolGateway(
        parallel,
        firecrawl,
        search_concurrency=search_concurrency,
        firecrawl_concurrency=firecrawl_concurrency,
        firecrawl_probe_url=probe_url,
        client_factory=factory,
    )


@pytest.fixture
def no_wait(monkeypatch):
    """Replace the gateway's retry/poll sleep with an immediate recorder of its durations."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(mcp_tools, "_async_sleep", fake_sleep)
    return waits


@pytest.fixture
def short_wait(monkeypatch):
    """Like `no_wait` but yields real (10 ms) time, for loops bounded by a real deadline."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        await asyncio.sleep(0.01)

    monkeypatch.setattr(mcp_tools, "_async_sleep", fake_sleep)
    return waits


def _session_tasks() -> set:
    return {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def _log_events(caplog, event: str) -> list[dict]:
    found = []
    for record in caplog.records:
        try:
            body = json.loads(record.getMessage())
        except ValueError:
            continue
        if isinstance(body, dict) and body.get("event") == event:
            found.append(body)
    return found


# ===================================================================================== Capability
async def test_t1_open_succeeds_when_required_tools_and_args_are_present() -> None:
    events: list = []
    gateway = _gateway(_parallel_server(), _firecrawl_server(), events=events)
    await gateway.open()
    await gateway.aclose()
    # One client per server, and both released on close.
    assert sorted(events) == [
        ("close", "firecrawl"),
        ("close", "parallel"),
        ("open", "firecrawl"),
        ("open", "parallel"),
    ]


@pytest.mark.parametrize(
    ("parallel", "firecrawl", "missing"),
    [
        (_parallel_server(include_queries_arg=False), _firecrawl_server(), "search_queries"),
        (_parallel_server(), _firecrawl_server(include_map=False), "firecrawl_map"),
        (_parallel_server(), _firecrawl_server(include_scrape=False), "firecrawl_scrape"),
        (_parallel_server(), _firecrawl_server(include_formats_arg=False), "formats"),
    ],
    ids=["parallel_arg", "map_tool", "scrape_tool", "scrape_arg"],
)
async def test_t2_missing_required_tool_or_argument_fails_at_connect(
    parallel, firecrawl, missing
) -> None:
    before = _session_tasks()
    gateway = _gateway(parallel, firecrawl)
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"
    assert missing in str(exc.value)
    await _settle()
    assert _session_tasks() == before  # a failed connect leaves nothing running


async def test_t3_crawl_tools_are_not_required_and_fail_per_call(no_wait) -> None:
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(include_crawl=False, include_status=False)
    )
    await gateway.open()  # M3 does not drive crawl, so a server without it still connects
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)  # the gap surfaces per call, not as a raise
    assert result.tool == "firecrawl_crawl"


# ===================================================================================== Probe
async def test_t4_probe_maps_and_scrapes_the_configured_url_after_the_capability_check() -> None:
    events: list[str] = []

    async def map_handler(url):
        events.append(f"map:{url}")
        return _DEFAULT_MAP_BODY

    async def scrape_handler(url, _formats, _only_main):
        events.append(f"scrape:{url}")
        return {"markdown": "text", "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(map_handler=map_handler, scrape_handler=scrape_handler),
        probe_url="https://probe.test",
    )
    original = gateway.verify_capabilities

    async def traced() -> None:
        events.append("capabilities")
        await original()

    gateway.verify_capabilities = traced
    await gateway.open()
    await gateway.aclose()
    assert events[0] == "capabilities"
    assert sorted(events[1:]) == ["map:https://probe.test", "scrape:https://probe.test"]


@pytest.mark.parametrize(
    ("scrape_body", "map_body"),
    [
        ({"markdown": "text", "metadata": {}}, None),
        ({"markdown": "text"}, None),
        (
            {"success": True, "data": {"markdown": "t", "metadata": {"sourceURL": _PROBE_URL}}},
            None,
        ),
        ({"markdown": "   ", "metadata": {"sourceURL": _PROBE_URL}}, None),
        (None, {"unexpected": 1}),
    ],
    ids=["blank_source_url", "no_metadata", "wrapped_envelope", "blank_page_text", "map_no_links"],
)
async def test_t5_probe_rejects_a_non_v3_shape_and_leaves_no_task(scrape_body, map_body) -> None:
    before = _session_tasks()
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            scrape_handler=_static(scrape_body or _DEFAULT_SCRAPE_BODY),
            map_handler=_static(map_body or _DEFAULT_MAP_BODY),
        ),
    )
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_probe"
    await _settle()
    assert _session_tasks() == before


async def test_t6_probe_that_cannot_complete_is_a_connection_error_not_a_shape_error(
    no_wait,
) -> None:
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(scrape_handler=_rate_limited_after_probe())
    )
    with pytest.raises(McpConnectionError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_probe"
    assert not isinstance(exc.value, McpToolUnavailableError)
    assert no_wait == [30.0, 60.0]  # rate-limited probe retry uses the window-clearing backoff (M8)


# ===================================================================================== Search
async def test_t7_search_parses_the_documented_parallel_shape_and_echoes_the_request() -> None:
    body = {
        "results": [
            {"url": "https://a.test", "title": "A", "excerpts": ["first part", "second part"]},
            {"url": "https://b.test", "title": None, "excerpts": ["only part"]},
        ]
    }
    gateway = _gateway(_parallel_server(_static(body)), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("find hours", ["pool hours", "pool prices"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert result.objective == "find hours"
    assert result.search_queries == ("pool hours", "pool prices")
    assert result.retrieved_at
    assert [(e.url, e.title, e.text) for e in result.excerpts] == [
        ("https://a.test", "A", "first part\nsecond part"),
        ("https://b.test", None, "only part"),
    ]


async def test_t8_search_prefers_structured_content_over_the_text_block() -> None:
    async def handler(*_a):
        # Text and structured payloads deliberately disagree; the structured one must be read.
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps({"results": [{"url": "from-text", "excerpts": ["t"]}]}),
                )
            ],
            structured_content={"results": [{"url": "from-structured", "excerpts": ["s"]}]},
            is_error=False,
        )

    gateway = _gateway(_parallel_server(handler), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert [e.url for e in result.excerpts] == ["from-structured"]


async def test_t9_empty_search_hit_list_is_a_valid_result_not_a_failure() -> None:
    gateway = _gateway(_parallel_server(_static({"results": []})), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert result.excerpts == ()
    assert result.retrieved_at


@pytest.mark.parametrize(
    "body",
    [
        {"unrelated": 1},
        {"results": "not a list"},
        {"results": [5]},
        _text_result("plain prose, not JSON"),
    ],
    ids=["no_hit_list_key", "hits_not_a_list", "hit_not_an_object", "non_json_text"],
)
async def test_t10_unreadable_search_body_is_unparseable_not_an_empty_result(body) -> None:
    gateway = _gateway(_parallel_server(_static(body)), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "unparseable"
    assert result.tool == "web_search"


# ===================================================================================== Map
async def test_t11_map_returns_every_link_unfiltered_uncapped_and_in_order() -> None:
    links = [{"url": f"https://x.test/p{i}", "title": f"P{i}", "description": f"d{i}"} for i in range(60)]
    links.append({"url": "https://other-host.test/ad", "title": "off-host"})
    handler = _except_probe(_static({"links": links}), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site(_SITE)
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert result.url == _SITE
    assert result.retrieved_at
    # Candidate shaping (host filter, cap) belongs to the caller, so nothing is dropped here.
    assert [link.url for link in result.links] == [link["url"] for link in links]
    assert result.links[3].title == "P3"
    assert result.links[3].description == "d3"


async def test_t12_map_tolerates_plain_string_links() -> None:
    body = {"links": ["https://x.test/a", "https://x.test/b"]}
    handler = _except_probe(_static(body), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site(_SITE)
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert [(link.url, link.title) for link in result.links] == [
        ("https://x.test/a", None),
        ("https://x.test/b", None),
    ]


async def test_t13_empty_map_is_a_valid_result() -> None:
    handler = _except_probe(_static({"links": []}), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site(_SITE)
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert result.links == ()


async def test_t14_map_drops_malformed_entries_and_records_how_many(caplog) -> None:
    caplog.set_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME)
    body = {"links": [{"url": "https://x.test/ok"}, {"title": "no url"}, 5, "  "]}
    handler = _except_probe(_static(body), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site(_SITE)
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert [link.url for link in result.links] == ["https://x.test/ok"]
    skipped = _log_events(caplog, "mcp.map_links_skipped")
    assert len(skipped) == 1
    assert (skipped[0]["skipped"], skipped[0]["kept"]) == (3, 1)


@pytest.mark.parametrize(
    "body",
    [{"unexpected": 1}, {"links": "nope"}, {"links": [{"title": "no url"}, 5]}],
    ids=["no_links_key", "links_not_a_list", "no_usable_entry"],
)
async def test_t15_unreadable_map_body_is_unparseable(body) -> None:
    handler = _except_probe(_static(body), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site(_SITE)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_map", "unparseable")


# ===================================================================================== Scrape
async def test_t16_scrape_is_keyed_by_the_server_reported_source_url() -> None:
    body = {"markdown": "# hello", "metadata": {"sourceURL": "https://x.test/final"}}
    handler = _except_probe(_static(body), _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    result = await gateway.scrape_page("https://x.test/start")
    await gateway.aclose()
    assert isinstance(result, ScrapeResult)
    assert result.url == "https://x.test/final"  # sourceURL as the server reports it, unchanged
    assert result.text == "# hello"
    assert result.retrieved_at


async def test_t17_scrape_requests_markdown_of_the_main_content_only() -> None:
    seen: dict = {}

    async def scrape_handler(url, formats, only_main):
        if url != _PROBE_URL:
            seen.update(url=url, formats=formats, only_main=only_main)
        return {"markdown": "x", "metadata": {"sourceURL": url}}

    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=scrape_handler))
    await gateway.open()
    await gateway.scrape_page("https://x.test/page")
    await gateway.aclose()
    assert seen == {"url": "https://x.test/page", "formats": ["markdown"], "only_main": True}


async def test_t18_empty_markdown_with_a_source_url_is_a_valid_page() -> None:
    body = {"markdown": "", "metadata": {"sourceURL": "https://x.test/blank"}}
    handler = _except_probe(_static(body), _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    result = await gateway.scrape_page("https://x.test/blank")
    await gateway.aclose()
    assert isinstance(result, ScrapeResult)
    assert (result.url, result.text) == ("https://x.test/blank", "")


@pytest.mark.parametrize(
    "body",
    [
        {"markdown": "text", "metadata": {}},
        {"markdown": "text"},
        {"metadata": {"sourceURL": "https://x.test"}},
        {"success": True, "data": {"markdown": "t", "metadata": {"sourceURL": "https://x.test"}}},
        _text_result("raw markdown, not JSON"),
    ],
    ids=["blank_source_url", "no_metadata", "no_markdown", "wrapped_envelope", "non_json_text"],
)
async def test_t19_scrape_without_text_or_source_url_is_unparseable(body) -> None:
    handler = _except_probe(_static(body), _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    result = await gateway.scrape_page(_SITE)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_scrape", "unparseable")


# ===================================================================================== Failures
async def test_t20_tool_error_is_returned_not_raised_and_not_retried(no_wait) -> None:
    calls = {"n": 0}

    async def broken(*_a):
        calls["n"] += 1
        raise ToolError("the tool is broken")

    gateway = _gateway(_parallel_server(broken), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("web_search", "tool_error")
    assert "broken" in result.message  # the server's reason is carried for the caller
    assert calls["n"] == 1
    assert no_wait == []


@pytest.mark.parametrize("op", ["search", "map", "scrape"])
async def test_t21_rate_limit_retries_twice_with_backoffs_then_fails(op, no_wait) -> None:
    calls = {"n": 0}
    handler = _rate_limited_after_probe(calls)
    parallel = _parallel_server(handler if op == "search" else None)
    firecrawl = _firecrawl_server(
        map_handler=_except_probe(handler, _DEFAULT_MAP_BODY) if op == "map" else None,
        scrape_handler=_except_probe(handler, _DEFAULT_SCRAPE_BODY) if op == "scrape" else None,
    )
    gateway = _gateway(parallel, firecrawl)
    await gateway.open()
    result = await {
        "search": lambda: gateway.search_web("o", ["q"]),
        "map": lambda: gateway.map_site(_SITE),
        "scrape": lambda: gateway.scrape_page(_SITE),
    }[op]()
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "rate_limited"
    assert calls["n"] == 3  # one attempt plus two retries
    assert no_wait == [30.0, 60.0]


async def test_t22_a_transient_failure_that_clears_returns_the_typed_result(no_wait) -> None:
    calls = {"n": 0}

    async def flaky(*_a):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ToolError("rate limit exceeded")
        return _DEFAULT_SEARCH_BODY

    gateway = _gateway(_parallel_server(flaky), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert result.excerpts[0].url == "http://a"
    assert calls["n"] == 2
    assert no_wait == [30.0]


async def test_t23_transport_errors_are_retried_and_recover(no_wait) -> None:
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(),
        flaky={"parallel": [ConnectionError("reset"), httpx2.ConnectError("refused")]},
    )
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert no_wait == [2.0, 3.0]


async def test_t24_persistent_transport_error_returns_a_transport_failure(no_wait) -> None:
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(),
        flaky={"parallel": [ConnectionError("down")] * 3},
    )
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("web_search", "transport")
    assert no_wait == [2.0, 3.0]


@pytest.mark.parametrize("op", ["search", "map", "scrape"])
async def test_t25_timeout_is_retried_then_reported_and_the_session_is_reused(
    op, no_wait, monkeypatch
) -> None:
    events: list = []
    calls = {"n": 0}
    monkeypatch.setattr(mcp_tools, "MAP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(mcp_tools, "SCRAPE_TIMEOUT_SECONDS", 0.05)

    async def search_handler(objective, _queries):
        if objective == "slow":
            calls["n"] += 1
            await asyncio.sleep(0.4)
        return _DEFAULT_SEARCH_BODY

    async def map_handler(url):
        if url.endswith("/slow"):
            calls["n"] += 1
            await asyncio.sleep(0.4)
        return _DEFAULT_MAP_BODY

    async def scrape_handler(url, _formats, _only_main):
        if url.endswith("/slow"):
            calls["n"] += 1
            await asyncio.sleep(0.4)
        return {"markdown": "ok", "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(search_handler),
        _firecrawl_server(map_handler=map_handler, scrape_handler=scrape_handler),
        parallel_timeout=0.05,
        events=events,
    )
    await gateway.open()
    slow, fast = {
        "search": (lambda: gateway.search_web("slow", ["q"]), lambda: gateway.search_web("fast", ["q"])),
        "map": (lambda: gateway.map_site(f"{_SITE}/slow"), lambda: gateway.map_site(f"{_SITE}/fast")),
        "scrape": (
            lambda: gateway.scrape_page(f"{_SITE}/slow"),
            lambda: gateway.scrape_page(f"{_SITE}/fast"),
        ),
    }[op]
    timed_out = await slow()
    follow_up = await fast()
    await gateway.aclose()
    assert isinstance(timed_out, ToolFailure)
    assert timed_out.kind == "timeout"
    assert calls["n"] == 3
    assert no_wait == [2.0, 3.0]
    assert not isinstance(follow_up, ToolFailure)
    # A timeout is our side giving up on one wait: no client was rebuilt for either server.
    assert events.count(("open", "parallel")) == 1
    assert events.count(("open", "firecrawl")) == 1


async def test_t26_every_failed_attempt_is_logged_with_its_index_and_page(caplog, no_wait) -> None:
    caplog.set_level(logging.DEBUG, logger=DEEP_SEARCH_LOGGER_NAME)
    handler = _except_probe(_rate_limited_after_probe(), _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    await gateway.scrape_page("https://x.test/page")
    await gateway.aclose()
    attempts = _log_events(caplog, "mcp.call_attempt_failed")
    assert [(a["tool"], a["attempt"], a["kind"]) for a in attempts] == [
        ("firecrawl_scrape", 0, "rate_limited"),
        ("firecrawl_scrape", 1, "rate_limited"),
        ("firecrawl_scrape", 2, "rate_limited"),
    ]
    assert {a["target"] for a in attempts} == {"https://x.test/page"}


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (ConnectionError("reset"), "transport"),
        (OSError("socket closed"), "transport"),
        (httpx2.ConnectError("refused"), "transport"),
        (asyncio.TimeoutError(), "timeout"),
        (type("Http429", (Exception,), {"status_code": 429})("limited"), "rate_limited"),
        (Exception("Too Many Requests"), "rate_limited"),
        (ValueError("bad argument"), "tool_error"),
    ],
    ids=["connection", "oserror", "httpx", "timeout", "status_429", "429_text", "other"],
)
def test_t27_classifier_maps_exception_types_to_failure_kinds(error, kind) -> None:
    # Direct unit test of a private helper: these classes cannot be produced by an in-process
    # server, yet a wrong kind decides whether a recoverable call is retried.
    assert _classify_failure(error) == kind


# ===================================================================================== Validation
async def test_t28_invalid_arguments_raise_value_error_before_any_tool_call() -> None:
    calls: list[str] = []

    def record(tool, body):
        async def handler(*_a):
            calls.append(tool)
            return body

        return handler

    gateway = _gateway(
        _parallel_server(record("web_search", _DEFAULT_SEARCH_BODY)),
        _firecrawl_server(
            map_handler=record("firecrawl_map", _DEFAULT_MAP_BODY),
            scrape_handler=record("firecrawl_scrape", _DEFAULT_SCRAPE_BODY),
            crawl_handler=record("firecrawl_crawl", {"id": "j"}),
        ),
    )
    await gateway.open()
    baseline = list(calls)  # the probe's own calls
    invalid = [
        lambda: gateway.search_web("   ", ["q"]),
        lambda: gateway.search_web("o", []),
        lambda: gateway.search_web("o", ["  "]),
        lambda: gateway.map_site("x.test"),
        lambda: gateway.map_site("ftp://x.test"),
        lambda: gateway.scrape_page(""),
        lambda: gateway.scrape_page("ftp://x.test"),
        lambda: gateway.crawl_site(_SITE, limit=0, depth=1),
        lambda: gateway.crawl_site(_SITE, limit=1, depth=-1),
        lambda: gateway.crawl_site("ftp://x.test", limit=1, depth=1),
    ]
    try:
        for call in invalid:
            with pytest.raises(ValueError):
                await call()
    finally:
        await gateway.aclose()
    assert calls == baseline  # no rejected call reached a server


async def test_t29_call_before_open_raises_connection_error() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    for call in (
        lambda: gateway.search_web("o", ["q"]),
        lambda: gateway.map_site(_SITE),
        lambda: gateway.scrape_page(_SITE),
    ):
        with pytest.raises(McpConnectionError):
            await call()


# ===================================================================================== Crawl
async def test_t30_crawl_sends_app_controlled_arguments() -> None:
    seen: dict = {}

    async def crawl_handler(url, limit, depth, allow_external):
        seen.update(url=url, limit=limit, depth=depth, allow_external=allow_external)
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(_parallel_server(), _firecrawl_server(crawl_handler=crawl_handler))
    await gateway.open()
    await gateway.crawl_site(_SITE, limit=5, depth=2)
    await gateway.aclose()
    assert seen == {"url": _SITE, "limit": 5, "depth": 2, "allow_external": False}


async def test_t31_crawl_accepts_inline_pages_without_polling() -> None:
    status_calls = {"n": 0}

    async def status_handler(_id):
        status_calls["n"] += 1
        return _DEFAULT_CRAWL_PAGES

    # The start body carries a job id AND completed pages: the pages must win, so no poll happens.
    start_body = {**_DEFAULT_CRAWL_PAGES, "id": "job-inline"}
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=_static(start_body), status_handler=status_handler),
    )
    await gateway.open()
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, CrawlResult)
    assert result.job_id == "job-inline"
    assert [(p.url, p.title, p.text) for p in result.pages] == [("http://p/1", "P1", "page one")]
    assert result.retrieved_at
    assert status_calls["n"] == 0


async def test_t32_crawl_polls_a_job_id_to_completion(no_wait) -> None:
    ids: list[str] = []

    async def status_handler(job_id):
        ids.append(job_id)
        if len(ids) < 3:
            return {"status": "scraping"}
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=_static({"id": "job-9"}), status_handler=status_handler),
    )
    await gateway.open()
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, CrawlResult)
    assert result.job_id == "job-9"
    assert result.pages[0].text == "page one"
    assert ids == ["job-9"] * 3
    assert no_wait == [mcp_tools.CRAWL_POLL_INTERVAL_SECONDS] * 2


async def test_t33_timed_out_crawl_start_is_never_reissued(no_wait) -> None:
    crawl_calls = {"n": 0}

    async def crawl_handler(*_a):
        crawl_calls["n"] += 1
        await asyncio.sleep(0.4)  # outlives the per-call timeout
        return {"id": "job-1"}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=crawl_handler),
        firecrawl_timeout=0.05,
    )
    await gateway.open()
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_crawl", "timeout")
    assert crawl_calls["n"] == 1  # a second start could create and bill a second job
    assert no_wait == []


async def test_t34_timed_out_status_read_is_asked_again_with_the_same_id(no_wait) -> None:
    crawl_calls = {"n": 0}
    status_ids: list[str] = []

    async def crawl_handler(*_a):
        crawl_calls["n"] += 1
        return {"id": "job-t"}

    async def status_handler(job_id):
        status_ids.append(job_id)
        if len(status_ids) == 1:
            await asyncio.sleep(0.4)  # first read outlives the per-call timeout
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=crawl_handler, status_handler=status_handler),
        firecrawl_timeout=0.05,
    )
    await gateway.open()
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, CrawlResult)
    assert crawl_calls["n"] == 1
    assert status_ids == ["job-t", "job-t"]


async def test_t35_crawl_deadline_returns_a_timeout_that_carries_the_job_id(
    short_wait, monkeypatch
) -> None:
    monkeypatch.setattr(mcp_tools, "CRAWL_DEADLINE_SECONDS", 0.2)
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            crawl_handler=_static({"id": "job-stuck"}),
            status_handler=_static({"status": "scraping"}),
        ),
    )
    await gateway.open()
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_check_crawl_status", "timeout")
    assert "job-stuck" in result.message  # the recovery handle is not lost


async def test_t36_unrecognised_status_fails_at_once_instead_of_polling_to_the_deadline(
    no_wait,
) -> None:
    status_calls = {"n": 0}

    async def status_handler(_id):
        status_calls["n"] += 1
        return {"status": "banana"}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=_static({"id": "j"}), status_handler=status_handler),
    )
    await gateway.open()
    result = await gateway.crawl_site(_SITE, limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_check_crawl_status", "unparseable")
    assert status_calls["n"] == 1


# ===================================================================================== Lifecycle
async def test_t37_aclose_is_idempotent_and_releases_every_session() -> None:
    before = _session_tasks()
    events: list = []
    gateway = _gateway(_parallel_server(), _firecrawl_server(), events=events)
    await gateway.open()
    assert len(_session_tasks() - before) == 2
    await gateway.aclose()
    await gateway.aclose()  # the second close is a no-op
    assert _session_tasks() == before
    assert events.count(("close", "parallel")) == 1
    assert events.count(("close", "firecrawl")) == 1


async def test_t38_a_session_can_be_closed_from_a_different_task_than_it_was_opened_in() -> None:
    before = _session_tasks()
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await asyncio.create_task(gateway.open())
    result = await gateway.search_web("o", ["q"])
    await asyncio.create_task(gateway.aclose())
    assert isinstance(result, WebSearchResult)
    assert _session_tasks() == before


async def test_t39_failed_connect_of_one_server_releases_the_other_and_raises() -> None:
    before = _session_tasks()
    events: list = []
    gateway = _gateway(
        _parallel_server(), ConnectionRefusedError("down"), events=events
    )
    with pytest.raises(McpConnectionError) as exc:
        await gateway.open()
    assert exc.value.stage == "open"
    await _settle()
    assert _session_tasks() == before
    assert ("close", "parallel") in events  # the session that did open was torn down


async def test_t40_cancelling_open_mid_connect_leaves_no_task() -> None:
    before = _session_tasks()
    events: list = []
    gateway = _gateway(_parallel_server(), _HANG, events=events)
    opening = asyncio.create_task(gateway.open())
    await asyncio.sleep(0.1)  # parallel is up; firecrawl is still connecting
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening
    await _settle()
    assert _session_tasks() == before
    assert ("close", "parallel") in events


# ===================================================================================== Concurrency
async def test_t41_concurrent_searches_stay_within_the_bound_and_keep_their_own_results() -> None:
    state = {"active": 0, "max": 0}

    async def tracking(objective, _queries):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        try:
            await asyncio.sleep(0.02)
            return {"results": [{"url": f"http://{objective}", "title": objective, "excerpts": [objective]}]}
        finally:
            state["active"] -= 1

    gateway = _gateway(_parallel_server(tracking), _firecrawl_server(), search_concurrency=4)
    await gateway.open()
    objectives = [f"obj-{i}" for i in range(10)]
    results = await asyncio.gather(*(gateway.search_web(o, ["q"]) for o in objectives))
    await gateway.aclose()
    assert 1 < state["max"] <= 4  # real overlap happened, and never past the bound
    assert [r.objective for r in results] == objectives
    assert [r.excerpts[0].text for r in results] == objectives  # no cross-talk on the shared client


async def test_t42_one_failed_call_does_not_abort_a_concurrent_gather() -> None:
    async def handler(objective, _queries):
        if objective == "bad":
            raise ToolError("the tool is broken")
        return _DEFAULT_SEARCH_BODY

    gateway = _gateway(_parallel_server(handler), _firecrawl_server())
    await gateway.open()
    results = await asyncio.gather(
        *(gateway.search_web(o, ["q"]) for o in ("a", "bad", "b", "c"))
    )
    await gateway.aclose()
    assert [type(r) for r in results] == [WebSearchResult, ToolFailure, WebSearchResult, WebSearchResult]


async def test_t43_map_scrape_and_crawl_share_one_firecrawl_pool() -> None:
    state = {"active": 0, "max": 0}

    async def tracked(body):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        try:
            await asyncio.sleep(0.02)
            return body
        finally:
            state["active"] -= 1

    async def map_handler(_url):
        return await tracked(_DEFAULT_MAP_BODY)

    async def scrape_handler(url, _formats, _only_main):
        return await tracked({"markdown": url, "metadata": {"sourceURL": url}})

    async def crawl_handler(*_a):
        return await tracked(_DEFAULT_CRAWL_PAGES)

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            map_handler=map_handler, scrape_handler=scrape_handler, crawl_handler=crawl_handler
        ),
        firecrawl_concurrency=2,
    )
    await gateway.open()
    urls = [f"{_SITE}/{i}" for i in range(5)]
    results = await asyncio.gather(
        gateway.map_site(_SITE),
        gateway.crawl_site(_SITE, limit=2, depth=1),
        *(gateway.scrape_page(u) for u in urls),
    )
    await gateway.aclose()
    assert state["max"] == 2  # real overlap, capped across all three operations together
    assert [r.url for r in results[2:]] == urls  # each scrape returned its own page


async def test_t44_a_saturated_firecrawl_pool_does_not_starve_search() -> None:
    release = asyncio.Event()

    async def scrape_handler(url, _formats, _only_main):
        if url != _PROBE_URL:
            await release.wait()
        return {"markdown": "x", "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(scrape_handler=scrape_handler),
        firecrawl_concurrency=1,
        firecrawl_timeout=30.0,
    )
    await gateway.open()
    scraping = asyncio.create_task(gateway.scrape_page(f"{_SITE}/slow"))
    await asyncio.sleep(0.1)  # the scrape now holds the only Firecrawl slot
    try:
        result = await asyncio.wait_for(gateway.search_web("o", ["q"]), timeout=2.0)
    finally:
        release.set()
        await scraping
        await gateway.aclose()
    assert isinstance(result, WebSearchResult)


async def test_t45_a_call_waiting_out_its_backoff_does_not_hold_the_pool_slot(
    monkeypatch,
) -> None:
    sleeping = asyncio.Event()
    gate = asyncio.Event()

    async def gated_sleep(_seconds: float) -> None:
        sleeping.set()
        await gate.wait()

    monkeypatch.setattr(mcp_tools, "_async_sleep", gated_sleep)

    async def scrape_handler(url, _formats, _only_main):
        if url.endswith("/limited"):
            raise ToolError("rate limit exceeded")
        return {"markdown": "x", "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(scrape_handler=_except_probe(scrape_handler, _DEFAULT_SCRAPE_BODY)),
        firecrawl_concurrency=1,
    )
    await gateway.open()
    limited = asyncio.create_task(gateway.scrape_page(f"{_SITE}/limited"))
    await asyncio.wait_for(sleeping.wait(), timeout=2.0)  # it is now in its 2 s backoff
    try:
        other = await asyncio.wait_for(gateway.scrape_page(f"{_SITE}/other"), timeout=2.0)
    finally:
        gate.set()
        await limited
        await gateway.aclose()
    assert isinstance(other, ScrapeResult)


@pytest.mark.parametrize("op", ["search", "scrape"])
async def test_t46_cancelling_an_in_flight_call_frees_its_slot_and_keeps_the_session(op) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def search_handler(objective, _queries):
        if objective == "cancel-me":
            entered.set()
            await release.wait()
        return _DEFAULT_SEARCH_BODY

    async def scrape_handler(url, _formats, _only_main):
        if url.endswith("/cancel-me"):
            entered.set()
            await release.wait()
        return {"markdown": "ok", "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(search_handler),
        _firecrawl_server(scrape_handler=scrape_handler),
        search_concurrency=1,
        firecrawl_concurrency=1,
        parallel_timeout=30.0,
        firecrawl_timeout=30.0,
    )
    await gateway.open()
    if op == "search":
        start = lambda: gateway.search_web("cancel-me", ["q"])  # noqa: E731
        follow = lambda: gateway.search_web("after", ["q"])  # noqa: E731
    else:
        start = lambda: gateway.scrape_page(f"{_SITE}/cancel-me")  # noqa: E731
        follow = lambda: gateway.scrape_page(f"{_SITE}/after")  # noqa: E731
    cancelled = asyncio.create_task(start())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    try:
        # Pool size is 1, so this only completes if the cancelled call released its slot.
        result = await asyncio.wait_for(follow(), timeout=2.0)
    finally:
        release.set()
        await gateway.aclose()
    assert not isinstance(result, ToolFailure)


# ===================================================================================== Secrets
async def test_t47_keys_never_reach_logs_or_failure_messages(caplog, no_wait) -> None:
    secret = "SECRET-KEY-DO-NOT-LEAK-123"
    caplog.set_level(logging.DEBUG, logger=DEEP_SEARCH_LOGGER_NAME)
    handler = _rate_limited_after_probe()
    gateway = _gateway(
        _parallel_server(handler),
        _firecrawl_server(
            map_handler=_except_probe(handler, _DEFAULT_MAP_BODY),
            scrape_handler=_except_probe(handler, _DEFAULT_SCRAPE_BODY),
        ),
        api_key=secret,
    )
    await gateway.open()
    failures = [
        await gateway.search_web("o", ["q"]),
        await gateway.map_site(_SITE),
        await gateway.scrape_page(_SITE),
    ]
    await gateway.aclose()
    assert all(isinstance(f, ToolFailure) for f in failures)
    assert all(secret not in f.message for f in failures)
    assert _log_events(caplog, "mcp.call_attempt_failed")  # there were records to leak into
    assert secret not in caplog.text


# ===================================================================================== Real HTTP
def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _HeaderCapture:
    """ASGI wrapper recording the Authorization header of every HTTP request a server receives."""

    def __init__(self, app, sink: list) -> None:
        self._app = app
        self._sink = sink

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            self._sink.append(dict(scope["headers"]).get(b"authorization"))
        await self._app(scope, receive, send)


@pytest.fixture
def http_servers():
    """Run both fake vendors on loopback HTTP so the production client factory is exercised."""
    seen: dict[str, list] = {"parallel": [], "firecrawl": []}
    running: list[tuple[uvicorn.Server, threading.Thread]] = []
    urls: dict[str, str] = {}
    for name, server in (("parallel", _parallel_server()), ("firecrawl", _firecrawl_server())):
        port = _free_port()
        app = _HeaderCapture(server.streamable_http_app(), seen[name])
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        uv = uvicorn.Server(config)
        thread = threading.Thread(target=uv.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not uv.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert uv.started, f"{name} test server did not start"
        running.append((uv, thread))
        urls[name] = f"http://127.0.0.1:{port}/mcp"
    yield urls, seen
    for uv, thread in running:
        uv.should_exit = True
        thread.join(timeout=10)


def _settings(urls: dict, *, parallel_key, firecrawl_key) -> Settings:
    return Settings.model_construct(
        parallel_api_key=parallel_key,
        firecrawl_api_key=firecrawl_key,
        parallel_mcp_url=urls["parallel"],
        firecrawl_mcp_url=urls["firecrawl"],
        firecrawl_probe_url=_PROBE_URL,
    )


async def test_t48_composition_root_gateway_serves_typed_results_over_real_http(
    http_servers,
) -> None:
    urls, _seen = http_servers
    gateway = create_mcp_tool_gateway(_settings(urls, parallel_key=None, firecrawl_key="fc-key"))
    await gateway.open()
    try:
        searched = await gateway.search_web("o", ["q"])
        mapped = await gateway.map_site(_SITE)
        scraped = await gateway.scrape_page(f"{_SITE}/page")
    finally:
        await gateway.aclose()
    assert isinstance(searched, WebSearchResult) and searched.excerpts[0].url == "http://a"
    assert isinstance(mapped, MapResult) and mapped.links[0].url == "https://example.com/a"
    assert isinstance(scraped, ScrapeResult) and scraped.text == "page text"


async def test_t49_bearer_header_is_sent_only_when_a_key_is_configured(http_servers) -> None:
    urls, seen = http_servers
    # A blank/whitespace key is the same as no key: no header, never "Bearer ".
    gateway = create_mcp_tool_gateway(_settings(urls, parallel_key="   ", firecrawl_key="fc-key"))
    await gateway.open()
    try:
        await gateway.search_web("o", ["q"])
        await gateway.scrape_page(f"{_SITE}/page")
    finally:
        await gateway.aclose()
    assert seen["parallel"] and all(h is None for h in seen["parallel"])
    assert seen["firecrawl"] and all(h == b"Bearer fc-key" for h in seen["firecrawl"])


# ============================================================ Iteration 3: classifier (M6, M7)
async def test_t50_mcp_error_sse_disconnect_is_transport_and_retried(no_wait) -> None:
    disconnect = MCPError(-32000, "SSE stream ended and reconnection attempts were exhausted")
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(),
        flaky={"parallel": [disconnect, disconnect]},  # two disconnects, then the real body
    )
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)  # retried on the same session and recovered
    assert no_wait == [2.0, 3.0]  # transport backoff, not the rate-limit one


async def test_t51_persistent_sse_disconnect_returns_transport_failure(no_wait) -> None:
    disconnect = MCPError(-32000, "SSE stream ended and reconnection attempts were exhausted")
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(), flaky={"parallel": [disconnect] * 3}
    )
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("web_search", "transport")
    assert no_wait == [2.0, 3.0]


async def test_t52_a_429_wrapped_in_mcperror_is_rate_limited(no_wait) -> None:
    throttled = MCPError(-32000, "upstream returned 429 Too Many Requests")
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(), flaky={"parallel": [throttled] * 3}
    )
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "rate_limited"  # 429 wins over the generic MCPError->transport branch
    assert no_wait == [30.0, 60.0]  # window-clearing backoff


def test_t53_classifier_maps_mcp_error_and_wrapped_429() -> None:
    sse = MCPError(-32000, "SSE stream ended and reconnection attempts were exhausted")
    assert _classify_failure(sse) == "transport"
    assert _classify_failure(MCPError(-32000, "boom: 429")) == "rate_limited"
    # An MCPError that is neither a disconnect nor a 429 stays a tool error (de-mask on the message).
    assert _classify_failure(MCPError(-32000, "tool blew up")) == "tool_error"


# ============================================================ Iteration 3: batch scrape (A4)
async def test_t54_batch_scrape_polls_a_job_to_completion_keyed_by_source_url() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    result = await gateway.batch_scrape([f"{_SITE}/1", f"{_SITE}/2"])
    await gateway.aclose()
    assert isinstance(result, BatchScrapeResult)
    assert [(p.url, p.text) for p in result.pages] == [
        ("https://x.test/1", "page one"),
        ("https://x.test/2", "page two"),
    ]
    assert (result.total, result.completed, result.failed_urls) == (2, 2, ())
    assert result.retrieved_at


async def test_t55_batch_scrape_follows_the_next_cursor(no_wait) -> None:
    async def batch_status_handler(_id, skip):
        if not skip:
            return {
                "status": "completed", "total": 2, "completed": 1, "next": 1,
                "data": [{"markdown": "one", "metadata": {"sourceURL": "https://x.test/1"}}],
            }
        return {
            "status": "completed", "total": 2, "completed": 2,
            "data": [{"markdown": "two", "metadata": {"sourceURL": "https://x.test/2"}}],
        }

    gateway = _gateway(
        _parallel_server(), _firecrawl_server(batch_status_handler=batch_status_handler)
    )
    await gateway.open()
    result = await gateway.batch_scrape([f"{_SITE}/1", f"{_SITE}/2"])
    await gateway.aclose()
    assert isinstance(result, BatchScrapeResult)
    assert [p.url for p in result.pages] == ["https://x.test/1", "https://x.test/2"]


async def test_t56_batch_partial_failure_rides_failed_urls_and_logs(caplog) -> None:
    caplog.set_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME)
    body = {
        "status": "completed", "total": 2, "completed": 1,
        "data": [
            {"markdown": "ok", "metadata": {"sourceURL": "https://x.test/1"}},
            {"url": "https://x.test/2", "metadata": {}},  # no sourceURL -> a per-URL failure
        ],
    }
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(batch_status_handler=_static(body))
    )
    await gateway.open()
    result = await gateway.batch_scrape([f"{_SITE}/1", f"{_SITE}/2"])
    await gateway.aclose()
    assert isinstance(result, BatchScrapeResult)
    assert [p.url for p in result.pages] == ["https://x.test/1"]
    assert result.failed_urls == ("https://x.test/2",)
    failed = _log_events(caplog, "mcp.batch_pages_failed")
    assert len(failed) == 1 and failed[0]["failed"] == 1


async def test_t57_unreadable_batch_status_is_unparseable() -> None:
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(batch_status_handler=_static({"status": "banana"})),
    )
    await gateway.open()
    result = await gateway.batch_scrape([f"{_SITE}/1"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_check_batch_scrape_status", "unparseable")


async def test_t58_batch_deadline_returns_timeout_carrying_the_job_id(short_wait, monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "BATCH_DEADLINE_SECONDS", 0.2)
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            batch_handler=_static({"id": "batch-stuck"}),
            batch_status_handler=_static({"status": "scraping"}),
        ),
    )
    await gateway.open()
    result = await gateway.batch_scrape([f"{_SITE}/1"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_check_batch_scrape_status", "timeout")
    assert "batch-stuck" in result.message


async def test_t59_bad_batch_input_raises_value_error() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    try:
        with pytest.raises(ValueError):
            await gateway.batch_scrape([])
        with pytest.raises(ValueError):
            await gateway.batch_scrape([f"{_SITE}/ok", "ftp://x.test"])
    finally:
        await gateway.aclose()


async def test_t60_missing_batch_tool_fails_per_call_not_at_connect(no_wait) -> None:
    # Batch is not capability-checked (user decision): open() still succeeds, and the gap shows
    # only when batch_scrape is actually called, like the retained crawl path.
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_batch=False))
    await gateway.open()
    result = await gateway.batch_scrape([f"{_SITE}/1"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.tool == "firecrawl_batch_scrape"


# ============================================================ Iteration 3: slow stream (M5), real HTTP
async def test_t61_a_slow_stream_is_not_severed_by_the_read_timeout() -> None:
    # Over real loopback HTTP: a scrape whose body streams for ~6 s (longer than httpx's old 5 s
    # read default) must still complete, proving the factory sets read=None (M5). The probe URL is
    # answered fast so open() is quick; only the page under test is slow.
    async def slow_scrape(url, _formats, _only_main):
        if url != _PROBE_URL:
            await asyncio.sleep(6.0)
        return {"markdown": "late body", "metadata": {"sourceURL": url}}

    servers = {
        "parallel": _parallel_server(),
        "firecrawl": _firecrawl_server(scrape_handler=slow_scrape),
    }
    running: list[tuple[uvicorn.Server, threading.Thread]] = []
    urls: dict[str, str] = {}
    for name, server in servers.items():
        port = _free_port()
        uv = uvicorn.Server(uvicorn.Config(server.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=uv.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not uv.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert uv.started, f"{name} did not start"
        running.append((uv, thread))
        urls[name] = f"http://127.0.0.1:{port}/mcp"
    try:
        gateway = create_mcp_tool_gateway(
            _settings(urls, parallel_key=None, firecrawl_key="fc-key")
        )
        await gateway.open()
        try:
            scraped = await gateway.scrape_page(f"{_SITE}/slow")
        finally:
            await gateway.aclose()
        assert isinstance(scraped, ScrapeResult)  # not a ToolFailure(timeout/transport)
        assert scraped.text == "late body"
    finally:
        for uv, thread in running:
            uv.should_exit = True
            thread.join(timeout=10)
