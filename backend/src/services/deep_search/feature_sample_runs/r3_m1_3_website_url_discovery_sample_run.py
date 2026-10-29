"""Manual, stage-by-stage run of `run_specific_metric_resolution`: R3.M1.3 discovery + R3.M1.4 phase 1.

Not a test: it asserts via prints and an exit code. It drives the real
stage methods on `SpecificMetricResolution` in sequence over dummy handoff state seeded as after
M1.3 (two `PredefinedMetricsRecord`s + their `discovered_places` + one eligible `CategoryMetricPlan`
with three real `MetricSpec`s). No earlier mechanism is called.

Two work items:
- Rijksmuseum: its Google website passes `official_url_gate` → NO discovery search; phase 1 runs
  with an official site, so its factual metrics get a `site:` query next to off-site queries.
- Museum Van Loon: empty Google website → one LIVE discovery `web_search` + a LIVE selection turn →
  a `discovered` URL or `none`; then phase 1 runs with whatever discovery found.
Three metrics per amenity: two factual (`museumkaart_free_entry`, `adult_ticket_price`) and one
experiential (`weekday_afternoon_crowding`, never host-scoped). None reuse the phase-1 prompt's
library worked example or the discovery prompt's examples.

LIVE: the C3.1.1 gateway `open()` + `tools/list`, one discovery search + two discovery LLM turns,
then per amenity one phase-1 LLM turn + one `web_search` per metric (+ at most one retry turn).
Expect about 7 billed searches plus any retries. A provider failure ends that amenity
(`resolution_call_failed`) and the run still reports it honestly.

OBJECT TRACE: `_ObjectWatcher` wraps the service's helpers at runtime (this file only; the service
code is untouched). Every watched call records its inputs (snapshotted before the call, so later
mutation of the shared message list cannot change them) and its output or raised error, tagged with
the amenity and turn. At the end, even when the run fails, the trace + seed inputs + final state
stores are appended as one section to `deep_search/sample_outputs.py` (or `--output PATH`).

From `backend/` (needs PARALLEL_API_KEY and FIRECRAWL_API_KEY for open() + searches;
OPENAI_API_KEY / GROQ_API_KEY for the LLM turns):
    stage by stage:  python -m src.services.deep_search.feature_sample_runs.r3_m1_3_website_url_discovery_sample_run
    full entry:      python -m src.services.deep_search.feature_sample_runs.r3_m1_3_website_url_discovery_sample_run --entry
    other dump file: ... --output path/to/file.py
"""

import asyncio
import contextvars
import dataclasses
import functools
import inspect
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from src.clients.llm_provider import create_structured_llm_caller
from src.clients.mcp_tools import create_mcp_tool_gateway
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import MetricResolutionProviderError
from src.exceptions.mcp import McpGatewayError
from src.services.deep_search.feature_prompts.phase1_web_search_instruction import (
    build_phase1_search_instruction,
)
from src.services.deep_search.feature_schemas.schemas import (
    AmenityPhase1Record,
    AmenitySearchState,
    CanonicalPlace,
    CategoryMetricPlan,
    GeoPoint,
    MetricResolutionSource,
    MetricSpec,
    PredefinedMetricsRecord,
)
from src.services.deep_search import specific_metric_resolution as smr_module
from src.services.deep_search.phase_tool_catalog import build_tool_catalog
from src.services.deep_search.specific_metric_resolution import (
    PHASE1_MAX_ATTEMPTS,
    SpecificMetricResolution,
    _CircuitBreaker,
)

_RULE = "=" * 78
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "sample_outputs.py"


