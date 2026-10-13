"""Offline fixtures for R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

No network and no keys: each test wires an in-process `MCPServer` into the gateway through the
client factory seam, so the real gateway code paths (owner tasks, capability check, shape probe,
retry, timeout, parsing, concurrency, close) run against a fake server on the event loop.

Because `open()` probes Firecrawl once (one map and one scrape of the probe URL), every Firecrawl
fixture serves MCP server 3.x JSON-shaped map and scrape bodies by default. A handler that fails on purpose is
wrapped with `_except_probe` so the probe still passes and only the page under test fails.
"""

import asyncio
import json
import logging
import socket
import threading
import time

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

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
    _parse_map_result,
    _parse_scrape_result,
    create_mcp_tool_gateway,
)
from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError


# ------------------------------------------------------------------------------------- handlers
def _static(value):
    async def handler(*_args, **_kwargs):
        return value

    return handler


_PROBE_URL = "https://example.com"
_DEFAULT_SEARCH_BODY = {"results": [{"url": "http://a", "title": "A", "text": "body"}]}
_DEFAULT_CRAWL_PAGES = {
    "status": "completed",
    "data": [{"url": "http://p/1", "title": "P1", "markdown": "page one"}],
}
_DEFAULT_MAP_BODY = {
    "links": [{"url": "https://example.com/a", "title": "A", "description": "page a"}]
}
_DEFAULT_SCRAPE_BODY = {"markdown": "page text", "metadata": {"sourceURL": _PROBE_URL}}
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


def _except_probe(handler, default):
    """Answer the connect-time probe URL with `default`; send every other URL to `handler`."""

    async def wrapped(url, *rest):
        if url == _PROBE_URL:
            return default
        return await handler(url, *rest)

    return wrapped


# ------------------------------------------------------------------------------------- servers
def _parallel_server(handler=None, *, include_queries_arg: bool = True) -> MCPServer:
    server = MCPServer(name="parallel-srv")
    handler = handler or _static(_DEFAULT_SEARCH_BODY)
    if include_queries_arg:

        @server.tool()
        async def web_search(objective: str, search_queries: list[str]) -> dict:  # noqa: D401
            return await handler(objective, search_queries)

    else:

        @server.tool()
        async def web_search(objective: str) -> dict:  # noqa: D401, F811
            return await handler(objective)

    return server


def _firecrawl_server(
    crawl_handler=None,
    status_handler=None,
    *,
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
        ) -> dict:
            return await batch_handler(urls, formats, onlyMainContent, maxConcurrency)

        @server.tool()
        async def firecrawl_check_batch_scrape_status(id: str, skip: int = 0) -> dict:  # noqa: A002
            return await batch_status_handler(id, skip)

    if include_crawl:

        @server.tool()
        async def firecrawl_crawl(
            url: str, limit: int, maxDiscoveryDepth: int, allowExternalLinks: bool  # noqa: N803
        ) -> dict:
            return await crawl_handler(url, limit, maxDiscoveryDepth, allowExternalLinks)

    if include_status:

        @server.tool()
        async def firecrawl_check_crawl_status(id: str) -> dict:  # noqa: A002
            return await status_handler(id)

    if include_map:

        @server.tool()
        async def firecrawl_map(url: str) -> dict:
            return await map_handler(url)

    if include_scrape:
        if include_formats_arg:

            @server.tool()
            async def firecrawl_scrape(
                url: str, formats: list[str], onlyMainContent: bool = True  # noqa: N803
            ) -> dict:
                return await scrape_handler(url, formats, onlyMainContent)

        else:

            @server.tool()
            async def firecrawl_scrape(url: str) -> dict:  # noqa: F811
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


