"""Offline fixtures for R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

No network and no keys: each test wires an in-process `MCPServer` into the gateway through the
client factory seam, so the real gateway code paths (owner tasks, capability check, retry, timeout,
parsing, concurrency, close) run against a fake server on the event loop.
"""

import asyncio
import logging

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from src.clients import mcp_tools
from src.clients.mcp_tools import (
    CrawlResult,
    McpServerConfig,
    McpToolGateway,
    ToolFailure,
    WebSearchResult,
)
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError


# ------------------------------------------------------------------------------------- handlers
def _static(value):
    async def handler(*_args, **_kwargs):
        return value

    return handler


_DEFAULT_SEARCH_BODY = {"results": [{"url": "http://a", "title": "A", "text": "body"}]}
_DEFAULT_CRAWL_PAGES = {
    "status": "completed",
    "data": [{"url": "http://p/1", "title": "P1", "markdown": "page one"}],
}


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
    include_crawl: bool = True,
    include_status: bool = True,
) -> MCPServer:
    server = MCPServer(name="firecrawl-srv")
    crawl_handler = crawl_handler or _static({"id": "job-1"})
    status_handler = status_handler or _static(_DEFAULT_CRAWL_PAGES)
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

    return server


# ------------------------------------------------------------------------------------- factory
def _factory(targets: dict, counter: list | None = None):
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
    crawl_concurrency: int = 2,
    api_key: str | None = None,
    factory_counter: list | None = None,
) -> McpToolGateway:
    parallel = McpServerConfig("parallel", "http://parallel", api_key, parallel_timeout)
    firecrawl = McpServerConfig("firecrawl", "http://firecrawl", api_key, firecrawl_timeout)
    factory = _factory(
        {"parallel": parallel_target, "firecrawl": firecrawl_target}, factory_counter
    )
    return McpToolGateway(
        parallel,
        firecrawl,
        search_concurrency=search_concurrency,
        crawl_concurrency=crawl_concurrency,
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


# ===================================================================================== Capabilities
async def test_full_capability_set_passes() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    await gateway.aclose()


async def test_missing_tool_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_crawl=False))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_argument_raises() -> None:
    gateway = _gateway(_parallel_server(include_queries_arg=False), _firecrawl_server())
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_status_tool_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_status=False))
    with pytest.raises(McpToolUnavailableError):
        await gateway.open()


async def test_keyless_firecrawl_without_crawl_tool_raises() -> None:
    # A keyless Firecrawl exposes no crawl tool; the capability check reports it like any miss.
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_crawl=False), api_key=None)
    with pytest.raises(McpToolUnavailableError):
        await gateway.open()


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
    assert no_wait == [2.0, 3.0]


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


# ===================================================================================== Session scope
async def test_call_before_open_raises() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    with pytest.raises(McpConnectionError):
        await gateway.search_web("o", ["q"])


async def test_aclose_is_idempotent() -> None:
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    await gateway.aclose()
    await gateway.aclose()  # no error on the second close


async def test_failed_open_leaves_no_running_task() -> None:
    before = {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}
    gateway = _gateway(_parallel_server(), McpConnectionError("boom"))
    with pytest.raises(McpConnectionError):
        await gateway.open()
    await asyncio.sleep(0)  # let any unwinding finish
    after = {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}
    assert after == before


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