# --------------------------------------------------------------------------------------------------
# Object trace: watch every object the run creates or uses, then append it to sample_outputs.py.
# --------------------------------------------------------------------------------------------------
def _to_jsonable(obj, _depth: int = 0):
    """Turn any run object into plain JSON (dataclass / pydantic / tuple-keyed dict / set / error)."""
    if _depth > 40:
        return repr(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, BaseException):
        out = {"error_type": type(obj).__name__, "message": str(obj)}
        for attr in ("stage", "cause"):
            if hasattr(obj, attr):
                out[attr] = _to_jsonable(getattr(obj, attr), _depth + 1)
        return out
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # Private fields (e.g. MetricsSourceContent._index) only duplicate public ones.
        return {
            f.name: _to_jsonable(getattr(obj, f.name), _depth + 1)
            for f in dataclasses.fields(obj)
            if not f.name.startswith("_")
        }
    if isinstance(obj, dict):
        return {_key(k): _to_jsonable(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        items = [_to_jsonable(v, _depth + 1) for v in obj]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True, default=str))
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v, _depth + 1) for v in obj]
    if hasattr(obj, "__dict__"):
        return {
            k: _to_jsonable(v, _depth + 1) for k, v in vars(obj).items() if not k.startswith("_")
        }
    return repr(obj)


def _key(key) -> str:
    """Dict keys as strings: `(1, 'rijks')` → `"1/rijks"`."""
    if isinstance(key, tuple):
        return "/".join(str(part) for part in key)
    return str(key)


_OMIT_CATALOG = "<omitted: see the build_tool_catalog events / runner tool_catalog in this trace>"

# (attribute name, args to replace by a short summary, args to snapshot again after the call)
# Module-level helpers the service calls by name (patched on the service module).
_WATCHED_MODULE_FUNCTIONS: tuple[tuple[str, dict, tuple[str, ...]], ...] = (
    ("official_url_gate", {}, ()),
    ("build_discovery_search_instruction", {}, ()),
    ("build_website_selection_instruction", {}, ()),
    ("_index_candidates", {}, ()),
    ("_resolve_verdict", {}, ()),
    ("build_tool_catalog", {}, ()),
    ("build_phase1_search_instruction", {}, ()),
    ("_new_ledger", {}, ()),
    ("guard_proposed_calls", {"catalog": _OMIT_CATALOG}, ()),
    ("prepare_admitted_calls", {}, ()),
    ("_admit_calls", {}, ()),
    ("_shape_web_search", {}, ()),
    ("_shape_not_executed", {}, ()),
    ("build_rejection_outcomes", {}, ()),
    ("_attribute_rejected_turn", {}, ("ledger",)),
    ("sanitize_replay_message", {}, ()),
    ("_shape_rejected", {}, ()),
    ("_apply_shaped", {}, ("row",)),
    ("_record_web_evidence", {}, ("store",)),
    ("_retry_eligible", {}, ()),
)
# Service methods (patched on the instance; the service calls them through `self.`).
_WATCHED_SERVICE_METHODS: tuple[tuple[str, dict, tuple[str, ...]], ...] = (
    ("_discovery_pre_pass", {"state": "<AmenitySearchState: see inputs / final_state>"}, ()),
    ("_discover_website_url", {}, ()),
    ("_run_amenity_pipeline", {"catalog": _OMIT_CATALOG}, ()),
    ("_phase1_loop", {"catalog": _OMIT_CATALOG}, ()),
    (
        "_run_phase1_turn",
        # The shared list is recorded in full by every llm.call_turn input and the final record.
        {"messages": lambda m: f"<{len(m)} messages: see the llm.call_turn input of this turn>",
         "catalog": _OMIT_CATALOG},
        ("ledger", "store"),
    ),
    ("_execute_web_searches", {}, ()),
    ("_sweep_pipeline_results", {}, ()),
)
_WATCHED_CALLER_METHODS = (("call_turn", {"tools": _OMIT_CATALOG}, ()), ("call_structured", {}, ()))
_WATCHED_GATEWAY_METHODS = (("get_tool_definitions", {}, ()), ("search_web", {}, ()))

_current_amenity: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sample_run_amenity", default=None
)
_current_turn: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "sample_run_turn", default=None
)