def _factory(targets: dict, counter: list | None = None, flaky: dict | None = None):
    """Build a client factory mapping config.name → an MCPServer, or an Exception to raise on open."""
    from contextlib import asynccontextmanager

    def factory(config: McpServerConfig):
        @asynccontextmanager
        async def cm():
            if counter is not None:
                counter.append(config.name)
            target = targets[config.name]
            if isinstance(target, BaseException):
                raise target
            async with Client(target) as client:
                if flaky and config.name in flaky:
                    yield _FlakyClient(client, flaky[config.name])
                else:
                    yield client

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
    factory_counter: list | None = None,
    flaky: dict | None = None,
) -> McpToolGateway:
    parallel = McpServerConfig("parallel", "http://parallel", api_key, parallel_timeout)
    firecrawl = McpServerConfig("firecrawl", "http://firecrawl", api_key, firecrawl_timeout)
    factory = _factory(
        {"parallel": parallel_target, "firecrawl": firecrawl_target}, factory_counter, flaky
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


# ===================================================================================== Capabilities
async def test_full_capability_set_passes() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    await gateway.aclose()


async def test_missing_map_tool_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_map=False))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_scrape_tool_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_scrape=False))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_scrape_formats_argument_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_formats_arg=False))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_parallel_argument_raises() -> None:
    gateway = _gateway(_parallel_server(include_queries_arg=False), _firecrawl_server())
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_server_without_crawl_and_status_tools_passes_connect() -> None:
    # Crawl and status are retained for crawl_site but are not part of the connect requirement.
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(include_crawl=False, include_status=False)
    )
    await gateway.open()
    await gateway.aclose()


async def test_crawl_without_crawl_tool_fails_per_call_not_at_connect(no_wait) -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_crawl=False))
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, ToolFailure)


# ===================================================================================== Probe
async def test_open_probes_firecrawl_once_after_the_capability_check() -> None:
    events: list[str] = []

    async def map_handler(url):
        events.append(f"map:{url}")
        return _DEFAULT_MAP_BODY

    async def scrape_handler(url, _formats, _only_main):
        events.append(f"scrape:{url}")
        return _DEFAULT_SCRAPE_BODY

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(map_handler=map_handler, scrape_handler=scrape_handler),
    )
    original = gateway.verify_capabilities

    async def traced() -> None:
        events.append("capabilities")
        await original()

    gateway.verify_capabilities = traced
    await gateway.open()
    await gateway.aclose()
    assert events[0] == "capabilities"
    assert sorted(events[1:]) == sorted([f"map:{_PROBE_URL}", f"scrape:{_PROBE_URL}"])


async def test_probe_uses_the_configured_url() -> None:
    seen: list[str] = []

    async def map_handler(url):
        seen.append(url)
        return _DEFAULT_MAP_BODY

    async def scrape_handler(url, _formats, _only_main):
        seen.append(url)
        return {"markdown": "text", "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(map_handler=map_handler, scrape_handler=scrape_handler),
        probe_url="https://probe.test",
    )
    await gateway.open()
    await gateway.aclose()
    assert seen == ["https://probe.test", "https://probe.test"]


async def test_probe_pass_is_logged(caplog) -> None:
    caplog.set_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME)
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    await gateway.aclose()
    assert "mcp.probe_passed" in caplog.text


@pytest.mark.parametrize(
    "scrape_body",
    [
        {"markdown": "text", "metadata": {}},
        {"markdown": "text"},
        {"success": True, "data": {"markdown": "text", "metadata": {"sourceURL": _PROBE_URL}}},
    ],
    ids=["blank_source_url", "no_metadata", "wrapped_data_envelope"],
)
async def test_probe_wrong_scrape_shape_raises_and_leaves_no_task(scrape_body) -> None:
    before = _session_tasks()
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(scrape_handler=_static(scrape_body))
    )
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_probe"
    await asyncio.sleep(0)
    assert _session_tasks() == before


async def test_probe_empty_page_text_raises() -> None:
    body = {"markdown": "", "metadata": {"sourceURL": _PROBE_URL}}
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=_static(body)))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_probe"


async def test_probe_map_without_links_list_raises() -> None:
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(map_handler=_static({"unexpected": 1}))
    )
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_probe"


