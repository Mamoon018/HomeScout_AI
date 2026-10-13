"""Manual, stage-by-stage run of R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

Not a test: it asserts nothing and writes nothing to disk. It hits the real Parallel and Firecrawl
MCP servers and calls no LLM, so there is no prompt module and no worked-pair examples. It seeds the
amenity from a real M1.1 capture (`data/m1_1_discovered_places.json`, the file the M1.2 runner uses):
the first place's `display_name.text` and `website_uri`. M1.1, M1.2 and M1.3 are not called; the
objective and queries are hand-written. Raw per-attempt and session records are read back off the
`homescout.deep_search` logger with a collecting handler.

From `backend/` (needs PARALLEL_API_KEY, FIRECRAWL_API_KEY and network access):
    python -m src.services.deep_search.feature_sample_runs.mcp_tool_gateway_sample_run

Stages: open (capability check, then the Firecrawl shape probe), search_web, map_site, scrape_page,
and aclose. Crawl is retained in the gateway but unused by M3, so it only runs with --crawl.

Flags:
    --v2a                 ten concurrent searches checked against their own requests, plus a
                          cancelled call mid-flight, then a follow-up (spends Parallel credits)
    --v2b                 one map, then several concurrent scrapes of mapped pages, each checked
                          against its own page, plus a cancelled scrape mid-flight and a follow-up
                          scrape on the same session (spends Firecrawl credits)
    --crawl               also run the retained crawl_site stage (spends Firecrawl credits)
    --url <url>           the site that map, scrape and crawl target (default: the seeded
                          place's website)
"""

import argparse
import asyncio
import json
import logging
import pathlib
import sys
from urllib.parse import urlsplit

from src.clients.mcp_tools import (
    BatchScrapeResult,
    CrawlResult,
    MapResult,
    ScrapeResult,
    ToolFailure,
    WebSearchResult,
    create_mcp_tool_gateway,
)
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.mcp import McpGatewayError

_RULE = "=" * 78

_DISCOVERED_PLACES_PATH = pathlib.Path(__file__).parent / "data" / "m1_1_discovered_places.json"

# Hand-written, not copied from any prompt.
_OBJECTIVE = "Find the opening hours and admission prices of this public swimming pool."
_SEARCH_QUERIES = (
    "Brentanobad Frankfurt opening hours",
    "Brentanobad Frankfurt admission price",
)
_CRAWL_LIMIT = 3
_CRAWL_DEPTH = 1
# Fallback site used only when neither --url nor the seeded M1.1 website is available.
_FALLBACK_SITE_URL = "https://www.frankfurter-baeder.de/freibad-brentanobad/"


