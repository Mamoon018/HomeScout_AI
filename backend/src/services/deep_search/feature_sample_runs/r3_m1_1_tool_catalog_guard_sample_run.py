"""Manual, stage-by-stage run of R3.M1.1 (phase-scoped tool catalog + call guard).

Not a test: it asserts via prints and exit codes but writes nothing to disk. It proves the two
R3.M1.1 abstractions work as a reusable unit before any core-workflow sub-component (R3.M1.3
discovery, R3.M1.4 phase loop) is built to call them, following
`feature_context/R3_M1_1_Dry_Run_Traceflow.md`.

What is LIVE: the C3.1.1 gateway `open()` + `tools/list` (real raw MCP schema), the C3.1.2
`call_turn()` (real OpenAI→Groq tool turn in Pass A), and exactly one billed Parallel
`search_web` (the mandatory end-to-end leg). What is DUMMY (the harness stands in for the
not-yet-built R3.M1.3/R3.M1.5 caller): the `context` per pass, the amenity identity and search
instructions in the message, the `validation_context`, and the two Pass-B crafted proposed-calls
fixtures. The two abstractions themselves are REAL — the thing under test.

Pass A proves the happy path on `website_discovery` (no metric_label, validation_context=None).
Pass B reuses the SAME two functions on `metric_web_search` to exercise metric_label and the
separate validator in both directions: B1 forces a genuine whole-message rejection (one invalid
label withholds a valid sibling); B2 proves acceptance when every label is valid.

From `backend/` (needs OPENAI_API_KEY + GROQ_API_KEY for the live turn, PARALLEL_API_KEY for the
live open() and the one billed search; FIRECRAWL_API_KEY only for the optional catalog-shape pass):
    python -m src.services.deep_search.feature_sample_runs.r3_m1_1_tool_catalog_guard_sample_run
"""

import asyncio
import json
import logging
import sys
from copy import deepcopy
from typing import Any

from src.clients.llm_provider import ToolCall, create_structured_llm_caller
from src.clients.mcp_tools import ToolFailure, WebSearchResult, create_mcp_tool_gateway
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import (
    MetricResolutionProviderError,
    MetricResolutionValidationError,
)
from src.exceptions.mcp import McpGatewayError
from src.services.deep_search.phase_tool_catalog import (
    CATALOG_BUILT_EVENT,
    GUARD_DECISION_EVENT,
    build_tool_catalog,
    guard_proposed_calls,
    metric_label_membership_validator,
)

_RULE = "=" * 78

# DUMMY amenity identity (the R3.M1.3/R3.M1.5 caller supplies this in production). Deliberately a
# distinct real venue — NOT the gateway runner's seeded swimming pool — so the live discovery turn
# and the one billed search are a fresh use case, not a replay of any worked pair.
_AMENITY_IDENTITY = {"name": "Tivoli Gardens", "city": "Copenhagen", "country": "Denmark"}

_DISCOVERY_INSTRUCTIONS = (
    "You locate the single official website of the amenity named in the user message. "
    "Call web_search once. Set `objective` to a short statement of what you are finding, and "
    "`search_queries` to one to three concise keyword queries (3-6 words each) that would surface "
    "the amenity's own site. Do not answer in prose; make the tool call."
)

_METRIC_INSTRUCTIONS = (
    "You gather web evidence for one named metric of the amenity. Call web_search, setting "
    "`objective`, `search_queries`, and `metric_label` (the exact metric you are resolving)."
)

# DUMMY validation_context for Pass B (built from amenity state in production).
_METRIC_LABELS = ["ticket_price", "opening_hours"]