async def test_probe_transient_failure_raises_connection_error(no_wait) -> None:
    async def rate_limited(*_a):
        raise ToolError("rate limit exceeded")

    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=rate_limited))
    with pytest.raises(McpConnectionError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_probe"
    assert no_wait == [30.0, 60.0]


# ===================================================================================== Typed results
async def test_search_result_is_typed_with_timestamp() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("find bakeries", ["bakery near me"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert result.objective == "find bakeries"
    assert result.search_queries == ("bakery near me",)
    assert result.retrieved_at
    assert result.excerpts[0].url == "http://a"
    assert result.excerpts[0].text == "body"


async def test_is_error_returns_tool_failure_not_raised() -> None:
    async def boom(*_a):
        raise ToolError("the tool is broken")

    gateway = _gateway(_parallel_server(boom), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "tool_error"


async def test_empty_search_body_gives_zero_excerpts() -> None:
    gateway = _gateway(_parallel_server(_static({"results": []})), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)
    assert result.excerpts == ()


# ===================================================================================== Map
async def test_map_returns_typed_links() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert result.url == "https://x.test"
    assert result.retrieved_at
    assert result.links[0].url == "https://example.com/a"
    assert result.links[0].title == "A"
    assert result.links[0].description == "page a"


async def test_map_accepts_plain_string_links() -> None:
    body = {"links": ["https://x.test/a", "https://x.test/b"]}
    handler = _except_probe(_static(body), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert [link.url for link in result.links] == ["https://x.test/a", "https://x.test/b"]
    assert all(link.title is None for link in result.links)


async def test_map_empty_links_is_a_valid_result() -> None:
    handler = _except_probe(_static({"links": []}), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert result.links == ()


async def test_map_without_links_list_is_unparseable() -> None:
    handler = _except_probe(_static({"unexpected": 1}), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "unparseable"
    assert result.tool == "firecrawl_map"


async def test_map_skips_malformed_entries_and_logs_the_count(caplog) -> None:
    caplog.set_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME)
    body = {"links": [{"url": "https://x.test/ok"}, {"title": "no url"}, 5]}
    handler = _except_probe(_static(body), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, MapResult)
    assert [link.url for link in result.links] == ["https://x.test/ok"]
    assert "mcp.map_links_skipped" in caplog.text


async def test_map_with_no_usable_entry_is_unparseable() -> None:
    body = {"links": [{"title": "no url"}, 5]}
    handler = _except_probe(_static(body), _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "unparseable"


async def test_map_is_error_returns_tool_failure_not_raised(no_wait) -> None:
    async def boom(_url):
        raise ToolError("the tool is broken")

    handler = _except_probe(boom, _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "tool_error"
    assert result.tool == "firecrawl_map"
    assert no_wait == []


async def test_map_retries_twice_on_rate_limit_then_fails(no_wait) -> None:
    calls = {"n": 0}

    async def rate_limited(_url):
        calls["n"] += 1
        raise ToolError("rate limit exceeded")

    handler = _except_probe(rate_limited, _DEFAULT_MAP_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(map_handler=handler))
    await gateway.open()
    result = await gateway.map_site("https://x.test")
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "rate_limited"
    assert calls["n"] == 3  # one attempt plus two retries
    assert no_wait == [30.0, 60.0]


async def test_bad_map_url_raises_value_error() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    try:
        for bad in ("", "ftp://x.test", "x.test"):
            with pytest.raises(ValueError):
                await gateway.map_site(bad)
    finally:
        await gateway.aclose()


# ===================================================================================== Scrape
async def test_scrape_returns_page_keyed_by_the_reported_source_url() -> None:
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


async def test_scrape_empty_markdown_with_source_url_is_a_valid_result() -> None:
    body = {"markdown": "", "metadata": {"sourceURL": "https://x.test/blank"}}
    handler = _except_probe(_static(body), _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    result = await gateway.scrape_page("https://x.test/blank")
    await gateway.aclose()
    assert isinstance(result, ScrapeResult)
    assert result.text == ""


@pytest.mark.parametrize(
    "body",
    [
        {"markdown": "text", "metadata": {}},
        {"markdown": "text"},
        {"metadata": {"sourceURL": "https://x.test"}},
        {"success": True, "data": {"markdown": "text", "metadata": {"sourceURL": "https://x.test"}}},
    ],
    ids=["blank_source_url", "no_metadata", "no_markdown", "wrapped_data_envelope"],
)
async def test_scrape_unrecognised_shape_is_unparseable(body) -> None:
    handler = _except_probe(_static(body), _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    result = await gateway.scrape_page("https://x.test")
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "unparseable"
    assert result.tool == "firecrawl_scrape"


async def test_scrape_sends_markdown_format_and_main_content_only() -> None:
    seen: dict = {}

    async def scrape_handler(url, formats, only_main):
        if url != _PROBE_URL:
            seen.update(url=url, formats=formats, only_main=only_main)
        return _DEFAULT_SCRAPE_BODY

    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=scrape_handler))
    await gateway.open()
    await gateway.scrape_page("https://x.test/page")
    await gateway.aclose()
    assert seen == {"url": "https://x.test/page", "formats": ["markdown"], "only_main": True}


async def test_scrape_retries_twice_on_rate_limit_then_fails(no_wait) -> None:
    calls = {"n": 0}

    async def rate_limited(_url, *_rest):
        calls["n"] += 1
        raise ToolError("rate limit exceeded")

    handler = _except_probe(rate_limited, _DEFAULT_SCRAPE_BODY)
    gateway = _gateway(_parallel_server(), _firecrawl_server(scrape_handler=handler))
    await gateway.open()
    result = await gateway.scrape_page("https://x.test")
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "rate_limited"
    assert calls["n"] == 3
    assert no_wait == [30.0, 60.0]


async def test_bad_scrape_url_raises_value_error() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    try:
        for bad in ("", "ftp://x.test", "x.test"):
            with pytest.raises(ValueError):
                await gateway.scrape_page(bad)
    finally:
        await gateway.aclose()


async def test_timed_out_scrape_leaves_the_same_client_usable(no_wait, monkeypatch) -> None:
    counter: list[str] = []
    monkeypatch.setattr(mcp_tools, "SCRAPE_TIMEOUT_SECONDS", 0.05)

    async def scrape_handler(url, _formats, _only_main):
        if url == "https://x.test/slow":
            await asyncio.sleep(0.5)  # cut short by the per-call scrape timeout
        return {"markdown": url, "metadata": {"sourceURL": url}}

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(scrape_handler=scrape_handler),
        factory_counter=counter,
    )
    await gateway.open()
    timed_out = await gateway.scrape_page("https://x.test/slow")
    follow_up = await gateway.scrape_page("https://x.test/fast")
    await gateway.aclose()
    assert isinstance(timed_out, ToolFailure)
    assert timed_out.kind == "timeout"
    assert no_wait == [2.0, 3.0]
    assert isinstance(follow_up, ScrapeResult)
    assert follow_up.url == "https://x.test/fast"
    # One client per server at open; none rebuilt after the timeout.
    assert counter.count("firecrawl") == 1


# ===================================================================================== Decode
def test_parsers_prefer_structured_content_over_the_text_block() -> None:
    # The in-process server fills both fields, so preference is proven at the parser: the text block
    # carries different data, and the structured payload must be the one read.
    map_result = CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"links": ["https://text.test"]}))],
        structured_content={"links": ["https://structured.test"]},
        is_error=False,
    )
    scrape_result = CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps({"markdown": "from text", "metadata": {"sourceURL": "https://t"}}),
            )
        ],
        structured_content={"markdown": "from structured", "metadata": {"sourceURL": "https://s"}},
        is_error=False,
    )
    mapped = _parse_map_result(map_result, "https://x.test", "2026-01-01T00:00:00+00:00")
    scraped = _parse_scrape_result(scrape_result, "2026-01-01T00:00:00+00:00")
    assert mapped.links[0].url == "https://structured.test"
    assert scraped.text == "from structured"
    assert scraped.url == "https://s"