class _RecordCollector(logging.Handler):
    """Collect `homescout.deep_search` records so each stage can print the raw call trail."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())

    def drain(self) -> list[str]:
        out, self.records = self.records, []
        return out


def _install_call_tracer(logger: logging.Logger, secrets: tuple[str, ...]) -> None:
    """Wrap the MCP SDK's `Client.call_tool` so the raw per-call outcome is logged.

    The gateway's `_single_call` collapses every per-call problem into a bare
    `ToolFailure(kind="tool_error", message="tool returned an error")` and discards the
    underlying exception type/text (and the server body behind an `is_error` result). That makes
    two very different causes indistinguishable in the logs:

      (A) the server RETURNED a result with `is_error=True` (a real tool error), or
      (B) `call_tool` RAISED while receiving/validating an otherwise-successful response
          (e.g. an SDK `pydantic.ValidationError` on a protocol/shape mismatch).

    This tracer sits *outside* the gateway, logs the truth before it is thrown away, and changes
    no production code. It redacts the configured API keys from everything it emits.
    """
    from mcp import Client

    if getattr(Client.call_tool, "_homescout_traced", False):
        return  # idempotent: don't double-wrap on a second call
    original = Client.call_tool
    masks = tuple(s for s in secrets if s)

    def _redact(text: str) -> str:
        for secret in masks:
            text = text.replace(secret, "<redacted>")
        return text

    async def traced(self, name, *args, **kwargs):  # noqa: ANN001
        try:
            result = await original(self, name, *args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - logged for diagnosis, then re-raised unchanged
            logger.info(
                json.dumps(
                    {
                        "event": "mcp_diag.call_tool_raised",
                        "timestamp": _timestamp(),
                        "tool": name,
                        "exc_type": f"{type(exc).__module__}.{type(exc).__name__}",
                        "exc_message": _redact(str(exc))[:500],
                    }
                )
            )
            raise
        if getattr(result, "is_error", False):
            text = "\n".join(
                getattr(block, "text", "") or "" for block in (getattr(result, "content", None) or [])
            )
            logger.info(
                json.dumps(
                    {
                        "event": "mcp_diag.call_tool_is_error",
                        "timestamp": _timestamp(),
                        "tool": name,
                        "server_text": _redact(text)[:500],
                        "has_structured": getattr(result, "structured_content", None) is not None,
                    }
                )
            )
        return result

    traced._homescout_traced = True  # type: ignore[attr-defined]
    Client.call_tool = traced  # type: ignore[assignment]


def _install_transport_tracer(logger: logging.Logger, secrets: tuple[str, ...]) -> None:
    """Route the MCP SDK's own transport logs into our redacted diagnostic stream.

    The call tracer tells us `call_tool` raised `MCPError("SSE stream ended and reconnection
    attempts were exhausted")`, but not *why* the stream dropped. The SDK already logs that: the
    Streamable-HTTP transport (`mcp.client.streamable_http`) emits "SSE stream ended" with the
    underlying exception attached (`exc_info`), plus the reconnection attempts, and the HTTP layer
    (`httpcore`/`httpx`) logs the connection lifecycle and any read/close error beneath it.

    This attaches one redacting relay to those loggers at DEBUG, turns OFF their propagation (so no
    raw line — which at httpcore DEBUG can include an `Authorization` header — reaches the console
    unredacted), and re-emits each record as an `mcp_diag.transport` event through our logger, with
    the exception type/message pulled out of `exc_info`. That exception is the disconnect's cause.

    Verbose by design (httpcore DEBUG logs every connection step); it is behind the trace flag.
    """
    masks = tuple(s for s in secrets if s)

    def _redact(text: str) -> str:
        for secret in masks:
            text = text.replace(secret, "<redacted>")
        return text

    class _Relay(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                payload = {
                    "event": "mcp_diag.transport",
                    "timestamp": _timestamp(),
                    "src": record.name,
                    "level": record.levelname,
                    "message": _redact(record.getMessage())[:600],
                }
                if record.exc_info and record.exc_info[0] is not None:
                    exc_type, exc_val = record.exc_info[0], record.exc_info[1]
                    payload["exc_type"] = f"{exc_type.__module__}.{exc_type.__name__}"
                    payload["exc_message"] = _redact(str(exc_val))[:600] if exc_val else None
                logger.info(json.dumps(payload))
            except Exception:  # noqa: BLE001 - a tracer must never break the run it observes
                pass

    relay = _Relay()
    relay.setLevel(logging.DEBUG)
    for name in ("mcp.client.streamable_http", "mcp", "httpcore", "httpx", "httpx2"):
        sdk_logger = logging.getLogger(name)
        if any(getattr(h, "_homescout_transport_relay", False) for h in sdk_logger.handlers):
            continue  # idempotent
        relay._homescout_transport_relay = True  # type: ignore[attr-defined]
        sdk_logger.setLevel(logging.DEBUG)
        sdk_logger.addHandler(relay)
        sdk_logger.propagate = False  # keep raw (unredacted) SDK lines off every other handler


def _install_http_header_tracer(logger: logging.Logger, secrets: tuple[str, ...]) -> None:
    """Log the reconnect-relevant request headers the transport logs don't expose.

    The SDK logs *that* it reconnected via GET and got 405, but not the `Last-Event-ID` it used to
    resume the stream, nor the `Mcp-Session-Id` it carried. Those settle the open question: did the
    reconnect GET go out with an empty/old id? This wraps the one HTTP funnel every MCP request
    passes through (`httpx2.AsyncClient.send`) and emits an `mcp_diag.http_request` event per
    request with its method, URL, and those two headers. `Authorization` is reported only as a
    present/absent flag, never its value, and configured keys are redacted everywhere.
    """
    import httpx2

    if getattr(httpx2.AsyncClient.send, "_homescout_traced", False):
        return  # idempotent
    original = httpx2.AsyncClient.send
    masks = tuple(s for s in secrets if s)

    def _redact(text):  # noqa: ANN001
        if text is None:
            return None
        for secret in masks:
            text = text.replace(secret, "<redacted>")
        return text

    async def send(self, request, *args, **kwargs):  # noqa: ANN001
        try:
            headers = request.headers
            logger.info(
                json.dumps(
                    {
                        "event": "mcp_diag.http_request",
                        "timestamp": _timestamp(),
                        "method": request.method,
                        "url": _redact(str(request.url)),
                        # Empty string → header present but blank; None → header absent entirely.
                        "last_event_id": _redact(headers.get("last-event-id")),
                        "mcp_session_id": _redact(headers.get("mcp-session-id")),
                        "has_authorization": "authorization" in headers,
                    }
                )
            )
        except Exception:  # noqa: BLE001 - a tracer must never break the run it observes
            pass
        return await original(self, request, *args, **kwargs)

    send._homescout_traced = True  # type: ignore[attr-defined]
    httpx2.AsyncClient.send = send  # type: ignore[assignment]


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


def _seed_amenity() -> tuple[str, str | None]:
    """Read the first place's display name and website from the real M1.1 capture."""
    raw = json.loads(_DISCOVERED_PLACES_PATH.read_text(encoding="utf-8"))
    first_category = next(iter(raw.values()))
    first_place = next(iter(first_category.values()))
    place = first_place.get("place", first_place)
    name = (place.get("display_name") or {}).get("text") or "unknown"
    return name, place.get("website_uri")