class _ObjectWatcher:
    """Wraps helpers at runtime and records every call's inputs and output as JSON events.

    Context (amenity, turn) lives in contextvars, so concurrent pipelines (`--entry`) are tagged
    correctly. `install()` fails fast, before any billed call, if a watched name no longer exists.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.notes: dict[str, object] = {}
        self.state: AmenitySearchState | None = None
        self.seed: dict | None = None
        self._restore: list[tuple[object, str, object, bool]] = []

    # ---- install / uninstall ---------------------------------------------------------------
    def install(self, service, caller, gateway) -> None:
        targets = [
            (smr_module, "service_module", _WATCHED_MODULE_FUNCTIONS),
            (service, "service", _WATCHED_SERVICE_METHODS),
            (caller, "llm", _WATCHED_CALLER_METHODS),
            (gateway, "gateway", _WATCHED_GATEWAY_METHODS),
        ]
        missing = [
            f"{prefix}.{name}"
            for target, prefix, specs in targets
            for name, _, _ in specs
            if not hasattr(target, name)
        ]
        if missing:
            raise RuntimeError(f"object watcher: names no longer exist: {missing}")
        for target, prefix, specs in targets:
            for name, summarize, after in specs:
                original = getattr(target, name)
                had_own = not inspect.ismodule(target) and name in vars(target)
                setattr(target, name, self._wrap(original, f"{prefix}.{name}", summarize, after))
                self._restore.append((target, name, original, had_own or inspect.ismodule(target)))

    def uninstall(self) -> None:
        for target, name, original, put_back in reversed(self._restore):
            if put_back:
                setattr(target, name, original)
            else:
                delattr(target, name)  # instance override removed → class method again
        self._restore.clear()

    def note(self, name: str, obj) -> None:
        """Record an object the runner itself builds (outside any watched call)."""
        self.notes[name] = _to_jsonable(obj)

    # ---- wrapping ----------------------------------------------------------------------------
    def _wrap(self, fn, name: str, summarize: dict, after: tuple[str, ...]):
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            signature = None

        def bind(args, kwargs) -> dict:
            if signature is None:
                return {"args": list(args), "kwargs": kwargs}
            try:
                bound = signature.bind(*args, **kwargs)
            except TypeError:
                return {"args": list(args), "kwargs": kwargs}
            return dict(bound.arguments)

        def snapshot_inputs(arguments: dict) -> dict:
            out = {}
            for arg, value in arguments.items():
                rule = summarize.get(arg)
                if rule is None:
                    out[arg] = _to_jsonable(value)
                else:
                    out[arg] = rule(value) if callable(rule) else rule
            return out

        def start(arguments: dict) -> dict:
            event = {
                "seq": len(self.events) + 1,
                "object": name,
                "amenity": _current_amenity.get(),
                "turn": _current_turn.get(),
                "at": datetime.now(timezone.utc).isoformat(),
                "inputs": snapshot_inputs(arguments),
            }
            self.events.append(event)  # appended at call start → events are in call order
            return event

        def finish(event: dict, arguments: dict, output=None, error=None) -> None:
            if error is not None:
                event["raised"] = _to_jsonable(error)
            else:
                event["output"] = _to_jsonable(output)
            if after:
                event["after_call"] = {
                    arg: _to_jsonable(arguments[arg]) for arg in after if arg in arguments
                }

        def context_tokens(arguments: dict) -> list:
            tokens = []
            work_item = arguments.get("work_item") or arguments.get("wi")
            if work_item is not None and hasattr(work_item, "place_id"):
                tokens.append((_current_amenity,
                               _current_amenity.set(f"{work_item.category_id}/{work_item.place_id}")))
            if "turn" in arguments and name.endswith("_run_phase1_turn"):
                tokens.append((_current_turn, _current_turn.set(arguments["turn"])))
            return tokens

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                arguments = bind(args, kwargs)
                tokens = context_tokens(arguments)
                event = start(arguments)
                try:
                    output = await fn(*args, **kwargs)
                except BaseException as exc:
                    finish(event, arguments, error=exc)
                    raise
                finally:
                    for var, token in reversed(tokens):
                        var.reset(token)
                finish(event, arguments, output=output)
                return output

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            arguments = bind(args, kwargs)
            event = start(arguments)
            try:
                output = fn(*args, **kwargs)
            except BaseException as exc:
                finish(event, arguments, error=exc)
                raise
            finish(event, arguments, output=output)
            return output

        return sync_wrapper

    # ---- dump --------------------------------------------------------------------------------
    def build_dump(self, *, mode: str, passed: bool, error: str | None, started_at: str) -> dict:
        state = self.state
        final_state = None
        if state is not None:
            final_state = {
                "official_gate_results": _to_jsonable(state.official_gate_results),
                "discovery_search_results": _to_jsonable(state.discovery_search_results),
                "website_search_results": _to_jsonable(state.website_search_results),
                "phase1_results": _to_jsonable(state.phase1_results),
            }
        return {
            "run": {
                "mode": mode,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "all_checkpoints_passed": passed,
                "error": error,
                "event_count": len(self.events),
            },
            "inputs": self.seed,
            "runner_objects": self.notes,
            "events": self.events,
            "final_state": final_state,
        }

    def append_to(self, path: Path, dump: dict) -> None:
        """Append one labelled section (same layout as the other sections in sample_outputs.py)."""
        run = dump["run"]
        header = (
            f"\n\n\n# {'=' * 78}\n"
            f"# R3.M1.3 + R3.M1.4 PHASE 1 - OBJECT TRACE ({run['mode']}, {run['started_at']})\n"
            f"# {'=' * 78}\n"
        )
        body = json.dumps(dump, ensure_ascii=False, indent=2)
        json.loads(body)  # never write a section that does not round-trip
        with path.open("a", encoding="utf-8") as handle:
            handle.write(header + body + "\n")


class _RecordCollector(logging.Handler):
    """Keeps the deep-search structured records so each stage can print its log trail."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []
        self._cursor = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except (json.JSONDecodeError, TypeError):
            pass

    def events(self, *names: str) -> list[dict]:
        return [r for r in self.records if r.get("event") in names]

    def new_events(self, *names: str) -> list[dict]:
        """Matching records emitted since the previous `new_events` call (one stage's trail)."""
        fresh = self.records[self._cursor:]
        self._cursor = len(self.records)
        return [r for r in fresh if r.get("event") in names]


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