# ===================================================================================== Crawl shapes
async def test_crawl_returns_pages_on_start() -> None:
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(crawl_handler=_static(_DEFAULT_CRAWL_PAGES))
    )
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, CrawlResult)
    assert result.pages[0].url == "http://p/1"
    assert result.pages[0].text == "page one"
    assert result.retrieved_at


async def test_crawl_polls_job_to_completion(no_wait) -> None:
    status_calls = {"n": 0}

    async def status_handler(_id):
        status_calls["n"] += 1
        if status_calls["n"] == 1:
            return {"status": "scraping"}
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=_static({"id": "job-9"}), status_handler=status_handler),
    )
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, CrawlResult)
    assert result.job_id == "job-9"
    assert status_calls["n"] == 2
    assert result.pages[0].url == "http://p/1"


# ===================================================================================== Retry
async def test_search_retries_twice_then_fails(no_wait) -> None:
    calls = {"n": 0}

    async def rate_limited(*_a):
        calls["n"] += 1
        raise ToolError("rate limit exceeded")

    gateway = _gateway(_parallel_server(rate_limited), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "rate_limited"
    assert calls["n"] == 3  # one attempt plus two retries
    assert no_wait == [30.0, 60.0]


async def test_non_transient_error_makes_one_attempt(no_wait) -> None:
    calls = {"n": 0}

    async def broken(*_a):
        calls["n"] += 1
        raise ToolError("permanently broken")

    gateway = _gateway(_parallel_server(broken), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.kind == "tool_error"
    assert calls["n"] == 1
    assert no_wait == []


# ===================================================================================== Crawl timeout
async def test_timed_out_status_read_retries_same_job(no_wait) -> None:
    crawl_calls = {"n": 0}
    status_calls = {"n": 0}

    async def crawl_handler(*_a):
        crawl_calls["n"] += 1
        return {"id": "job-timeout"}

    async def status_handler(job_id):
        status_calls["n"] += 1
        assert job_id == "job-timeout"
        if status_calls["n"] == 1:
            await asyncio.sleep(0.5)  # cut short by the gateway's per-call timeout
            return _DEFAULT_CRAWL_PAGES
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=crawl_handler, status_handler=status_handler),
        firecrawl_timeout=0.05,
    )
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()
    assert isinstance(result, CrawlResult)
    assert crawl_calls["n"] == 1  # the crawl is never re-issued
    assert status_calls["n"] == 2  # the timed-out status read is asked again with the same id