def _print_records(collector: _RecordCollector) -> None:
    for line in collector.drain():
        print(f"  log: {line}")


async def _stage_open(gateway, settings, collector: _RecordCollector) -> None:
    _section("STAGE 1 — open, capability check and Firecrawl shape probe")
    await gateway.open()
    # open() raised nothing, so every required tool and argument is present on both servers and the
    # probe confirmed the Firecrawl MCP server 3.x JSON output shape (see the mcp.probe_passed
    # record below).
    for name, key in (
        ("parallel", settings.parallel_api_key),
        ("firecrawl", settings.firecrawl_api_key),
    ):
        session = gateway._parallel if name == "parallel" else gateway._firecrawl
        listing = await session.client().list_tools(cache_mode="bypass")
        tool_names = [tool.name for tool in listing.tools]
        print(
            json.dumps(
                {
                    "server": name,
                    "connected": True,
                    "tool_count": len(tool_names),
                    "required_tools_and_args_found": True,
                    "map_tool_present": "firecrawl_map" in tool_names
                    if name == "firecrawl"
                    else "n/a",
                    "scrape_tool_present": "firecrawl_scrape" in tool_names
                    if name == "firecrawl"
                    else "n/a",
                    "crawl_tool_present_not_required": "firecrawl_crawl" in tool_names
                    if name == "firecrawl"
                    else "n/a",
                    "key_present": key is not None,
                },
                indent=2,
            )
        )
    _print_records(collector)


async def _stage_search(gateway, collector: _RecordCollector) -> bool:
    _section("STAGE 2 — search_web")
    print(f"request: objective={_OBJECTIVE!r} queries={list(_SEARCH_QUERIES)}")
    result = await gateway.search_web(_OBJECTIVE, _SEARCH_QUERIES)
    _print_records(collector)
    if isinstance(result, ToolFailure):
        print(f"ToolFailure: tool={result.tool} kind={result.kind} message={result.message}")
        return False
    assert isinstance(result, WebSearchResult)
    print(f"excerpt_count: {len(result.excerpts)}")
    print(f"retrieved_at: {result.retrieved_at}")
    for excerpt in result.excerpts[:5]:
        print(f"  - url={excerpt.url} title={excerpt.title!r} len={len(excerpt.text)}")
    return True


async def _stage_map(
    gateway, site_url: str, collector: _RecordCollector
) -> MapResult | None:
    _section("STAGE 3 — map_site")
    print(f"request: url={site_url}")
    result = await gateway.map_site(site_url)
    _print_records(collector)
    if isinstance(result, ToolFailure):
        print(f"ToolFailure: tool={result.tool} kind={result.kind} message={result.message}")
        return None
    assert isinstance(result, MapResult)
    print(f"link_count: {len(result.links)}")
    print(f"retrieved_at: {result.retrieved_at}")
    for link in result.links[:5]:
        print(f"  - url={link.url} title={link.title!r}")
    return result


async def _stage_scrape(gateway, page_url: str, collector: _RecordCollector) -> bool:
    _section("STAGE 4 — scrape_page")
    print(f"request: url={page_url}")
    result = await gateway.scrape_page(page_url)
    _print_records(collector)
    if isinstance(result, ToolFailure):
        print(f"ToolFailure: tool={result.tool} kind={result.kind} message={result.message}")
        return False
    assert isinstance(result, ScrapeResult)
    print(f"reported_url: {result.url}")
    print(f"text_length: {len(result.text)}")
    print(f"retrieved_at: {result.retrieved_at}")
    return True


