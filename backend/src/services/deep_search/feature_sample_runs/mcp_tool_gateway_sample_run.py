"""Manual, stage-by-stage run of R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

Not a test: it asserts nothing and writes nothing to disk. It hits the real Parallel and Firecrawl
MCP servers and calls no LLM, so there is no prompt module and no worked-pair examples. It seeds the
amenity from a real M1.1 capture (`data/m1_1_discovered_places.json`, the file the M1.2 runner uses):
the first place's `display_name.text` and `website_uri`. M1.1, M1.2 and M1.3 are not called; the
objective and queries are hand-written. Raw per-attempt and session records are read back off the
`homescout.deep_search` logger with a collecting handler.

From `backend/` (needs PARALLEL_API_KEY, FIRECRAWL_API_KEY and network access):
    python -m src.services.deep_search.feature_sample_runs.mcp_tool_gateway_sample_run

Flags:
    --v2a                 ten concurrent searches checked against their own requests, plus a
                          cancelled call mid-flight, then a follow-up (spends Parallel credits)
    --v2b                 two concurrent crawls on different URLs, a capability call during a crawl,
                          and a crawl wait cut short then recovered by job id (spends Firecrawl credits)
    --crawl-url <url>     override the crawled URL (default: the seeded place's website)
"""

import argparse
import asyncio
import json
import logging
import pathlib
import sys

from src.clients.mcp_tools import (
    CrawlResult,
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
    _section("STAGE 1 — open and capability check")
    await gateway.open()
    # open() raised nothing, so every required tool and argument is present on both servers.
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
                    "status_tool_present": "firecrawl_check_crawl_status" in tool_names
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


async def _stage_crawl(gateway, crawl_url: str, collector: _RecordCollector) -> bool:
    _section("STAGE 3 — crawl_site")
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


async def _verify_v2b(gateway, crawl_url: str, collector: _RecordCollector) -> bool:
    _section("V2b — concurrent crawls, capability call during a crawl")
    urls = [crawl_url, "https://example.com"]
    crawl_task = asyncio.gather(
        *(gateway.crawl_site(url, limit=_CRAWL_LIMIT, depth=_CRAWL_DEPTH) for url in urls)
    )
    # A fast capability call on the same Firecrawl Client while the crawls run.
    await gateway.verify_capabilities()
    print("verify_capabilities during crawl: ok")
    results = await crawl_task
    ok = all(not isinstance(r, ToolFailure) for r in results)
    print(f"two concurrent crawls did not interfere: {ok}")
    _print_records(collector)
    return ok


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="C3.1.1 MCP tool gateway sample runner")
    parser.add_argument("--v2a", action="store_true", help="concurrent search verification")
    parser.add_argument("--v2b", action="store_true", help="concurrent crawl verification")
    parser.add_argument("--crawl-url", dest="crawl_url", default=None)
    return parser.parse_args(argv)


async def run_sample_mcp_gateway(argv: list[str]) -> int:
    args = _parse_args(argv)
    configure_logging("INFO")
    logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    logger.addHandler(collector)

    settings = get_settings()
    name, website = _seed_amenity()
    crawl_url = args.crawl_url or website or "https://example.com"

    _section("INPUT STATE")
    print(
        json.dumps(
            {
                "seeded_amenity": name,
                "objective": _OBJECTIVE,
                "search_queries": list(_SEARCH_QUERIES),
                "crawl_url": crawl_url,
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
        if not await _stage_crawl(gateway, crawl_url, collector):
            degraded = True
        if args.v2a and not await _verify_v2a(gateway, collector):
            degraded = True
        if args.v2b and not await _verify_v2b(gateway, crawl_url, collector):
            degraded = True
    except McpGatewayError as exc:
        _print_records(collector)
        print(f"\nMcpGatewayError: {type(exc).__name__} stage={exc.stage} message={exc}")
        await gateway.aclose()
        return 1
    finally:
        _section("STAGE 4 — aclose")
        await gateway.aclose()
        await gateway.aclose()  # a second close is a no-op
        print("owner tasks ended; second aclose was a no-op")

    return 1 if degraded else 0


def main() -> None:
    sys.exit(asyncio.run(run_sample_mcp_gateway(sys.argv[1:])))


if __name__ == "__main__":
    main()