# ===================================================================================== Arguments
async def test_crawl_sends_depth_and_disallows_external_links() -> None:
    seen = {}

    async def crawl_handler(url, limit, max_depth, allow_external):
        seen.update(
            url=url, limit=limit, maxDiscoveryDepth=max_depth, allowExternalLinks=allow_external
        )
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(_parallel_server(), _firecrawl_server(crawl_handler=crawl_handler))
    await gateway.open()
    await gateway.crawl_site("https://x.test", limit=5, depth=2)
    await gateway.aclose()
    assert seen["maxDiscoveryDepth"] == 2
    assert seen["allowExternalLinks"] is False
    assert seen["limit"] == 5


async def test_bad_crawl_arguments_raise_value_error() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    try:
        with pytest.raises(ValueError):
            await gateway.crawl_site("https://x.test", limit=0, depth=1)
        with pytest.raises(ValueError):
            await gateway.crawl_site("https://x.test", limit=1, depth=-1)
        with pytest.raises(ValueError):
            await gateway.crawl_site("ftp://x.test", limit=1, depth=1)
    finally:
        await gateway.aclose()


# ===================================================================================== Concurrency
async def test_in_flight_searches_never_exceed_semaphore() -> None:
    state = {"active": 0, "max": 0}

    async def tracking(objective, _queries):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        try:
            await asyncio.sleep(0.01)
            return {"results": [{"url": "http://a", "title": objective, "text": objective}]}
        finally:
            state["active"] -= 1

    gateway = _gateway(
        _parallel_server(tracking), _firecrawl_server(), search_concurrency=4
    )
    await gateway.open()
    results = await asyncio.gather(
        *(gateway.search_web(f"obj-{i}", ["q"]) for i in range(10))
    )
    await gateway.aclose()
    assert state["max"] <= 4
    # Each concurrent call returns its own result, matched by the echoed objective.
    assert {r.excerpts[0].title for r in results} == {f"obj-{i}" for i in range(10)}


async def test_concurrent_map_and_scrape_share_one_firecrawl_pool() -> None:
    state = {"active": 0, "max": 0}

    async def tracked(body_for):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        try:
            await asyncio.sleep(0.01)
            return body_for
        finally:
            state["active"] -= 1

    async def map_handler(_url):
        return await tracked(_DEFAULT_MAP_BODY)

    async def scrape_handler(url, _formats, _only_main):
        return await tracked({"markdown": url, "metadata": {"sourceURL": url}})

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(map_handler=map_handler, scrape_handler=scrape_handler),
        firecrawl_concurrency=2,
    )
    await gateway.open()
    urls = [f"https://x.test/{i}" for i in range(6)]
    results = await asyncio.gather(
        gateway.map_site("https://x.test"),
        gateway.map_site("https://y.test"),
        *(gateway.scrape_page(u) for u in urls),
    )
    await gateway.aclose()
    assert state["max"] <= 2
    scraped = results[2:]
    # Each concurrent scrape returns its own page.
    assert [r.url for r in scraped] == urls
    assert [r.text for r in scraped] == urls


# ===================================================================================== Session scope
async def test_call_before_open_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    with pytest.raises(McpConnectionError):
        await gateway.search_web("o", ["q"])
    with pytest.raises(McpConnectionError):
        await gateway.map_site("https://x.test")
    with pytest.raises(McpConnectionError):
        await gateway.scrape_page("https://x.test")