def _print_records(records: list[dict]) -> None:
    for record in records:
        print(f"  log: {json.dumps(record, ensure_ascii=False)}")


def _rec(category_id, place_id, name, website, address) -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=category_id,
        taxonomy_node="museum",
        depth="specific_attributes",
        place_id=place_id,
        name=name,
        category=None,
        address=address,
        website=website,
        google_maps_uri=None,
        coordinates=None,
        opening_hours=None,
        contact_phone=None,
        rating=None,
        review_volume=None,
        price_level=None,
        reviews=None,
        routing={},
        transit=None,
    )


def _metrics() -> list[MetricSpec]:
    """Three real metric specs (two factual, one experiential), as Mechanism 6 would store them."""
    return [
        MetricSpec(
            label="museumkaart_free_entry",
            question="Is general admission free with a Dutch Museumkaart?",
            value_type="boolean",
            unit=None,
            enum_values=[],
            evidence_class="factual",
            resolution_source=MetricResolutionSource(
                web_target="museum admission or Museumkaart acceptance information",
                scrape_target="the museum's tickets / admission page",
            ),
            verification="an official ticketing page or Museumkaart listing states it explicitly",
            null_policy="unknown",
            band="specific_attributes",
        ),
        MetricSpec(
            label="adult_ticket_price",
            question="What is the standard adult admission price?",
            value_type="number_with_unit",
            unit="EUR",
            enum_values=[],
            evidence_class="factual",
            resolution_source=MetricResolutionSource(
                web_target="current adult ticket price",
                scrape_target="the museum's tickets / admission page",
            ),
            verification="a current official price for one adult ticket",
            null_policy="null",
            band="specific_attributes",
        ),
        MetricSpec(
            label="weekday_afternoon_crowding",
            question="How crowded is it on a typical weekday afternoon?",
            value_type="enum",
            unit=None,
            enum_values=["quiet", "moderate", "busy"],
            evidence_class="experiential",
            resolution_source=MetricResolutionSource(
                web_target="visitor accounts of crowds on weekday afternoons",
                review_target="visitor reviews mentioning crowds or queues",
            ),
            verification="several independent visitor accounts agree",
            null_policy="unknown",
            band="specific_attributes",
        ),
    ]