async def _stage_batch(
    gateway, page_urls: list[str], collector: _RecordCollector
) -> bool:
    _section("STAGE 4b — batch_scrape (A4)")
    print(f"request: urls={page_urls}")
    result = await gateway.batch_scrape(page_urls)
    _print_records(collector)
    if isinstance(result, ToolFailure):
        print(f"ToolFailure: tool={result.tool} kind={result.kind} message={result.message}")
        return False
    assert isinstance(result, BatchScrapeResult)
    print(f"total: {result.total} completed: {result.completed} failed: {len(result.failed_urls)}")
    print(f"retrieved_at: {result.retrieved_at}")
    for page in result.pages[:5]:
        print(f"  - url={page.url} len={len(page.text)}")
    for failed in result.failed_urls[:5]:
        print(f"  - FAILED {failed}")
    return True


async def _stage_crawl(gateway, crawl_url: str, collector: _RecordCollector) -> bool:
    _section("STAGE 5 — crawl_site (retained, unused by M3)")
    print(f"request: url={crawl_url} limit={_CRAWL_LIMIT} depth={_CRAWL_DEPTH}")
    result = await gateway.crawl_site(crawl_url, limit=_CRAWL_LIMIT, depth=_CRAWL_DEPTH)
    _print_records(collector)
    if isinstance(result, ToolFailure):
        print(f"ToolFailure: tool={result.tool} kind={result.kind} message={result.message}")
        return False
    assert isinstance(result, CrawlResult)
    print(f"job_id: {result.job_id}")
    print(f"page_count: {len(result.pages)}")
    print(f"retrieved_at: {result.retrieved_at}")
    for page in result.pages[:5]:
        print(f"  - url={page.url} title={page.title!r} len={len(page.text)}")
    return True


async def _verify_v2a(gateway, collector: _RecordCollector) -> bool:
    _section("V2a — concurrent searches, a cancelled call, a follow-up")
    objectives = [f"{_OBJECTIVE} (variant {i})" for i in range(10)]
    results = await asyncio.gather(
        *(gateway.search_web(obj, _SEARCH_QUERIES) for obj in objectives)
    )
    ok = True
    for obj, result in zip(objectives, results):
        if isinstance(result, ToolFailure):
            print(f"  FAIL {obj!r}: {result.kind}")
            ok = False
        elif result.objective != obj:
            print(f"  MISMATCH: asked {obj!r}, got {result.objective!r}")
            ok = False
    print(f"ten concurrent searches matched their own requests: {ok}")

    cancelled = asyncio.ensure_future(gateway.search_web("cancel me", _SEARCH_QUERIES))
    await asyncio.sleep(0)
    cancelled.cancel()
    try:
        await cancelled
    except asyncio.CancelledError:
        print("mid-flight call cancelled cleanly")
    follow = await gateway.search_web("after cancel", _SEARCH_QUERIES)
    print(f"follow-up after cancel usable: {not isinstance(follow, ToolFailure)}")
    _print_records(collector)
    return ok and not isinstance(follow, ToolFailure)


_V2B_SCRAPES = 4