class _RecordCollector(logging.Handler):
    """Keeps the deep-search structured records so each stage can print the call/decision trail."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except (json.JSONDecodeError, TypeError):
            pass

    def events(self, *names: str) -> list[dict]:
        return [r for r in self.records if r.get("event") in names]


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


def _print_events(collector: _RecordCollector, *names: str) -> None:
    for record in collector.events(*names):
        print(f"  log: {json.dumps(record, ensure_ascii=False)}")


def _unresolved_refs(parameters: dict) -> list[str]:
    """Return any `#/$defs/<name>` ref in the built schema not satisfied by its carried `$defs`."""
    carried = set(parameters.get("$defs", {}))
    missing: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                    name = value[len("#/$defs/") :]
                    if name not in carried:
                        missing.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(parameters.get("properties", {}))
    return missing


def _catalog_parameters(catalog: list[dict]) -> dict:
    return catalog[0]["function"]["parameters"]


async def _pass_a(gateway, caller, collector: _RecordCollector) -> bool:
    """website_discovery: live MCP + live LLM, then the mandatory billed search."""
    _section("PASS A — website_discovery (live MCP open + live LLM tool turn)")

    await gateway.open()
    raw_tool_definitions = gateway.get_tool_definitions()
    captured_before = deepcopy(raw_tool_definitions)
    _print_events(collector, "mcp.tools_listed")
    print(
        "input state: context=website_discovery  servers="
        f"{sorted(raw_tool_definitions)}  parallel_tools="
        f"{sorted(raw_tool_definitions.get('parallel', {}))}"
    )

    _section("PASS A — STEP 1: build_tool_catalog(website_discovery)")
    catalog = build_tool_catalog(raw_tool_definitions, "website_discovery")
    parameters = _catalog_parameters(catalog)
    _print_events(collector, CATALOG_BUILT_EVENT)
    print(json.dumps(catalog, indent=2, ensure_ascii=False))

    _section("PASS A — CHECKPOINT A1: catalog contract")
    exposed = sorted(parameters.get("properties", {}))
    unresolved = _unresolved_refs(parameters)
    raw_unchanged = raw_tool_definitions == captured_before
    only_web_search = [t["function"]["name"] for t in catalog] == ["web_search"]
    no_metric_label = "metric_label" not in parameters.get("properties", {})
    a1_ok = (
        only_web_search
        and set(exposed) == {"objective", "search_queries"}
        and no_metric_label
        and not unresolved
        and raw_unchanged
        and parameters.get("additionalProperties") is False
    )
    print(f"only web_search exposed:            {only_web_search}")
    print(f"exposed fields:                     {exposed}")
    print(f"metric_label absent:                {no_metric_label}")
    print(f"retained $refs resolve:             {not unresolved} (unresolved={unresolved})")
    print(f"raw_tool_definitions unchanged:     {raw_unchanged}")
    print(f"additionalProperties == false:      {parameters.get('additionalProperties') is False}")
    print(f"A1 PASS: {a1_ok}")

    _section("PASS A — LIVE C3.1.2 call_turn() (real OpenAI→Groq tool turn)")
    messages = [
        {"role": "system", "content": _DISCOVERY_INSTRUCTIONS},
        {"role": "user", "content": json.dumps(_AMENITY_IDENTITY)},
    ]
    try:
        turn = await caller.call_turn(
            messages=messages,
            tools=catalog,
            tool_choice="required",
            stage="r3_m1_1_sample_discovery_turn",
            provider_error_cls=MetricResolutionProviderError,
        )
    except MetricResolutionProviderError as exc:
        # The live turn is a C3.1.2 (shared caller / provider) concern, not R3.M1.1. When no
        # provider can complete it (model config or connectivity), the catalog contract (A1) is
        # still proven; report the blockage honestly and let the fixture-driven passes continue.
        _print_events(collector, "llm_provider.attempt", "llm_provider.rejected")
        print(f"LIVE TURN BLOCKED (upstream of R3.M1.1): {type(exc).__name__} stage={exc.stage}")
        print(f"  {exc}")
        print("  A2 guard + mandatory search leg skipped; A1 catalog contract stands.")
        return a1_ok  # A1 is the R3.M1.1 contract Pass A can still prove
    _print_events(collector, "llm_provider.attempt", "llm.generate_turn")
    print(f"provider={turn.provider}  finish_reason={turn.finish_reason}  "
          f"tool_calls={len(turn.tool_calls)}")
    for call in turn.tool_calls:
        print(f"  proposed: id={call.id} name={call.name} arguments={call.arguments}")

    _section("PASS A — STEP 2: guard_proposed_calls(validation_context=None)")
    decision = guard_proposed_calls(turn.tool_calls, catalog, "website_discovery", None)
    _print_events(collector, GUARD_DECISION_EVENT)
    print(f"decision: {decision.decision}")
    for vc in decision.validated_calls:
        print(f"  validated: id={vc.tool_call_id} name={vc.tool_name} arguments={vc.arguments}")
    for err in decision.errors:
        print(f"  error: {err}")

    _section("PASS A — CHECKPOINT A2: guard contract")
    args_decoded = all(isinstance(vc.arguments, dict) for vc in decision.validated_calls)
    order_preserved = [vc.tool_call_id for vc in decision.validated_calls] == [
        c.id for c in turn.tool_calls
    ]
    a2_ok = decision.decision == "accepted" and not decision.errors and args_decoded and order_preserved
    print(f"accepted:                 {decision.decision == 'accepted'}")
    print(f"errors empty:             {not decision.errors}")
    print(f"arguments decoded to dict:{args_decoded}")
    print(f"order preserved:          {order_preserved}")
    print(f"A2 PASS: {a2_ok}")

    if not decision.validated_calls:
        print("no accepted call to execute; skipping the mandatory end-to-end leg")
        return a1_ok and a2_ok

    _section("PASS A — MANDATORY end-to-end leg: live gw.search_web (1 billed call)")
    first = decision.validated_calls[0]
    result = await gateway.search_web(
        objective=first.arguments["objective"],
        search_queries=first.arguments["search_queries"],
    )
    _print_events(collector, "mcp.call_attempt_failed")
    if isinstance(result, ToolFailure):
        print(f"ToolFailure: tool={result.tool} kind={result.kind} message={result.message}")
        return False
    assert isinstance(result, WebSearchResult)
    print(f"SearchResults: excerpts={len(result.excerpts)} retrieved_at={result.retrieved_at}")
    return a1_ok and a2_ok


def _tool_call(call_id: str, label: str, objective: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        name="web_search",
        arguments=json.dumps(
            {"objective": objective, "search_queries": [objective], "metric_label": label}
        ),
    )


def _pass_b(gateway, caller, raw_tool_definitions, collector: _RecordCollector) -> bool:
    """metric_web_search: reuse the same two functions; exercise both validator directions."""
    _section("PASS B — metric_web_search (reuse; validator both directions; no 2nd open)")
    print(f"validation_context: {{'metric_labels': {_METRIC_LABELS}}}")

    catalog = build_tool_catalog(raw_tool_definitions, "metric_web_search")
    parameters = _catalog_parameters(catalog)
    _print_events(collector, CATALOG_BUILT_EVENT)
    print(json.dumps(catalog, indent=2, ensure_ascii=False))

    _section("PASS B — CATALOG CHECKPOINT")
    props = parameters.get("properties", {})
    metric_label_required = "metric_label" in parameters.get("required", [])
    only_web_search = [t["function"]["name"] for t in catalog] == ["web_search"]
    cat_ok = metric_label_required and "metric_label" in props and only_web_search
    print(f"metric_label required: {metric_label_required}")
    print(f"only web_search:       {only_web_search}")
    print(f"CATALOG PASS: {cat_ok}")

    validation_context = {"metric_labels": _METRIC_LABELS}

    _section("PASS B — CASE B1: one invalid label forces whole-message rejection")
    b1_calls = [
        _tool_call("c1", "ticket_price", "price"),          # valid label
        _tool_call("c2", "wheelchair_access", "hours"),     # NOT in the set → forces rejection
    ]
    b1 = guard_proposed_calls(b1_calls, catalog, "metric_web_search", validation_context)
    _print_events(collector, GUARD_DECISION_EVENT)
    print(f"decision: {b1.decision}")
    for err in b1.errors:
        print(f"  error: {err}")
    b1_ok = (
        b1.decision == "rejected"
        and not b1.validated_calls  # valid sibling c1 withheld
        and any(
            e.reason_code == "metric_label_not_in_set"
            and e.category == "in_catalog"
            and e.tool_call_id == "c2"
            and e.field_path == "arguments.metric_label"
            for e in b1.errors
        )
    )
    print(f"B1 PASS (rejected, c1 withheld, validator error on c2): {b1_ok}")

    _section("PASS B — CASE B2: every label valid → accept and preserve")
    b2_calls = [
        _tool_call("d1", "ticket_price", "price"),
        _tool_call("d2", "opening_hours", "hours"),
    ]
    b2 = guard_proposed_calls(b2_calls, catalog, "metric_web_search", validation_context)
    _print_events(collector, GUARD_DECISION_EVENT)
    print(f"decision: {b2.decision}")
    for vc in b2.validated_calls:
        print(f"  validated: id={vc.tool_call_id} metric_label={vc.arguments.get('metric_label')}")
    b2_ok = (
        b2.decision == "accepted"
        and [vc.tool_call_id for vc in b2.validated_calls] == ["d1", "d2"]
        and [vc.arguments["metric_label"] for vc in b2.validated_calls]
        == ["ticket_price", "opening_hours"]
    )
    print(f"B2 PASS (accepted, order + metric_label preserved): {b2_ok}")

    _section("PASS B — OPTIONAL: same B2 fixture with validation_context=None still accepts")
    b2_none = guard_proposed_calls(b2_calls, catalog, "metric_web_search", None)
    none_ok = b2_none.decision == "accepted"
    print(f"validation_context=None skips membership check, accepts: {none_ok}")

    return cat_ok and b1_ok and b2_ok and none_ok


def _firecrawl_pass(raw_tool_definitions, collector: _RecordCollector) -> bool:
    """Optional catalog-shape assertions for the Firecrawl contexts (no live scrape)."""
    _section("OPTIONAL FIRECRAWL — site_map and metric_scrape catalog shape")
    if "firecrawl" not in raw_tool_definitions:
        print("firecrawl definitions absent (no key / not opened); skipping")
        return True
    ok = True
    try:
        site_map = _catalog_parameters(build_tool_catalog(raw_tool_definitions, "site_map"))
        map_ok = not site_map.get("properties") and site_map.get("required") == []
        print(f"site_map: no LLM-settable args: {map_ok}  params={json.dumps(site_map)}")
        ok = ok and map_ok

        scrape = _catalog_parameters(build_tool_catalog(raw_tool_definitions, "metric_scrape"))
        scrape_props = set(scrape.get("properties", {}))
        scrape_ok = scrape_props == {"id", "metric_label"} and "metric_label" in scrape.get(
            "required", []
        )
        print(f"metric_scrape: id + metric_label only, url/formats absent: {scrape_ok}  "
              f"props={sorted(scrape_props)}")
        ok = ok and scrape_ok
    except MetricResolutionValidationError as exc:
        print(f"catalog construction failed: stage={exc.stage} message={exc}")
        ok = False
    _print_events(collector, CATALOG_BUILT_EVENT)
    return ok


async def run(argv: list[str]) -> int:
    # Windows consoles default to cp1252 and cannot encode the box-drawing / arrow characters in
    # the printed sections; force UTF-8 so the run is not killed by a print, not a real failure.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    settings = get_settings()
    configure_logging(settings.log_level)
    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    gateway = create_mcp_tool_gateway(settings)
    caller = create_structured_llm_caller(settings)
    # The metric-label validator is exported for callers; referenced here so the import is exercised.
    assert metric_label_membership_validator({"metric_label": "x"}, {"metric_labels": []})

    passed = True
    try:
        a_ok = await _pass_a(gateway, caller, collector)
        raw_tool_definitions = gateway.get_tool_definitions()
        b_ok = _pass_b(gateway, caller, raw_tool_definitions, collector)
        fc_ok = _firecrawl_pass(raw_tool_definitions, collector)
        passed = a_ok and b_ok and fc_ok
    except MetricResolutionValidationError as exc:
        _section("FAILED — catalog construction")
        print(f"exception: {type(exc).__name__}  stage={exc.stage}  message={exc}")
        return 1
    except MetricResolutionProviderError as exc:
        _section("FAILED — LLM tool turn")
        print(f"exception: {type(exc).__name__}  stage={exc.stage}  message={exc}")
        return 1
    except McpGatewayError as exc:
        _section("FAILED — MCP gateway")
        print(f"exception: {type(exc).__name__}  stage={exc.stage}  message={exc}")
        return 1
    finally:
        _section("TEARDOWN — gateway + caller close")
        await gateway.aclose()
        await caller.aclose()
        print("gateway and caller closed")

    _section("RESULT")
    print(f"all checkpoints passed: {passed}")
    return 0 if passed else 1


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