def _seed_state() -> AmenitySearchState:
    """Dummy handoff state as after M1.3: one gate-official museum + one declined (empty website)."""
    plan = CategoryMetricPlan(1, "museum", "specific_attributes", [], _metrics())
    place = CanonicalPlace("x", {})
    official = _rec(
        1,
        "rijks",
        "Rijksmuseum",
        "https://www.rijksmuseum.nl",
        "Museumstraat 1, 1071 XX Amsterdam, Netherlands",
    )
    declined = _rec(
        1,
        "vanloon",
        "Museum Van Loon",
        "",  # empty Google website → gate declines → live discovery
        "Keizersgracht 672, 1017 ET Amsterdam, Netherlands",
    )
    return AmenitySearchState(
        origin=GeoPoint(52.36, 4.885),
        radius_km=2.0,
        category_metric_plans=[plan],
        discovered_places={1: {"rijks": place, "vanloon": place}},
        predefined_records={1: {"rijks": official, "vanloon": declined}},
    )


def _print_conversation(messages: list[dict]) -> None:
    """Print the shared phase-1 conversation turn by turn (system text is printed separately)."""
    turn = 0
    for message in messages:
        role = message["role"]
        if role in ("system", "user"):
            continue
        if role == "assistant":
            turn += 1
            print(f"  -- turn {turn}: assistant proposed {len(message.get('tool_calls', []))} call(s)")
            for call in message.get("tool_calls", []):
                args = json.loads(call["function"]["arguments"])
                print(f"     {call['id']}: label={args.get('metric_label')!r} "
                      f"queries={args.get('search_queries')}")
        elif role == "tool":
            payload = json.loads(message["content"])
            extra = (f"hits={len(payload.get('hits', []))}" if payload["status"] != "failed"
                     else f"failure={payload.get('failure')!r}")
            print(f"     tool[{message['tool_call_id']}]: {payload['status']} "
                  f"label={payload.get('metric_label')!r} {extra}")


def _check_record(record: AmenityPhase1Record) -> list[str]:
    """Checkpoint failures for one record (empty list = passed)."""
    problems: list[str] = []
    if record.phase1 is None:
        return problems
    messages = record.phase1.messages
    call_ids = [c["id"] for m in messages if m["role"] == "assistant" for c in m.get("tool_calls", [])]
    tool_ids = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
    if sorted(call_ids) != sorted(tool_ids):
        problems.append("a tool call is unanswered or a tool message is orphaned")
    for label, row in record.phase1.metric_outcomes.items():
        if row.attempts_used > PHASE1_MAX_ATTEMPTS:
            problems.append(f"{label} used {row.attempts_used} attempts")
    return problems