async def test_aclose_is_idempotent() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    await gateway.aclose()
    await gateway.aclose()  # no error on the second close


async def test_failed_open_leaves_no_running_task() -> None:
    before = _session_tasks()
    gateway = _gateway(_parallel_server(), McpConnectionError("boom"))
    with pytest.raises(McpConnectionError):
        await gateway.open()
    await asyncio.sleep(0)  # let any unwinding finish
    assert _session_tasks() == before


# ===================================================================================== Forced timeout
async def test_timed_out_search_leaves_session_usable(no_wait) -> None:
    counter: list[str] = []

    async def handler(objective, _queries):
        # Every attempt for "first" is cut short by the per-call timeout; "second" returns at once.
        if objective == "first":
            await asyncio.sleep(0.5)
        return {"results": [{"url": "http://a", "title": objective, "text": objective}]}

    gateway = _gateway(
        _parallel_server(handler),
        _firecrawl_server(),
        parallel_timeout=0.05,
        factory_counter=counter,
    )
    await gateway.open()
    timed_out = await gateway.search_web("first", ["q"])
    follow_up = await gateway.search_web("second", ["q"])
    await gateway.aclose()
    # The call gives up after exhausting its timeout retries, but the session is untouched.
    assert isinstance(timed_out, ToolFailure)
    assert timed_out.kind == "timeout"
    assert no_wait == [2.0, 3.0]
    assert isinstance(follow_up, WebSearchResult)
    assert follow_up.excerpts[0].title == "second"
    # Exactly one client was built per server at open; no new client after the timeout.
    assert counter.count("parallel") == 1


# ===================================================================================== Secrets
async def test_keys_never_appear_in_logs_or_errors(caplog) -> None:
    secret = "SECRET-KEY-DO-NOT-LEAK-123"
    caplog.set_level(logging.DEBUG, logger=DEEP_SEARCH_LOGGER_NAME)

    async def rate_limited(*_a):
        raise ToolError("rate limit exceeded")

    gateway = _gateway(_parallel_server(rate_limited), _firecrawl_server(), api_key=secret)
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert secret not in result.message
    assert secret not in caplog.text


async def test_keys_never_appear_in_map_or_scrape_logs(caplog, no_wait) -> None:
    secret = "SECRET-KEY-DO-NOT-LEAK-456"
    caplog.set_level(logging.DEBUG, logger=DEEP_SEARCH_LOGGER_NAME)

    async def rate_limited(_url, *_rest):
        raise ToolError("rate limit exceeded")

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            map_handler=_except_probe(rate_limited, _DEFAULT_MAP_BODY),
            scrape_handler=_except_probe(rate_limited, _DEFAULT_SCRAPE_BODY),
        ),
        api_key=secret,
    )
    await gateway.open()
    mapped = await gateway.map_site("https://x.test")
    scraped = await gateway.scrape_page("https://x.test")
    await gateway.aclose()
    assert isinstance(mapped, ToolFailure) and isinstance(scraped, ToolFailure)
    assert secret not in mapped.message and secret not in scraped.message
    assert secret not in caplog.text
    # The failed attempts are logged at WARN and carry the page they were for.
    assert "mcp.call_attempt_failed" in caplog.text
    assert "https://x.test" in caplog.text


# ============================================================ Iteration 3: classifier (M6, M7)
async def test_mcp_error_sse_disconnect_is_transport_and_retried(no_wait) -> None:
    disconnect = MCPError(-32000, "SSE stream ended and reconnection attempts were exhausted")
    gateway = _gateway(
        _parallel_server(), _firecrawl_server(), flaky={"parallel": [disconnect, disconnect]}
    )
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()
    assert isinstance(result, WebSearchResult)  # retried on the same session and recovered
    assert no_wait == [2.0, 3.0]  # transport backoff, not the rate-limit one


async def test_persistent_sse_disconnect_returns_transport_failure(no_wait) -> None:
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


async def test_a_429_wrapped_in_mcperror_is_rate_limited(no_wait) -> None:
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


