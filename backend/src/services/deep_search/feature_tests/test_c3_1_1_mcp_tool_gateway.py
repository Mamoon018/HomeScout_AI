"""Tests for R2 Mechanism 3 Component C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl).

Implements the reviewed plan in `C3_1_1_mcp_tool_gateway_test_plan.md` (same folder). Each test
drives the real `McpToolGateway` and the real `mcp.Client` against an in-process `MCPServer`
injected through the gateway's own `client_factory` seam, so only the hosted vendor servers are
faked (costly / networked / non-deterministic). Backoff and poll waits are made deterministic by
recording `mcp_tools._async_sleep`; genuine timeouts use real `asyncio.timeout` with tiny budgets.

Test ids (T1..T24) map one-to-one to the plan entries.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from src.clients import mcp_tools
from src.clients.mcp_tools import (
    CrawlResult,
    McpServerConfig,
    McpToolGateway,
    ToolFailure,
    WebSearchResult,
    _classify_failure,
    _parse_search_result,
)
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.mcp import McpConnectionError, McpToolUnavailableError


# ============================================================================= harness
def _static(value):
    async def handler(*_args, **_kwargs):
        return value

    return handler


_DEFAULT_SEARCH_BODY = {"results": [{"url": "http://a", "title": "A", "text": "body"}]}
_DEFAULT_CRAWL_PAGES = {
    "status": "completed",
    "data": [{"url": "http://p/1", "title": "P1", "markdown": "page one"}],
}


def _parallel_server(handler=None, *, include_queries_arg: bool = True) -> MCPServer:
    """In-process stand-in for Parallel. `handler` is an async fn returning the tool body."""
    server = MCPServer(name="parallel-srv")
    handler = handler or _static(_DEFAULT_SEARCH_BODY)
    if include_queries_arg:

        @server.tool()
        async def web_search(objective: str, search_queries: list[str]) -> dict:
            return await handler(objective, search_queries)

    else:

        @server.tool()
        async def web_search(objective: str) -> dict:  # noqa: F811 - missing-arg variant
            return await handler(objective)

    return server


def _firecrawl_server(
    crawl_handler=None,
    status_handler=None,
    *,
    include_crawl: bool = True,
    include_status: bool = True,
) -> MCPServer:
    """In-process stand-in for Firecrawl, with the crawl and status tools toggleable."""
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


def _factory(targets: dict, counter: list | None = None):
    """Client factory mapping config.name → an MCPServer, or an Exception to raise on connect."""

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
    """Record each retry/poll backoff and return immediately instead of sleeping."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(mcp_tools, "_async_sleep", fake_sleep)
    return waits


# ============================================================================= Capability check


async def test_open_succeeds_when_both_catalogs_expose_required_tools_and_args() -> None:  # T1
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()  # returns only if every required tool+arg matched
    await gateway.aclose()


async def test_missing_required_tool_raises_tool_unavailable_at_verify() -> None:  # T2
    # Firecrawl without the crawl tool — the same path a keyless Firecrawl hits in production.
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_crawl=False))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_required_argument_raises_tool_unavailable() -> None:  # T3
    gateway = _gateway(_parallel_server(include_queries_arg=False), _firecrawl_server())
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


async def test_missing_status_tool_raises_tool_unavailable() -> None:  # T4
    gateway = _gateway(_parallel_server(), _firecrawl_server(include_status=False))
    with pytest.raises(McpToolUnavailableError) as exc:
        await gateway.open()
    assert exc.value.stage == "verify_capabilities"


# ============================================================================= Typed search results


async def test_search_returns_typed_result_with_stamped_timestamp_and_echoed_request() -> None:  # T5
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("find bakeries", ["bakery near me"])
    await gateway.aclose()

    assert isinstance(result, WebSearchResult)
    assert result.objective == "find bakeries"
    assert result.search_queries == ("bakery near me",)
    assert result.retrieved_at  # stamped on receipt
    assert len(result.excerpts) == 1
    assert result.excerpts[0].url == "http://a"  # read from the server body, not the request
    assert result.excerpts[0].text == "body"


async def test_empty_search_hit_list_returns_zero_excerpts_not_a_failure() -> None:  # T6
    gateway = _gateway(_parallel_server(_static({"results": []})), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()

    assert isinstance(result, WebSearchResult)
    assert result.excerpts == ()
    assert result.retrieved_at


async def test_tool_error_result_returns_toolfailure_not_raised() -> None:  # T7
    async def boom(*_a):
        raise ToolError("the tool is broken")

    gateway = _gateway(_parallel_server(boom), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])  # must return, not raise
    await gateway.aclose()

    assert isinstance(result, ToolFailure)
    assert result.kind == "tool_error"