def _print_records_summary(records: dict) -> bool:
    passed = True
    for key, record in records.items():
        print(f"  ({key[0]}, {key[1]}): outcome={record.outcome} "
              f"failed_stage={record.failed_stage} failed_cause={record.failed_cause}")
        if record.phase1 is not None:
            p1 = record.phase1
            print(f"     turns_run={p1.turns_run} uncovered={list(p1.uncovered_labels)} "
                  f"evidence_items={len(p1.metrics_source_content.items)}")
            first_label = next(iter(p1.metric_outcomes), None)
            for label, row in p1.metric_outcomes.items():
                items = p1.metrics_source_content.items_for(label)
                print(f"     {label}: status={row.status} attempts={row.attempts_used} "
                      f"failure_kind={row.failure_kind} evidence={len(items)}")
                if label == first_label:
                    # Full evidence for the first metric only: every item's shaped_text (title +
                    # excerpts), exactly as the LLM saw it in the tool message.
                    for n, item in enumerate(items, start=1):
                        print(f"        [{n}] {item.url}")
                        print(f"            evidence_id={item.evidence_id}  "
                              f"labels={sorted(item.metric_labels)}")
                        for line in item.shaped_text.splitlines():
                            print(f"            | {line}")
                    continue
                for item in items[:3]:
                    print(f"        - {item.url}  | {item.shaped_text.splitlines()[0][:70]!r}")
        problems = _check_record(record)
        for problem in problems:
            print(f"     CHECKPOINT FAILED: {problem}")
        passed = passed and not problems
    return passed


def _seed_inputs(state: AmenitySearchState) -> dict:
    return {
        "origin": _to_jsonable(state.origin),
        "radius_km": state.radius_km,
        "category_metric_plans": _to_jsonable(state.category_metric_plans),
        "predefined_records": _to_jsonable(state.predefined_records),
    }