async def _verify_v2b(gateway, site_url: str, collector: _RecordCollector) -> bool:
    _section("V2b — one map, concurrent scrapes, a cancelled scrape, a follow-up")
    mapped = await gateway.map_site(site_url)
    if isinstance(mapped, ToolFailure):
        print(f"map_site failed: kind={mapped.kind} message={mapped.message}")
        _print_records(collector)
        return False
    # Scrape up to a handful of mapped pages; fall back to the site itself when the map is thin.
    pages = [link.url for link in mapped.links[:_V2B_SCRAPES]] or [site_url]
    results = await asyncio.gather(*(gateway.scrape_page(url) for url in pages))
    ok = True
    for url, result in zip(pages, results):
        if isinstance(result, ToolFailure):
            print(f"  FAIL {url}: {result.kind}")
            ok = False
        elif urlsplit(result.url).netloc != urlsplit(url).netloc:
            # Per Firecrawl's docs sourceURL is the URL that was requested, so a different host is
            # unexpected here; flag it so the match cannot be assumed.
            print(f"  MISMATCH: asked {url}, server reported {result.url}")
            ok = False
        elif result.url.rstrip("/") != url.rstrip("/"):
            print(f"  note: asked {url}, server reported {result.url} (same host)")
    print(f"concurrent scrapes matched their own pages: {ok}")

    cancelled = asyncio.ensure_future(gateway.scrape_page(site_url))
    await asyncio.sleep(0)
    cancelled.cancel()
    try:
        await cancelled
    except asyncio.CancelledError:
        print("mid-flight scrape cancelled cleanly")
    follow = await gateway.scrape_page(site_url)
    print(f"follow-up scrape after cancel usable: {not isinstance(follow, ToolFailure)}")
    _print_records(collector)
    return ok and not isinstance(follow, ToolFailure)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="C3.1.1 MCP tool gateway sample runner")
    parser.add_argument("--v2a", action="store_true", help="concurrent search verification")
    parser.add_argument("--v2b", action="store_true", help="concurrent scrape verification")
    parser.add_argument("--crawl", action="store_true", help="also run the retained crawl stage")
    parser.add_argument(
        "--trace-calls",
        action="store_true",
        help=(
            "diagnostics: log each raw MCP call outcome (is_error body vs raised exception) AND the "
            "SDK transport logs (SSE disconnect reason, reconnects, HTTP lifecycle), keys redacted"
        ),
    )
    parser.add_argument("--url", dest="url", default=None, help="site to map, scrape and crawl")
    return parser.parse_args(argv)


async def run_sample_mcp_gateway(argv: list[str]) -> int:
    args = _parse_args(argv)
    configure_logging("INFO")
    logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    logger.addHandler(collector)

    settings = get_settings()
    if args.trace_calls:
        secrets = (settings.parallel_api_key, settings.firecrawl_api_key)
        _install_call_tracer(logger, secrets)
        _install_transport_tracer(logger, secrets)
        _install_http_header_tracer(logger, secrets)
    name, website = _seed_amenity()
    site_url = args.url or website or _FALLBACK_SITE_URL
    # For this run only, the connect-time probe targets the same site that is mapped and scraped,
    # so the shape check is made on the page that matters. Production keeps FIRECRAWL_PROBE_URL
    # because no amenity URL exists yet when the gateway opens.
    settings = settings.model_copy(update={"firecrawl_probe_url": site_url})

    _section("INPUT STATE")
    print(
        json.dumps(
            {
                "seeded_amenity": name,
                "objective": _OBJECTIVE,
                "search_queries": list(_SEARCH_QUERIES),
                "site_url": site_url,
                "probe_url": settings.firecrawl_probe_url,
                "crawl_enabled": args.crawl,
                "crawl_limit": _CRAWL_LIMIT,
                "crawl_depth": _CRAWL_DEPTH,
            },
            indent=2,
        )
    )

    gateway = create_mcp_tool_gateway(settings)
    degraded = False
    try:
        await _stage_open(gateway, settings, collector)
        if not await _stage_search(gateway, collector):
            degraded = True
        mapped = await _stage_map(gateway, site_url, collector)
        if mapped is None:
            degraded = True
        # Scrape the first mapped page, or the site itself when the map is empty or failed.
        page_url = mapped.links[0].url if mapped is not None and mapped.links else site_url
        if not await _stage_scrape(gateway, page_url, collector):
            degraded = True
        # Batch-scrape the first few mapped pages (A4), or the site itself when the map is thin.
        batch_urls = (
            [link.url for link in mapped.links[:3]]
            if mapped is not None and mapped.links
            else [site_url]
        )
        if not await _stage_batch(gateway, batch_urls, collector):
            degraded = True
        if args.crawl and not await _stage_crawl(gateway, site_url, collector):
            degraded = True
        if args.v2a and not await _verify_v2a(gateway, collector):
            degraded = True
        if args.v2b and not await _verify_v2b(gateway, site_url, collector):
            degraded = True
    except McpGatewayError as exc:
        _print_records(collector)
        print(f"\nMcpGatewayError: {type(exc).__name__} stage={exc.stage} message={exc}")
        await gateway.aclose()
        return 1
    finally:
        _section("STAGE 6 — aclose")
        await gateway.aclose()
        await gateway.aclose()  # a second close is a no-op
        print("owner tasks ended; second aclose was a no-op")

    return 1 if degraded else 0


def main() -> None:
    sys.exit(asyncio.run(run_sample_mcp_gateway(sys.argv[1:])))


if __name__ == "__main__":
    main()