async def test_unrecognized_search_body_returns_toolfailure_unparseable() -> None:  # T8
    gateway = _gateway(_parallel_server(_static("<<<not json>>>")), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()

    assert isinstance(result, ToolFailure)
    assert result.kind == "unparseable"


def test_search_parser_prefers_structured_content_over_text() -> None:  # T9 (unit)
    # The in-process server always sets both fields, so preference is proven at the parser: the text
    # block is deliberately non-JSON; parsing must still succeed from structured_content.
    result = CallToolResult(
        content=[TextContent(type="text", text="<<<not json>>>")],
        structured_content={"results": [{"url": "http://s", "title": "S", "text": "structured"}]},
        is_error=False,
    )
    parsed = _parse_search_result(result, "o", ("q",), "2026-01-01T00:00:00+00:00")

    assert isinstance(parsed, WebSearchResult)
    assert parsed.excerpts[0].url == "http://s"
    assert parsed.excerpts[0].text == "structured"


# ============================================================================= Search retry policy


async def test_transient_search_failure_retries_twice_with_backoffs_then_fails(no_wait) -> None:  # T10
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
    assert calls["n"] == 3  # one attempt + two retries
    assert no_wait == [2.0, 3.0]


async def test_non_transient_search_failure_makes_single_attempt(no_wait) -> None:  # T11
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


# ============================================================================= Crawl args & validation


async def test_crawl_sends_depth_and_disables_external_links() -> None:  # T12
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


async def test_invalid_crawl_arguments_raise_value_error() -> None:  # T13
    called = {"n": 0}

    async def crawl_handler(*_a):
        called["n"] += 1
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(_parallel_server(), _firecrawl_server(crawl_handler=crawl_handler))
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

    assert called["n"] == 0  # the guard rejects before any call is spent


# ============================================================================= Crawl shapes & job reading


async def test_crawl_returns_pages_when_start_response_has_them() -> None:  # T14
    status_calls = {"n": 0}

    async def status_handler(_id):
        status_calls["n"] += 1
        return _DEFAULT_CRAWL_PAGES

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(
            crawl_handler=_static(_DEFAULT_CRAWL_PAGES), status_handler=status_handler
        ),
    )
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()

    assert isinstance(result, CrawlResult)
    assert result.pages[0].url == "http://p/1"
    assert result.pages[0].text == "page one"
    assert status_calls["n"] == 0  # inline pages accepted; no polling


async def test_crawl_polls_job_id_to_completion(no_wait) -> None:  # T15
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
    assert status_calls["n"] == 2  # advanced running → completed
    assert result.pages[0].url == "http://p/1"


async def test_timed_out_status_read_retries_same_job_without_reissuing_crawl(no_wait) -> None:  # T16
    crawl_calls = {"n": 0}
    status_calls = {"n": 0}
    seen_ids: list[str] = []

    async def crawl_handler(*_a):
        crawl_calls["n"] += 1
        return {"id": "job-timeout"}

    async def status_handler(job_id):
        status_calls["n"] += 1
        seen_ids.append(job_id)
        if status_calls["n"] == 1:
            await asyncio.sleep(0.5)  # cut short by the per-call timeout
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
    assert status_calls["n"] == 2  # the timed-out read is asked again
    assert seen_ids == ["job-timeout", "job-timeout"]  # always the same id


async def test_crawl_deadline_reached_returns_timeout_carrying_job_id(no_wait, monkeypatch) -> None:  # T17
    monkeypatch.setattr(mcp_tools, "CRAWL_DEADLINE_SECONDS", 0.05)

    async def status_handler(_id):
        await asyncio.sleep(0.005)  # advance real time so the deadline is reached deterministically
        return {"status": "scraping"}  # never completes

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=_static({"id": "job-stuck"}), status_handler=status_handler),
    )
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()

    assert isinstance(result, ToolFailure)
    assert result.kind == "timeout"
    assert "job-stuck" in result.message  # the job handle is preserved, not lost


# ============================================================================= Session scope & lifecycle


async def test_call_before_open_raises_connection_error() -> None:  # T18
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    with pytest.raises(McpConnectionError):
        await gateway.search_web("o", ["q"])


async def test_aclose_is_idempotent() -> None:  # T19
    gateway = _gateway(_parallel_server(), _firecrawl_server())
    await gateway.open()
    await gateway.aclose()
    await gateway.aclose()  # second close is a no-op, not an error


async def test_failed_open_raises_and_leaves_no_running_task() -> None:  # T20
    before = {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}
    gateway = _gateway(_parallel_server(), McpConnectionError("connect refused"))
    with pytest.raises(McpConnectionError):
        await gateway.open()
    await asyncio.sleep(0)  # let any unwinding settle
    after = {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}
    assert after == before  # the already-started owner task was torn down


# ============================================================================= Concurrency & shared client


async def test_concurrent_searches_respect_semaphore_and_return_own_results() -> None:  # T21
    state = {"active": 0, "max": 0}

    async def tracking(objective, _queries):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        try:
            await asyncio.sleep(0.01)  # hold the slot so overlap is observable
            return {"results": [{"url": "http://a", "title": objective, "text": objective}]}
        finally:
            state["active"] -= 1

    gateway = _gateway(_parallel_server(tracking), _firecrawl_server(), search_concurrency=4)
    await gateway.open()
    results = await asyncio.gather(*(gateway.search_web(f"obj-{i}", ["q"]) for i in range(10)))
    await gateway.aclose()

    assert state["max"] <= 4  # semaphore bounds in-flight work
    assert {r.excerpts[0].title for r in results} == {f"obj-{i}" for i in range(10)}  # no cross-talk