async def _run_stage_by_stage(service, gateway, collector, watcher: _ObjectWatcher) -> bool:
    state = _seed_state()
    watcher.state = state
    watcher.seed = _seed_inputs(state)
    batch_id = uuid4().hex
    run_id = uuid4().hex
    breaker = _CircuitBreaker(threshold=get_settings().metric_resolution_breaker_threshold)
    watcher.note("ids", {"batch_id": batch_id, "run_id": run_id})

    _section("STAGE: seed state (as after M1.3)")
    for category_id, places in state.predefined_records.items():
        for place_id, rec in places.items():
            print(f"  ({category_id}, {place_id}): name={rec.name!r} website={rec.website!r}")
    print(f"  metrics: {[(m.label, m.evidence_class) for m in state.category_metric_plans[0].specific_metrics]}")
    print(f"  breaker: threshold={breaker.threshold} counter={breaker.counter} open={breaker.open}")

    _section("STEP 0: open gateway + capture raw tool definitions")
    await gateway.open()
    raw_tool_definitions = gateway.get_tool_definitions()
    _print_records(collector.new_events("mcp.tools_listed"))
    print(f"  servers={sorted(raw_tool_definitions)}  "
          f"parallel_tools={sorted(raw_tool_definitions.get('parallel', {}))}")

    _section("STEP 1: build_plan_index")
    plan_index = service._build_plan_index(state)
    watcher.note("plan_index", plan_index)
    print(f"  plan_index keys: {sorted(plan_index)}")

    _section("STEP 2: derive work items (RC7)")
    work_items = service._derive_work_items(state, plan_index)
    watcher.note("work_items", work_items)
    for wi in work_items:
        print(f"  work item: ({wi.category_id}, {wi.place_id})  node={wi.taxonomy_node}  "
              f"metrics={len(wi.specific_metrics)}")

    _section("STEP 3 / STAGE 0: official_url_gate pre-pass (all items)")
    declined = service._discovery_pre_pass(state, work_items, batch_id)
    _print_records(collector.new_events("r3m1_3.object_finalized", "r3m1_3.discovery_degraded"))
    for key, gate in state.official_gate_results.items():
        print(f"  gate ({key[0]}, {key[1]}): verdict={gate.verdict} "
              f"reason={gate.reason_code} sld={gate.sld} compact_name={gate.compact_name}")
    print(f"  declined (go to Stage 1): {[(w.category_id, w.place_id) for w in declined]}")

    for wi in declined:
        key = (wi.category_id, wi.place_id)
        rec = state.predefined_records[wi.category_id][wi.place_id]
        _section(f"STEP 3 / STAGE 1: discovery for ({key[0]}, {key[1]}) — {rec.name!r}")
        verdict, telemetry = await service._discover_website_url(
            wi, rec, raw_tool_definitions, batch_id, breaker=breaker
        )
        _print_records(collector.new_events(
            "r3m1_1.guard_decision", "llm_provider.attempt", "llm_provider.rejected",
            "mcp.call_attempt_failed", "r3m1_3.object_finalized", "r3m1_3.discovery_degraded",
            "r3m1_5.breaker_opened",
        ))
        state.website_search_results[key] = verdict  # the runner plays the STEP-3 merge
        if telemetry is not None:
            state.discovery_search_results[key] = telemetry
            for candidate in telemetry.candidates:
                print(f"    {candidate.id}: {candidate.url}  | {candidate.title}")
        print(f"  verdict: origin={verdict.website_origin} url={verdict.website_url!r}")

    _section("STEP 3 RESULT: website_search_results (RC8)")
    for key, verdict in state.website_search_results.items():
        print(f"  ({key[0]}, {key[1]}): {verdict.website_origin} {verdict.website_url!r}")
    rc8 = all((wi.category_id, wi.place_id) in state.website_search_results for wi in work_items)
    print(f"  RC8 (every work item has a verdict): {rc8}")
    print(f"  breaker: counter={breaker.counter} open={breaker.open}")

    _section("STEP 4: build the metric_web_search catalog (R3.M1.1)")
    catalog = build_tool_catalog(raw_tool_definitions, "metric_web_search")
    watcher.note("tool_catalog", catalog)
    params = catalog[0]["function"]["parameters"]
    print(f"  tool={catalog[0]['function']['name']}  fields={sorted(params.get('properties', {}))}  "
          f"required={params.get('required')}")
    collector.new_events()  # drop the catalog log line from the next stage's trail

    records: dict = {}
    for wi in work_items:
        key = (wi.category_id, wi.place_id)
        rec = state.predefined_records[wi.category_id][wi.place_id]
        website = state.website_search_results[key]
        _section(f"STEP 4 / PHASE 1: ({key[0]}, {key[1]}) — {rec.name!r}  site={website.website_url!r}")
        instruction = build_phase1_search_instruction(
            rec.name, rec.address, wi.taxonomy_node, website.website_url, wi.specific_metrics
        )
        print("  instruction (METRICS block):")
        for line in instruction.split("METRICS\n", 1)[1].splitlines():
            print(f"    {line}")
        # The real pipeline: catch → _phase1_loop → turn 1 → (retry turn) → coverage.
        record = await service._run_amenity_pipeline(
            wi, rec, website, catalog, breaker, run_id
        )
        _print_records(collector.new_events(
            "llm_provider.attempt", "llm_provider.rejected", "r3m1_1.guard_decision",
            "mcp.call_attempt_failed", "r3m1_4.phase1_turn", "r3m1_4.guard_rejected",
            "r3m1_4.call_not_executed", "r3m1_4.search_failed", "r3m1_4.metrics_uncovered",
            "r3m1_4.phase1_done", "r3m1_4.pipeline_provider_failed", "r3m1_5.breaker_opened",
        ))
        if record.phase1 is not None:
            print("  conversation:")
            _print_conversation(record.phase1.messages)
        records[key] = record

    _section("STEP 5: sweep + write state.phase1_results + run-level check")
    swept = service._sweep_pipeline_results(work_items, list(records.values()), breaker, run_id)
    state.phase1_results.update(swept)
    _print_records(collector.new_events("r3m1_4.pipelines_done"))
    passed = _print_records_summary(state.phase1_results)
    try:
        service._raise_if_no_pipeline_completed(swept, breaker)
        print("  run-level raise: not triggered")
    except MetricResolutionProviderError as exc:
        print(f"  run-level raise: {type(exc).__name__} stage={exc.stage} cause={exc.cause}")
        passed = False
    print(f"  breaker: counter={breaker.counter} open={breaker.open}")
    covered = all((wi.category_id, wi.place_id) in state.phase1_results for wi in work_items)
    print(f"  every work item has an AmenityPhase1Record: {covered}")
    return passed and rc8 and covered