def test_classifier_maps_mcp_error_and_wrapped_429() -> None:
    sse = MCPError(-32000, "SSE stream ended and reconnection attempts were exhausted")
    assert _classify_failure(sse) == "transport"
    assert _classify_failure(MCPError(-32000, "boom: 429")) == "rate_limited"
    # An MCPError that is neither a disconnect nor a 429 stays a tool error (de-mask on the message).
    assert _classify_failure(MCPError(-32000, "tool blew up")) == "tool_error"


# ============================================================ Iteration 3: batch scrape (A4)
async def test_batch_scrape_polls_a_job_to_completion_keyed_by_source_url() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    result = await gateway.batch_scrape(["https://x.test/1", "https://x.test/2"])
    await gateway.aclose()
    assert isinstance(result, BatchScrapeResult)
    assert [(p.url, p.text) for p in result.pages] == [
        ("https://x.test/1", "page one"),
        ("https://x.test/2", "page two"),
    ]
    assert (result.total, result.completed, result.failed_urls) == (2, 2, ())
    assert result.retrieved_at


async def test_batch_scrape_follows_the_next_cursor(no_wait) -> None:
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
    result = await gateway.batch_scrape(["https://x.test/1", "https://x.test/2"])
    await gateway.aclose()
    assert isinstance(result, BatchScrapeResult)
    assert [p.url for p in result.pages] == ["https://x.test/1", "https://x.test/2"]


async def test_batch_partial_failure_rides_failed_urls_and_logs(caplog) -> None:
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
    result = await gateway.batch_scrape(["https://x.test/1", "https://x.test/2"])
    await gateway.aclose()
    assert isinstance(result, BatchScrapeResult)
    assert [p.url for p in result.pages] == ["https://x.test/1"]
    assert result.failed_urls == ("https://x.test/2",)
    assert "mcp.batch_pages_failed" in caplog.text


async def test_unreadable_batch_status_is_unparseable() -> None:
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(batch_status_handler=_static({"status": "banana"})),
    )
    await gateway.open()
    result = await gateway.batch_scrape(["https://x.test/1"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_check_batch_scrape_status", "unparseable")


async def test_batch_deadline_returns_timeout_carrying_the_job_id(short_wait, monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "BATCH_DEADLINE_SECONDS", 0.2)
    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            batch_handler=_static({"id": "batch-stuck"}),
            batch_status_handler=_static({"status": "scraping"}),
        ),
    )
    await gateway.open()
    result = await gateway.batch_scrape(["https://x.test/1"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert (result.tool, result.kind) == ("firecrawl_check_batch_scrape_status", "timeout")
    assert "batch-stuck" in result.message


async def test_bad_batch_input_raises_value_error() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    try:
        with pytest.raises(ValueError):
            await gateway.batch_scrape([])
        with pytest.raises(ValueError):
            await gateway.batch_scrape(["https://x.test/ok", "ftp://x.test"])
    finally:
        await gateway.aclose()


async def test_missing_batch_tool_fails_per_call_not_at_connect(no_wait) -> None:
    # Batch is not capability-checked (user decision): open() succeeds, the gap shows only on use.
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_batch=False))
    await gateway.open()
    result = await gateway.batch_scrape(["https://x.test/1"])
    await gateway.aclose()
    assert isinstance(result, ToolFailure)
    assert result.tool == "firecrawl_batch_scrape"


# ============================================================ Iteration 3: slow stream (M5), real HTTP
def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _settings(urls: dict, *, parallel_key, firecrawl_key) -> Settings:
    return Settings.model_construct(
        parallel_api_key=parallel_key,
        firecrawl_api_key=firecrawl_key,
        parallel_mcp_url=urls["parallel"],
        firecrawl_mcp_url=urls["firecrawl"],
        firecrawl_probe_url=_PROBE_URL,
    )


async def test_a_slow_stream_is_not_severed_by_the_read_timeout() -> None:
    # Over real loopback HTTP: a scrape whose body streams for ~6 s (longer than httpx's old 5 s
    # read default) must still complete, proving the factory sets read=None (M5).
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
        uv = uvicorn.Server(
            uvicorn.Config(server.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning")
        )
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
            scraped = await gateway.scrape_page("https://x.test/slow")
        finally:
            await gateway.aclose()
        assert isinstance(scraped, ScrapeResult)  # not a ToolFailure(timeout/transport)
        assert scraped.text == "late body"
    finally:
        for uv, thread in running:
            uv.should_exit = True
            thread.join(timeout=10)