async def test_timed_out_call_leaves_same_client_usable_without_rebuild(no_wait) -> None:  # T22
    counter: list[str] = []

    async def handler(objective, _queries):
        if objective == "first":
            await asyncio.sleep(0.5)  # every attempt cut short by the per-call timeout
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

    assert isinstance(timed_out, ToolFailure)
    assert timed_out.kind == "timeout"
    assert no_wait == [2.0, 3.0]  # exhausted the timeout retries
    assert isinstance(follow_up, WebSearchResult)
    assert follow_up.excerpts[0].title == "second"  # same session still serves
    assert counter.count("parallel") == 1  # no new client was built after the timeout


# ============================================================================= Secret hygiene


async def test_api_keys_never_appear_in_logs_or_failure_messages(caplog) -> None:  # T23
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


# ============================================================================= Failure classification (unit)


def test_classify_failure_maps_transport_and_rate_limited_exceptions() -> None:  # T24
    # These classes cannot be produced by the in-process fake without real network, yet a
    # misclassification changes retry behavior, so the pure function is tested directly here.
    class RateLimited(Exception):
        status_code = 429

    assert _classify_failure(ConnectionError("link down")) == "transport"
    assert _classify_failure(RateLimited("slow down")) == "rate_limited"


# ============================================================= Drift-remediation behaviors (D1–D4)
# Lock in the four C3.1.1 drift fixes: parser de-masks (search + crawl status), open() cleanup on
# cancellation, and search input validation.


async def test_unrecognised_search_object_returns_toolfailure_unparseable() -> None:  # D1
    # A JSON object with no recognised hit-list key is an unreadable shape, NOT an empty search
    # (contrast T6, where `{"results": []}` is a valid empty result).
    gateway = _gateway(_parallel_server(_static({"unexpected": 1})), _firecrawl_server())
    await gateway.open()
    result = await gateway.search_web("o", ["q"])
    await gateway.aclose()

    assert isinstance(result, ToolFailure)  # not WebSearchResult(excerpts=())
    assert result.kind == "unparseable"


async def test_unrecognised_crawl_status_returns_unparseable_without_polling(no_wait) -> None:  # D2
    status_calls = {"n": 0}

    async def status_handler(_id):
        status_calls["n"] += 1
        return {"state": "weird"}  # neither a known running nor terminal status, and no pages

    gateway = _gateway(
        _parallel_server(),
        _firecrawl_server(crawl_handler=_static({"id": "job-x"}), status_handler=status_handler),
    )
    await gateway.open()
    result = await gateway.crawl_site("https://x.test", limit=3, depth=1)
    await gateway.aclose()

    assert isinstance(result, ToolFailure)
    assert result.kind == "unparseable"
    assert status_calls["n"] == 1  # de-masked on the first read; not polled to the deadline
    assert no_wait == []  # and no poll backoff was ever slept (contrast T17's poll-to-timeout)


async def test_open_cancelled_mid_connect_leaves_no_task_and_does_not_hang() -> None:  # D3
    blocker = asyncio.Event()  # never set → firecrawl stays mid-connect
    parallel = _parallel_server()

    def factory(config: McpServerConfig):
        @asynccontextmanager
        async def cm():
            if config.name == "firecrawl":
                await blocker.wait()  # block inside connect, before readiness is published
                yield None  # unreachable
            else:
                async with Client(parallel) as client:
                    yield client

        return cm()

    gateway = McpToolGateway(
        McpServerConfig("parallel", "http://parallel", None, 5.0),
        McpServerConfig("firecrawl", "http://firecrawl", None, 5.0),
        client_factory=factory,
    )

    before = {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}
    open_task = asyncio.ensure_future(gateway.open())
    for _ in range(5):  # let parallel become ready and firecrawl's owner task reach the block
        await asyncio.sleep(0)
    open_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(open_task, timeout=1.0)  # completes quickly → no hang
    await asyncio.sleep(0)  # let teardown settle
    after = {t for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session")}
    assert after == before  # both owner tasks were torn down, none leaked


async def test_search_rejects_empty_objective_and_queries_before_any_call() -> None:  # D4
    called = {"n": 0}

    async def handler(objective, _queries):
        called["n"] += 1
        return _DEFAULT_SEARCH_BODY

    gateway = _gateway(_parallel_server(handler), _firecrawl_server())
    await gateway.open()
    try:
        with pytest.raises(ValueError):
            await gateway.search_web("", ["q"])
        with pytest.raises(ValueError):
            await gateway.search_web("   ", ["q"])
        with pytest.raises(ValueError):
            await gateway.search_web("o", ["", "  "])
    finally:
        await gateway.aclose()

    assert called["n"] == 0  # rejected before any call is spent (mirrors T13)