async def _run_entry(service, collector, watcher: _ObjectWatcher) -> bool:
    state = _seed_state()
    watcher.state = state
    watcher.seed = _seed_inputs(state)
    _section("ENTRY: run_specific_metric_resolution(state)  (one call, STEP 0-5)")
    try:
        await service.run_specific_metric_resolution(state)
        raised = None
    except MetricResolutionProviderError as exc:
        raised = exc
    _print_records(collector.events(
        "r3m1_3.discovery_batch_done", "r3m1_4.pipelines_start", "r3m1_4.phase1_turn",
        "r3m1_4.phase1_done", "r3m1_4.pipeline_provider_failed", "r3m1_4.pipelines_done",
        "r3m1_5.breaker_opened",
    ))
    _section("ENTRY RESULT: stores")
    for key, verdict in state.website_search_results.items():
        print(f"  website ({key[0]}, {key[1]}): {verdict.website_origin} {verdict.website_url!r}")
    passed = _print_records_summary(state.phase1_results)
    if raised is not None:
        print(f"  run-level raise: {type(raised).__name__} stage={raised.stage} cause={raised.cause}")
        return False
    return passed and len(state.phase1_results) == 2


async def run(argv: list[str]) -> int:
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
    service = SpecificMetricResolution(
        tool_gateway=gateway,
        llm_caller=caller,
        owns_caller=False,
        breaker_threshold=settings.metric_resolution_breaker_threshold,
    )
    output_path = _output_path(argv)
    mode = "entry" if "--entry" in argv else "stage_by_stage"
    started_at = datetime.now(timezone.utc).isoformat()
    watcher = _ObjectWatcher()
    # Installed before open(): a renamed helper fails here, before any billed call.
    watcher.install(service, caller, gateway)
    passed = False
    error: str | None = None
    try:
        if mode == "entry":
            passed = await _run_entry(service, collector, watcher)
        else:
            passed = await _run_stage_by_stage(service, gateway, collector, watcher)
    except McpGatewayError as exc:
        error = f"{type(exc).__name__} stage={exc.stage}: {exc}"
        _section("FAILED — MCP gateway")
        print(f"exception: {type(exc).__name__}  stage={exc.stage}  message={exc}")
        return 1
    except MetricResolutionProviderError as exc:
        error = f"{type(exc).__name__} stage={exc.stage} cause={exc.cause}: {exc}"
        _section("FAILED — provider")
        print(f"exception: {type(exc).__name__}  stage={exc.stage}  cause={exc.cause}  message={exc}")
        return 1
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _section("TEARDOWN — gateway + caller close")
        await gateway.aclose()
        await caller.aclose()
        print("gateway and caller closed")
        watcher.uninstall()
        _section("OBJECT TRACE — append to sample outputs")
        try:
            dump = watcher.build_dump(mode=mode, passed=passed, error=error, started_at=started_at)
            watcher.append_to(output_path, dump)
            print(f"appended {len(watcher.events)} events to {output_path}")
        except Exception as dump_exc:  # a dump bug must never hide the run's own result
            print(f"OBJECT TRACE NOT WRITTEN: {type(dump_exc).__name__}: {dump_exc}")

    _section("RESULT")
    print(f"all checkpoints passed: {passed}")
    return 0 if passed else 1


def _output_path(argv: list[str]) -> Path:
    if "--output" in argv:
        index = argv.index("--output")
        if index + 1 >= len(argv):
            raise SystemExit("--output needs a file path")
        return Path(argv[index + 1]).resolve()
    return DEFAULT_OUTPUT_PATH


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
