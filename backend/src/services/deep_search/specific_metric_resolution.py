"""Responsibility 3 — Specific Metric Resolution.

This module holds the `SpecificMetricResolution` responsibility class. Its entry method
`run_specific_metric_resolution` is being built sub-component by sub-component, following
`feature_context/R3_Specific_Metric_Resolution_spec.md` and `feature_context/R3_M1_Traceflow.md`.

**Built so far: through STEP 5 with phase 1 only (R3.M1.4 step 1).** `run_specific_metric_resolution`
opens the gateway, builds `plan_index` (STEP 1), derives the eligible work items (STEP 2, RC7), runs
the R3.M1.3 discovery batch (STEP 3) to populate `state.website_search_results` /
`state.discovery_search_results` / `state.official_gate_results`, runs one amenity pipeline per work
item (STEP 4; the pipeline is the R3.M1.4 Phase-1 Loop alone for now), sweeps the results (STEP 5),
writes them to the TEMPORARY `state.phase1_results`, then closes the gateway. A run-scoped circuit
breaker (R3.M1.5) is shared by discovery and the pipelines. **Not yet built:** triage, phase 2, R3.M2
resolution and STEP 6 combine, so `state.amenity_records` is still `None` after this partial run.

R3.M1.4 Phase-1 Loop, per amenity: turn 1 asks the LLM for one `web_search` per metric (all metrics,
each tagged `metric_label`); the app owns the budget (one search + one retry per metric), runs the
admitted searches together, shapes every call into exactly one `ok` / `empty` / `failed` tool message
(R3.M1.2), and records each hit of an `ok` result into the amenity's `metrics_source_content`. If any
metric is retry-eligible (`failed` or guard-rejected, retry unused), ONE retry turn runs on the same
shared conversation; otherwise phase 1 ends without another LLM call. A provider-chain failure ends
the amenity (evidence discarded, `resolution_call_failed`); a tool failure never does.

R3.M1.3 itself is a two-stage decision per work item (traceflow Part 3 / 3a):
- **Stage 0** — a synchronous pre-pass over ALL work items running the deterministic
  `official_url_gate` (`official_url_gate.py`): a `google` verdict is written immediately; a
  declined item falls to Stage 1. Both verdicts are recorded to `state.official_gate_results`.
- **Stage 1** — for the declined subset only, concurrently behind a hard barrier: one LLM-built
  `web_search` (C3.1.2 `call_turn` + R3.M1.1 catalog/guard + C3.1.1 `search_web`), candidate
  id-indirection, then a structured selection turn (C3.1.2 `call_structured`) that resolves to a
  `discovered` URL or `none`. The LLM never emits a URL. Every failure degrades to `none` (D5).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar
from uuid import uuid4

from pydantic import ValidationError

from src.clients.llm_provider import (
    StructuredLLMCaller,
    create_structured_llm_caller,
)
from src.clients.mcp_tools import (
    SEARCH_CONCURRENCY,
    RawToolDefinitions,
    ToolFailure,
    ToolGateway,
    WebSearchResult,
    create_mcp_tool_gateway,
)
from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import (
    MetricResolutionProviderError,
    MetricResolutionValidationError,
    ProviderFailureCause,
)
from src.services.deep_search.feature_prompts.phase1_web_search_instruction import (
    USER_TURN_CONTENT as PHASE1_USER_TURN_CONTENT,
)
from src.services.deep_search.feature_prompts.phase1_web_search_instruction import (
    build_phase1_search_instruction,
)
from src.services.deep_search.feature_prompts.website_discovery_instruction import (
    build_discovery_search_instruction,
    build_website_selection_instruction,
)
from src.services.deep_search.feature_schemas.schemas import (
    WEBSITE_SELECTION_SCHEMA_NAME,
    AmenityPhase1Record,
    AmenitySearchState,
    CategoryMetricPlan,
    DepthLevel,
    DiscoveryCandidate,
    DiscoverySearchRecord,
    MetricSearchOutcome,
    MetricSearchStatus,
    MetricsSourceContent,
    MetricSpec,
    OfficialGateRecord,
    Phase1Result,
    PredefinedMetricsRecord,
    WebsiteSearchResult,
    WebsiteSelectionResult,
    website_selection_json_schema,
)
from src.services.deep_search.official_url_gate import official_url_gate
from src.services.deep_search.phase_tool_catalog import (
    PreparedCall,
    RejectedCallOutcome,
    build_rejection_outcomes,
    build_tool_catalog,
    guard_proposed_calls,
    prepare_admitted_calls,
    sanitize_replay_message,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# The fan-out bound for the Stage-1 discovery batch. Discovery runs under the Parallel search pool,
# so the number of in-flight discovery coroutines is capped to the same width the gateway allows
# for `web_search` (C3.1.1 `SEARCH_CONCURRENCY`); the gateway's own per-server semaphore + reactive
# 429 handling back it. The barrier's latency scales with the declined subset, not N.
DISCOVERY_CONCURRENCY = SEARCH_CONCURRENCY

# R3.M1.3 log events (threaded by batch_id + the (category_id, place_id) key).
DISCOVERY_BATCH_START_EVENT = "r3m1_3.discovery_batch_start"
DISCOVERY_PRE_PASS_DONE_EVENT = "r3m1_3.pre_pass_done"
DISCOVERY_DEGRADED_EVENT = "r3m1_3.discovery_degraded"
DISCOVERY_RESOLVED_EVENT = "r3m1_3.discovery_resolved"
DISCOVERY_BATCH_DONE_EVENT = "r3m1_3.discovery_batch_done"
# Every R3.M1.3-created object (the Stage-0 gate record, the verdict, the Stage-1 candidate set,
# and the Stage-1 telemetry) is logged the moment it is finalized, threaded by batch_id + key.
# DEBUG, not INFO: this is one line per object per work item, so it would spam a normal run; the
# sample runner raises the logger to DEBUG to show the full object trace, and it can be enabled in
# production to trace one amenity. The authoritative copies still live in the state stores.
DISCOVERY_OBJECT_FINALIZED_EVENT = "r3m1_3.object_finalized"

# STEP 4 bound: amenity pipelines in flight. Each pipeline has at most one LLM call in flight, so
# this also bounds concurrent LLM calls (no separate LLM-call semaphore). Phase-1 searches share the
# gateway's Parallel semaphore with discovery. Starting value, not measured.
AMENITY_PIPELINE_CONCURRENCY = SEARCH_CONCURRENCY
# R3.M1.4 phase-1 budget per metric: one search + one retry. The app counts, never the LLM.
PHASE1_MAX_ATTEMPTS = 2
PHASE1_TURN1_STAGE = "r3_m1_4_phase1_turn1"
PHASE1_RETRY_STAGE = "r3_m1_4_phase1_retry"
_PHASE1_CONTEXT = "metric_web_search"
# R3.M1.5 run-level circuit breaker default (Settings `METRIC_RESOLUTION_BREAKER_THRESHOLD`).
BREAKER_THRESHOLD_DEFAULT = 3

# R3.M1.4 / R3.M1.5 log events (threaded by run_id + the (category_id, place_id) key).
BREAKER_OPENED_EVENT = "r3m1_5.breaker_opened"
PIPELINES_START_EVENT = "r3m1_4.pipelines_start"
PIPELINES_DONE_EVENT = "r3m1_4.pipelines_done"
PIPELINE_DEGRADED_EVENT = "r3m1_4.pipeline_degraded"
PIPELINE_PROVIDER_FAILED_EVENT = "r3m1_4.pipeline_provider_failed"
PIPELINE_CRASHED_EVENT = "r3m1_4.pipeline_crashed"
PHASE1_TURN_EVENT = "r3m1_4.phase1_turn"
PHASE1_GUARD_REJECTED_EVENT = "r3m1_4.guard_rejected"
PHASE1_CALL_NOT_EXECUTED_EVENT = "r3m1_4.call_not_executed"
PHASE1_SEARCH_FAILED_EVENT = "r3m1_4.search_failed"
PHASE1_METRICS_UNCOVERED_EVENT = "r3m1_4.metrics_uncovered"
PHASE1_DONE_EVENT = "r3m1_4.phase1_done"
# DEBUG, like the R3.M1.3 object trace: the finalized Phase1Result summary per amenity.
PHASE1_OBJECT_FINALIZED_EVENT = "r3m1_4.object_finalized"

# Gateway failure kinds rendered for the LLM in a `failed` tool message (a few words, no retry flag).
_FAILURE_PHRASES = {
    "timeout": "timed out",
    "rate_limited": "rate limited",
    "transport": "connection failed",
    "tool_error": "the search tool returned an error",
    "unparseable": "the search result could not be read",
}
# Why the app did not send an admitted call to the gateway (the LLM sees these words).
_NOT_EXECUTED_PHRASES = {
    "already_searched": "not run: this metric was already searched and its result is final",
    "no_attempt_left": "not run: this metric has no search attempt left",
    "not_retry_eligible": "not run: only metrics whose search failed may be searched again",
    "duplicate_in_turn": "not run: another call in this turn already searches this metric",
    "unattributed": "not run: the call is not tagged with a known metric_label",
}

_T = TypeVar("_T")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class _DiscoveryWorkItem:
    """STEP 2 output: one eligible (category_id, place_id) amenity, with its plan context.

    Carries only the key fields; discovery reads the amenity identity (name, website, address) from
    the `PredefinedMetricsRecord` at `state.predefined_records[category_id][place_id]`.
    """

    category_id: int
    place_id: str
    taxonomy_node: str
    depth: DepthLevel
    specific_metrics: list[MetricSpec]


@dataclass
class _CircuitBreaker:
    """R3.M1.5 run-scoped circuit breaker, shared by the discovery batch and every amenity pipeline.

    One per run, created at the start of `run_specific_metric_resolution` and passed down (never kept
    on `self`, so runs do not share it). `counter` is the number of `availability` LLM failures with no
    LLM success in between, in completion order. At `threshold` the breaker opens for the rest of the
    run. Updates contain no `await`, so on the single event loop they need no lock.
    """

    threshold: int
    counter: int = 0
    open: bool = False

    def check(self, stage: str) -> None:
        """Raise `circuit_open` instead of making the call when the breaker is open."""
        if self.open:
            raise MetricResolutionProviderError(
                f"circuit breaker open; {stage} LLM call not made",
                stage=stage,
                cause="circuit_open",
            )

    def record_success(self) -> None:
        """Any LLM call that answered resets the consecutive-failure count."""
        self.counter = 0

    def record_failure(self, cause: ProviderFailureCause, stage: str) -> None:
        """Count an `availability` failure; open at the threshold. Other causes never count."""
        if cause != "availability" or self.open:
            return
        self.counter += 1
        if self.counter >= self.threshold:
            self.open = True
            # A state change that degrades every later LLM call in the run: the only signal of why
            # later amenities stop with `circuit_open`.
            logger.warning(
                json.dumps(
                    {
                        "event": BREAKER_OPENED_EVENT,
                        "timestamp": _timestamp(),
                        "threshold": self.threshold,
                        "counter": self.counter,
                        "stage": stage,
                    }
                )
            )


@dataclass(frozen=True)
class _ShapedToolResult:
    """R3.M1.2 output for one phase-1 call: exactly one `tool` message plus its status.

    `result` is the passed-through search result for `ok` / `empty` (None for `failed`), used to
    record evidence. `failure_kind` is the gateway kind, `rejected`, or a not-executed reason.
    """

    tool_call_id: str
    metric_label: str | None
    status: MetricSearchStatus
    message: dict
    result: WebSearchResult | None
    failure_kind: str | None


class SpecificMetricResolution:
    """Responsibility 3: resolve each LLM-defined `specific_metric` to a committed factual value.

    R3 owns the MCP tool gateway (its session lifecycle lives inside
    `run_specific_metric_resolution`) and uses the shared `StructuredLLMCaller` for its LLM turns.
    The gateway is injected and never opened at construction; the shared caller is owned by the
    `DeepSearch` feature (so `owns_caller` is False) — standalone construction owns its own.
    """

    def __init__(
        self,
        *,
        tool_gateway: ToolGateway,
        llm_caller: StructuredLLMCaller | None = None,
        owns_caller: bool = True,
        breaker_threshold: int = BREAKER_THRESHOLD_DEFAULT,
    ) -> None:
        # Injected (C3.1.1). It is the locked test seam, so the service never sees MCP types. No
        # session is opened at construction; `run_specific_metric_resolution` opens and closes it.
        self._tool_gateway = tool_gateway
        # Shared caller for the R3.M1 tool turns and R3.M2 structured turns (C3.1.2). When the
        # DeepSearch feature injects one, `owns_caller` is False and the feature closes it.
        self._llm_caller = llm_caller
        self._owns_caller = owns_caller
        # Consecutive availability failures that open the run's circuit breaker (R3.M1.5).
        self._breaker_threshold = breaker_threshold

    async def run_specific_metric_resolution(
        self, state: AmenitySearchState
    ) -> AmenitySearchState:
        """R3 entry point — built through STEP 5 with the Phase-1 Loop as the only pipeline step.

        Opens the gateway, builds `plan_index` (STEP 1), derives the eligible work items (STEP 2),
        builds the phase-1 catalog (fails the run before any LLM call if the schema is unusable),
        runs the discovery batch (STEP 3), runs one pipeline per work item (STEP 4), sweeps the
        results into `state.phase1_results` (STEP 5) and applies the run-level raise, then closes
        the gateway. STEP 6 (combine) is not built, so `state.amenity_records` stays `None`.
        """
        if self._llm_caller is None:
            # Discovery Stage 1 needs the shared caller; a None caller is a composition-root bug.
            raise MetricResolutionProviderError(
                "SpecificMetricResolution has no LLM caller; cannot run discovery",
                stage="run_specific_metric_resolution",
                cause="availability",
            )
        # One breaker per run, shared by discovery and every pipeline (R3.M1.5).
        breaker = _CircuitBreaker(threshold=self._breaker_threshold)
        await self._tool_gateway.open()
        try:
            raw_tool_definitions = self._tool_gateway.get_tool_definitions()
            plan_index = self._build_plan_index(state)  # STEP 1
            work_items = self._derive_work_items(state, plan_index)  # STEP 2
            phase1_catalog: list[dict] | None = None
            if work_items:
                # Raw definitions are fixed after open(); a schema the catalog cannot be built from
                # is a gateway mismatch, so it raises here, before any LLM spend (R3.M1.1).
                phase1_catalog = build_tool_catalog(raw_tool_definitions, _PHASE1_CONTEXT)
            await self._run_discovery_batch(  # STEP 3
                state, work_items, raw_tool_definitions, breaker=breaker
            )
            if phase1_catalog is not None:
                run_id = uuid4().hex
                results = await self._run_amenity_pipelines(  # STEP 4
                    state, work_items, phase1_catalog, breaker, run_id
                )
                records = self._sweep_pipeline_results(work_items, results, breaker, run_id)
                # The only STEP 4/5 state write, after the barrier (pipelines return by value).
                state.phase1_results.update(records)
                self._raise_if_no_pipeline_completed(records, breaker)  # STEP 5 run-level raise
        finally:
            # Session scope = this method (C3.1.1): close the gateway sessions even on failure. The
            # shared caller is not closed here; `aclose()` closes it only when this instance owns it.
            await self._tool_gateway.aclose()
        return state

    # ---- STEP 1 / STEP 2 (deterministic spine) -------------------------------------------------
    def _build_plan_index(
        self, state: AmenitySearchState
    ) -> dict[int, CategoryMetricPlan]:
        """STEP 1: index the category plans by `category_id` once."""
        return {plan.category_id: plan for plan in state.category_metric_plans}

    def _derive_work_items(
        self,
        state: AmenitySearchState,
        plan_index: dict[int, CategoryMetricPlan],
    ) -> list[_DiscoveryWorkItem]:
        """STEP 2 (RC7): one work item per discovered (cat, place) whose category has specifics."""
        work_items: list[_DiscoveryWorkItem] = []
        for category_id, places in state.discovered_places.items():
            plan = plan_index.get(category_id)
            if plan is None or not plan.specific_metrics:
                # No plan ⇒ no metrics, or a basic_profile category with no specific_metrics (RC7):
                # not eligible, so no work item. Reproducible from inputs, so DEBUG not WARN.
                logger.debug(
                    json.dumps(
                        {
                            "event": "r3m1_3.category_not_eligible",
                            "timestamp": _timestamp(),
                            "category_id": category_id,
                            "has_plan": plan is not None,
                        }
                    )
                )
                continue
            for place_id in places:
                work_items.append(
                    _DiscoveryWorkItem(
                        category_id=category_id,
                        place_id=place_id,
                        taxonomy_node=plan.taxonomy_node,
                        depth=plan.depth,
                        specific_metrics=plan.specific_metrics,
                    )
                )
        return work_items

    # ---- STEP 3 (R3.M1.3 discovery batch) ------------------------------------------------------
    async def _run_discovery_batch(
        self,
        state: AmenitySearchState,
        work_items: list[_DiscoveryWorkItem],
        raw_tool_definitions: RawToolDefinitions,
        *,
        breaker: _CircuitBreaker,
    ) -> None:
        """STEP 3: Stage-0 sync pre-pass over all items, then Stage-1 fan-out over the declined.

        The `asyncio.gather` is the hard barrier (RC8): when it returns, every work item has a
        verdict in `state.website_search_results` (google items written in the pre-pass, the rest
        merged here). Tasks return their results; the stores are written after the barrier, so no
        task mutates shared state during the gather.
        """
        batch_id = uuid4().hex
        logger.info(
            json.dumps(
                {
                    "event": DISCOVERY_BATCH_START_EVENT,
                    "timestamp": _timestamp(),
                    "batch_id": batch_id,
                    "work_items": len(work_items),
                }
            )
        )

        declined = self._discovery_pre_pass(state, work_items, batch_id)
        logger.info(
            json.dumps(
                {
                    "event": DISCOVERY_PRE_PASS_DONE_EVENT,
                    "timestamp": _timestamp(),
                    "batch_id": batch_id,
                    "official": len(work_items) - len(declined),
                    "declined": len(declined),
                }
            )
        )

        if declined:
            semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

            async def _one(work_item: _DiscoveryWorkItem):
                rec = state.predefined_records[work_item.category_id][work_item.place_id]
                async with semaphore:
                    return await self._discover_website_url(
                        work_item, rec, raw_tool_definitions, batch_id, breaker=breaker
                    )

            results = await asyncio.gather(
                *(_one(work_item) for work_item in declined), return_exceptions=True
            )
            for work_item, result in zip(declined, results):
                key = (work_item.category_id, work_item.place_id)
                if isinstance(result, BaseException):
                    # An unexpected raise escaped the coroutine's own handling: isolate it to this
                    # item as `none` (D5); siblings are unaffected (return_exceptions=True).
                    state.website_search_results[key] = WebsiteSearchResult(None, "none")
                    self._log_object_finalized(
                        batch_id, key, "website_search_result", state.website_search_results[key]
                    )
                    self._log_degraded(batch_id, key, "task_exception")
                    continue
                verdict, telemetry = result
                state.website_search_results[key] = verdict
                if telemetry is not None:
                    state.discovery_search_results[key] = telemetry
                if verdict.website_origin == "discovered":
                    logger.info(
                        json.dumps(
                            {
                                "event": DISCOVERY_RESOLVED_EVENT,
                                "timestamp": _timestamp(),
                                "batch_id": batch_id,
                                "category_id": key[0],
                                "place_id": key[1],
                                "origin": verdict.website_origin,
                            }
                        )
                    )

        self._log_batch_done(state, work_items, batch_id)

    def _discovery_pre_pass(
        self,
        state: AmenitySearchState,
        work_items: list[_DiscoveryWorkItem],
        batch_id: str,
    ) -> list[_DiscoveryWorkItem]:
        """Stage 0 (synchronous, all items): gate each item; return the declined subset.

        Writes a `google` verdict for every gate-`official` item immediately, and an
        `OfficialGateRecord` for EVERY item (both verdicts). A missing record cannot be discovered
        (no identity) → `none` verdict, not declined. A gate that raises on a malformed record is
        routed to the declined set (safe default), never silently to `none`.
        """
        declined: list[_DiscoveryWorkItem] = []
        for work_item in work_items:
            key = (work_item.category_id, work_item.place_id)
            rec = state.predefined_records.get(work_item.category_id, {}).get(
                work_item.place_id
            )
            if rec is None:
                # Precondition drift: M1.3 wrote no record for this key, so there is no identity to
                # discover with. Reject to a `none` verdict and record why.
                state.website_search_results[key] = WebsiteSearchResult(None, "none")
                state.official_gate_results[key] = OfficialGateRecord(
                    name=None,
                    website=None,
                    host=None,
                    registered_domain=None,
                    sld=None,
                    suffix=None,
                    compact_name=None,
                    compact_sld=None,
                    verdict="discovery",
                    reason_code="missing_record",
                )
                self._log_object_finalized(
                    batch_id, key, "official_gate_record", state.official_gate_results[key]
                )
                self._log_object_finalized(
                    batch_id, key, "website_search_result", state.website_search_results[key]
                )
                self._log_degraded(batch_id, key, "missing_record")
                continue
            try:
                outcome = official_url_gate(rec.website, rec.name)
            except Exception:  # noqa: BLE001 - a malformed record must not crash the pre-pass
                # De-mask: route to discovery (it will search), never silent `none`; record it.
                declined.append(work_item)
                state.official_gate_results[key] = OfficialGateRecord(
                    name=rec.name,
                    website=rec.website,
                    host=None,
                    registered_domain=None,
                    sld=None,
                    suffix=None,
                    compact_name=None,
                    compact_sld=None,
                    verdict="discovery",
                    reason_code="gate_error",
                )
                self._log_object_finalized(
                    batch_id, key, "official_gate_record", state.official_gate_results[key]
                )
                self._log_degraded(batch_id, key, "gate_error")
                continue

            state.official_gate_results[key] = OfficialGateRecord(
                name=rec.name,
                website=rec.website,
                host=outcome.host,
                registered_domain=outcome.registered_domain,
                sld=outcome.sld,
                suffix=outcome.suffix,
                compact_name=outcome.compact_name,
                compact_sld=outcome.compact_sld,
                verdict=outcome.verdict,
                reason_code=outcome.reason_code,
            )
            self._log_object_finalized(
                batch_id, key, "official_gate_record", state.official_gate_results[key]
            )
            if outcome.verdict == "official":
                state.website_search_results[key] = WebsiteSearchResult(
                    rec.website, "google"
                )
                self._log_object_finalized(
                    batch_id, key, "website_search_result", state.website_search_results[key]
                )
            else:
                declined.append(work_item)
        return declined

    async def _discover_website_url(
        self,
        work_item: _DiscoveryWorkItem,
        rec: PredefinedMetricsRecord,
        raw_tool_definitions: RawToolDefinitions,
        batch_id: str,
        *,
        breaker: _CircuitBreaker,
    ) -> tuple[WebsiteSearchResult, DiscoverySearchRecord | None]:
        """Stage 1 for one declined item: search → index → select → resolve. Degrades to `none`.

        Checks the run's breaker first (R3.M1.5 check point: before each discovery coroutine starts
        Stage 1). When open, the item skips its search and selection turn and gets `none`.
        """
        key = (work_item.category_id, work_item.place_id)
        if breaker.open:
            verdict = WebsiteSearchResult(None, "none")
            self._log_object_finalized(batch_id, key, "website_search_result", verdict)
            self._log_degraded(batch_id, key, "circuit_open")
            return verdict, None
        search = await self._run_discovery_search(
            rec, raw_tool_definitions, key, batch_id, breaker=breaker
        )
        if search is None:
            # search give-up (catalog / provider / guard / tool failure) already logged degraded.
            verdict = WebsiteSearchResult(None, "none")
            self._log_object_finalized(batch_id, key, "website_search_result", verdict)
            return verdict, None

        candidates, id_url_map = _index_candidates(search)
        self._log_object_finalized(batch_id, key, "discovery_candidates", candidates)
        if not candidates:
            # The search returned nothing selectable (no excerpts, or all url=None). Genuine
            # no-candidate → `none`; not a drift, so no WARN. Telemetry still records the search.
            verdict = WebsiteSearchResult(None, "none")
            telemetry = DiscoverySearchRecord(
                objective=search.objective,
                search_queries=search.search_queries,
                candidates=(),
                selected_id=None,
                resolved_url=None,
                retrieved_at=search.retrieved_at,
            )
            self._log_object_finalized(batch_id, key, "website_search_result", verdict)
            self._log_object_finalized(batch_id, key, "discovery_search_record", telemetry)
            return verdict, telemetry

        selected_id = await self._select_candidate(
            rec.name, rec.address, candidates, id_url_map, key, batch_id, breaker=breaker
        )
        verdict = _resolve_verdict(selected_id, id_url_map)
        telemetry = DiscoverySearchRecord(
            objective=search.objective,
            search_queries=search.search_queries,
            candidates=candidates,
            selected_id=selected_id,
            resolved_url=verdict.website_url,
            retrieved_at=search.retrieved_at,
        )
        self._log_object_finalized(batch_id, key, "website_search_result", verdict)
        self._log_object_finalized(batch_id, key, "discovery_search_record", telemetry)
        return verdict, telemetry

    async def _run_discovery_search(
        self,
        rec: PredefinedMetricsRecord,
        raw_tool_definitions: RawToolDefinitions,
        key: tuple[int, str],
        batch_id: str,
        *,
        breaker: _CircuitBreaker,
    ) -> WebSearchResult | None:
        """One LLM-built `web_search` turn: catalog → call_turn → guard → search (+1 retry).

        Returns the search result, or `None` on any give-up (caller → `none`). Each give-up is
        logged WARN with its reason.
        """
        assert self._llm_caller is not None  # guarded in run_specific_metric_resolution
        try:
            catalog = build_tool_catalog(raw_tool_definitions, "website_discovery")
        except MetricResolutionValidationError:
            self._log_degraded(batch_id, key, "catalog_error")
            return None

        instruction = build_discovery_search_instruction(rec.name, rec.address)
        messages = [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": "Make the web_search tool call now for the amenity above.",
            },
        ]
        try:
            turn = await self._counted_llm_call(
                breaker,
                self._llm_caller.call_turn(
                    messages=messages,
                    tools=catalog,
                    tool_choice="required",
                    stage="r3_m1_3_discovery_search",
                    provider_error_cls=MetricResolutionProviderError,
                ),
            )
        except MetricResolutionProviderError:
            self._log_degraded(batch_id, key, "provider_exhausted")
            return None

        decision = guard_proposed_calls(turn.tool_calls, catalog, "website_discovery", None)
        if decision.decision != "accepted" or not decision.validated_calls:
            self._log_degraded(batch_id, key, "guard_rejected")
            return None

        call = decision.validated_calls[0]
        objective = call.arguments["objective"]
        search_queries = call.arguments["search_queries"]

        result = await self._search_once(objective, search_queries)
        if isinstance(result, ToolFailure):
            # Tool call failed (gateway failure, after the gateway's own transient retries): one
            # R3.M1.3-level retry of the same call, then give up (spec "Failure vs empty").
            result = await self._search_once(objective, search_queries)
            if isinstance(result, ToolFailure):
                self._log_degraded(batch_id, key, "search_failed")
                return None
        return result

    async def _search_once(
        self, objective: str, search_queries: list[str]
    ) -> WebSearchResult | ToolFailure:
        """One `search_web` call; a bad-argument `ValueError` is turned into a typed tool failure."""
        try:
            return await self._tool_gateway.search_web(objective, search_queries)
        except ValueError as exc:
            return ToolFailure("web_search", "tool_error", str(exc))

    async def _select_candidate(
        self,
        name: str | None,
        address: str | None,
        candidates: tuple[DiscoveryCandidate, ...],
        id_url_map: dict[str, str],
        key: tuple[int, str],
        batch_id: str,
        *,
        breaker: _CircuitBreaker,
    ) -> str | None:
        """Structured selection turn: return a valid candidate id, or `None`.

        `None` means either the confident `none` sentinel (terminal, not a drift) or an invalid
        verdict after one retry. An invalid verdict (schema-invalid body, or a `selected_id` not in
        the issued set) is retried once with the SAME candidates — no second `web_search`. Provider
        exhaustion → `None` (D5).
        """
        assert self._llm_caller is not None  # guarded in run_specific_metric_resolution
        schema = website_selection_json_schema()
        instruction = build_website_selection_instruction(name, address, candidates, schema)
        user_content = "Return the id of the amenity's official-site candidate, or null."

        # One attempt + one retry of the selection turn only (same indexed candidates in hand).
        for _attempt in range(2):
            try:
                body, _answered_by = await self._counted_llm_call(
                    breaker,
                    self._llm_caller.call_structured(
                        instruction=instruction,
                        user_content=user_content,
                        json_schema=schema,
                        schema_name=WEBSITE_SELECTION_SCHEMA_NAME,
                        stage="r3_m1_3_website_selection",
                        provider_error_cls=MetricResolutionProviderError,
                    ),
                )
            except MetricResolutionProviderError:
                self._log_degraded(batch_id, key, "provider_exhausted")
                return None

            try:
                parsed = WebsiteSelectionResult.model_validate(body)
            except ValidationError:
                # Schema-invalid body (unexpected under strict): invalid verdict → retry once.
                continue

            selected_id = parsed.selected_id
            if selected_id is None:
                return None  # confident `none` sentinel — terminal, no retry
            if selected_id in id_url_map:
                return selected_id
            # selected_id ∉ issued set → invalid verdict → retry once with the same candidates.

        self._log_degraded(batch_id, key, "invalid_verdict")
        return None

    # ---- R3.M1.5 breaker funnel (shared by STEP 3 and STEP 4) --------------------------------
    async def _counted_llm_call(
        self, breaker: _CircuitBreaker, awaitable: Awaitable[_T]
    ) -> _T:
        """Await one LLM call and feed its outcome to the run's breaker.

        Success resets the counter; a `MetricResolutionProviderError` counts only when its cause is
        `availability`, then propagates unchanged. The open-breaker check happens before the call
        is created (`breaker.check`), so this funnel never sees `circuit_open` from itself.
        """
        try:
            result = await awaitable
        except MetricResolutionProviderError as exc:
            breaker.record_failure(exc.cause, exc.stage)
            raise
        breaker.record_success()
        return result

    # ---- STEP 4 (amenity pipelines; R3.M1.4 phase 1 only for now) ------------------------------
    async def _run_amenity_pipelines(
        self,
        state: AmenitySearchState,
        work_items: list[_DiscoveryWorkItem],
        catalog: list[dict],
        breaker: _CircuitBreaker,
        run_id: str,
    ) -> list[AmenityPhase1Record | BaseException]:
        """STEP 4: one pipeline per work item, concurrently under a cap; the gather is the barrier.

        Pipelines read state but write none; each returns its record by value. An unexpected raise
        comes back as a value (`return_exceptions=True`) for the STEP 5 sweep, so siblings finish.
        """
        logger.info(
            json.dumps(
                {
                    "event": PIPELINES_START_EVENT,
                    "timestamp": _timestamp(),
                    "run_id": run_id,
                    "work_items": len(work_items),
                    "concurrency": AMENITY_PIPELINE_CONCURRENCY,
                }
            )
        )
        semaphore = asyncio.Semaphore(AMENITY_PIPELINE_CONCURRENCY)

        async def _one(work_item: _DiscoveryWorkItem) -> AmenityPhase1Record:
            key = (work_item.category_id, work_item.place_id)
            website = state.website_search_results.get(key)
            if website is None:
                # RC8 says discovery wrote a verdict for every item; de-mask a violation instead of
                # a KeyError: run phase 1 without a URL and say so.
                self._log_pipeline_event(
                    logging.WARNING, PIPELINE_DEGRADED_EVENT, run_id, key, reason="missing_verdict"
                )
                website = WebsiteSearchResult(None, "none")
            rec = state.predefined_records.get(work_item.category_id, {}).get(
                work_item.place_id
            )
            async with semaphore:
                return await self._run_amenity_pipeline(
                    work_item, rec, website, catalog, breaker, run_id
                )

        return await asyncio.gather(
            *(_one(work_item) for work_item in work_items), return_exceptions=True
        )

    async def _run_amenity_pipeline(
        self,
        work_item: _DiscoveryWorkItem,
        rec: PredefinedMetricsRecord | None,
        website: WebsiteSearchResult,
        catalog: list[dict],
        breaker: _CircuitBreaker,
        run_id: str,
    ) -> AmenityPhase1Record:
        """One amenity pipeline with its provider-failure catch (R3.M1.5 pipeline catch).

        A `MetricResolutionProviderError` from any LLM step ends the amenity: evidence is discarded
        and the record is `resolution_call_failed` with the step's `stage` and `cause`. Any other
        exception propagates to the gather (and becomes `pipeline_error` in the sweep).
        """
        key = (work_item.category_id, work_item.place_id)
        if rec is None:
            # Precondition drift: no M1.3 record means no amenity identity to search with.
            self._log_pipeline_event(
                logging.WARNING, PIPELINE_DEGRADED_EVENT, run_id, key, reason="missing_record"
            )
            return AmenityPhase1Record(key[0], key[1], "pipeline_error", None)
        try:
            phase1 = await self._phase1_loop(work_item, rec, website, catalog, breaker, run_id)
        except MetricResolutionProviderError as exc:
            self._log_pipeline_event(
                logging.WARNING,
                PIPELINE_PROVIDER_FAILED_EVENT,
                run_id,
                key,
                stage=exc.stage,
                cause=exc.cause,
            )
            return AmenityPhase1Record(
                key[0],
                key[1],
                "resolution_call_failed",
                None,
                failed_stage=exc.stage,
                failed_cause=exc.cause,
            )
        return AmenityPhase1Record(key[0], key[1], "completed", phase1)

    # ---- R3.M1.4 step 1: Phase-1 Loop ----------------------------------------------------------
    async def _phase1_loop(
        self,
        work_item: _DiscoveryWorkItem,
        rec: PredefinedMetricsRecord,
        website: WebsiteSearchResult,
        catalog: list[dict],
        breaker: _CircuitBreaker,
        run_id: str,
    ) -> Phase1Result:
        """Turn 1 for every metric, then at most one retry turn for retry-eligible metrics.

        The app owns the budget: after turn 1 it decides whether a retry turn happens (any metric
        `failed` or guard-rejected with its retry unused) and which calls may run. A provider error
        in either turn propagates (no tool message appended, no budget retry used).
        """
        key = (work_item.category_id, work_item.place_id)
        messages: list[dict] = [
            {
                "role": "system",
                "content": build_phase1_search_instruction(
                    rec.name,
                    rec.address,
                    work_item.taxonomy_node,
                    website.website_url,
                    work_item.specific_metrics,
                ),
            },
            {"role": "user", "content": PHASE1_USER_TURN_CONTENT},
        ]
        ledger = _new_ledger(work_item.specific_metrics)
        store = MetricsSourceContent()

        await self._run_phase1_turn(messages, catalog, ledger, 1, store, breaker, key, run_id)
        turns_run = 1
        retry_labels = _retry_eligible(ledger)
        if retry_labels:
            # Same shared history, nothing re-sent: the LLM matches its failed results by
            # tool_call_id and re-emits only those metrics.
            await self._run_phase1_turn(messages, catalog, ledger, 2, store, breaker, key, run_id)
            turns_run = 2

        uncovered = tuple(label for label, row in ledger.items() if row.status == "not_searched")
        if uncovered:
            # Coverage degrade: no call was ever attributed to these metrics; triage forces them
            # unresolved. This WARN is the only signal the LLM skipped them.
            self._log_pipeline_event(
                logging.WARNING,
                PHASE1_METRICS_UNCOVERED_EVENT,
                run_id,
                key,
                labels=list(uncovered),
            )
        result = Phase1Result(
            messages=messages,
            metrics_source_content=store,
            metric_outcomes=ledger,
            uncovered_labels=uncovered,
            turns_run=turns_run,
        )
        counts = _status_counts(ledger)
        self._log_pipeline_event(
            logging.INFO,
            PHASE1_DONE_EVENT,
            run_id,
            key,
            turns_run=turns_run,
            retried_labels=list(retry_labels),
            evidence_items=len(store.items),
            **counts,
        )
        self._log_pipeline_event(
            logging.DEBUG,
            PHASE1_OBJECT_FINALIZED_EVENT,
            run_id,
            key,
            object="phase1_result",
            metric_outcomes={
                label: {
                    "status": row.status,
                    "attempts_used": row.attempts_used,
                    "failure_kind": row.failure_kind,
                }
                for label, row in ledger.items()
            },
            evidence={
                label: [item.url for item in store.items_for(label)] for label in ledger
            },
            message_count=len(messages),
        )
        return result

    async def _run_phase1_turn(
        self,
        messages: list[dict],
        catalog: list[dict],
        ledger: dict[str, MetricSearchOutcome],
        turn: int,
        store: MetricsSourceContent,
        breaker: _CircuitBreaker,
        key: tuple[int, str],
        run_id: str,
    ) -> tuple[_ShapedToolResult, ...]:
        """One pass of the R3.M1 tool-turn atom on the amenity's shared history.

        breaker check → `call_turn(required)` → guard → (accepted) prepare + budget admission +
        concurrent searches + shaping, or (rejected) outcomes + attribution + replay cleanup →
        append the assistant message, then exactly one tool message per kept call in message order
        → record evidence from `ok` results. Mutates `messages`, `ledger` and `store`.
        """
        assert self._llm_caller is not None  # guarded in run_specific_metric_resolution
        stage = PHASE1_TURN1_STAGE if turn == 1 else PHASE1_RETRY_STAGE
        breaker.check(stage)
        assistant = await self._counted_llm_call(
            breaker,
            self._llm_caller.call_turn(
                messages=messages,
                tools=catalog,
                tool_choice="required",
                stage=stage,
                provider_error_cls=MetricResolutionProviderError,
            ),
        )
        decision = guard_proposed_calls(
            assistant.tool_calls,
            catalog,
            _PHASE1_CONTEXT,
            {"metric_labels": list(ledger)},
        )

        shaped: list[_ShapedToolResult] = []
        executed = 0
        not_executed = 0
        if decision.decision == "accepted":
            messages.append(assistant.message)
            prepared = prepare_admitted_calls(decision.validated_calls, _PHASE1_CONTEXT)
            admitted, refused = _admit_calls(prepared, ledger, turn)
            results = await self._execute_web_searches(admitted)
            by_id: dict[str, _ShapedToolResult] = {}
            for call, outcome in zip(admitted, results):
                label = call.metric_labels[0]
                item = _shape_web_search(call.tool_call_id, label, outcome)
                _apply_shaped(ledger[label], item)
                by_id[call.tool_call_id] = item
                if item.status == "failed":
                    self._log_pipeline_event(
                        logging.WARNING,
                        PHASE1_SEARCH_FAILED_EVENT,
                        run_id,
                        key,
                        turn=turn,
                        metric_label=label,
                        failure_kind=item.failure_kind,
                    )
            for call, reason in refused:
                label = call.metric_labels[0] if call.metric_labels else None
                by_id[call.tool_call_id] = _shape_not_executed(call.tool_call_id, label, reason)
                self._log_pipeline_event(
                    logging.WARNING,
                    PHASE1_CALL_NOT_EXECUTED_EVENT,
                    run_id,
                    key,
                    turn=turn,
                    metric_label=label,
                    reason=reason,
                )
            shaped = [by_id[call.tool_call_id] for call in prepared]
            executed = len(admitted)
            not_executed = len(refused)
        else:
            outcomes = build_rejection_outcomes(assistant.tool_calls, decision)
            attributed = _attribute_rejected_turn(outcomes, ledger, turn)
            sanitized = sanitize_replay_message(assistant.message, outcomes)
            kept = [o for o in outcomes if o.category != "out_of_catalog"]
            if sanitized is not None:
                messages.append(sanitized)
                shaped = [_shape_rejected(o, ledger) for o in kept]
            self._log_pipeline_event(
                logging.WARNING,
                PHASE1_GUARD_REJECTED_EVENT,
                run_id,
                key,
                turn=turn,
                reason_codes=sorted({e.reason_code for e in decision.errors}),
                attributed_labels=list(attributed),
                stripped_out_of_catalog=len(outcomes) - len(kept),
            )

        for item in shaped:
            messages.append(item.message)
        recorded = _record_web_evidence(shaped, store)
        status_counts: dict[str, int] = {}
        for item in shaped:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
        self._log_pipeline_event(
            logging.INFO,
            PHASE1_TURN_EVENT,
            run_id,
            key,
            turn=turn,
            provider=assistant.provider,
            guard_decision=decision.decision,
            proposed=len(assistant.tool_calls),
            executed=executed,
            not_executed=not_executed,
            tool_messages=len(shaped),
            hits_recorded=recorded,
            statuses=status_counts,
        )
        return tuple(shaped)

    async def _execute_web_searches(
        self, calls: Sequence[PreparedCall]
    ) -> list[WebSearchResult | ToolFailure]:
        """Run the admitted searches together (gateway Parallel semaphore bounds them).

        Results come back in call order. A raise that escapes `_search_once` becomes a typed
        `tool_error` failure here, so one bad call cannot stop the turn (it is shaped `failed`).
        """
        results = await asyncio.gather(
            *(
                self._search_once(call.arguments["objective"], call.arguments["search_queries"])
                for call in calls
            ),
            return_exceptions=True,
        )
        typed: list[WebSearchResult | ToolFailure] = []
        for result in results:
            if isinstance(result, BaseException):
                typed.append(
                    ToolFailure("web_search", "tool_error", f"{type(result).__name__}: {result}")
                )
            else:
                typed.append(result)
        return typed

    # ---- STEP 5 (post-gather sweep + run-level raise) ------------------------------------------
    def _sweep_pipeline_results(
        self,
        work_items: list[_DiscoveryWorkItem],
        results: list[AmenityPhase1Record | BaseException],
        breaker: _CircuitBreaker,
        run_id: str,
    ) -> dict[tuple[int, str], AmenityPhase1Record]:
        """STEP 5: turn every gather slot into a record; an exception slot is a `pipeline_error`."""
        records: dict[tuple[int, str], AmenityPhase1Record] = {}
        for work_item, result in zip(work_items, results):
            key = (work_item.category_id, work_item.place_id)
            if isinstance(result, BaseException):
                # An unexpected raise escaped the pipeline (a bug): isolate it to this amenity (D5).
                self._log_pipeline_event(
                    logging.ERROR,
                    PIPELINE_CRASHED_EVENT,
                    run_id,
                    key,
                    error_type=type(result).__name__,
                    message=str(result),
                )
                records[key] = AmenityPhase1Record(key[0], key[1], "pipeline_error", None)
            else:
                records[key] = result
        counts = {"completed": 0, "resolution_call_failed": 0, "pipeline_error": 0}
        for record in records.values():
            counts[record.outcome] += 1
        logger.info(
            json.dumps(
                {
                    "event": PIPELINES_DONE_EVENT,
                    "timestamp": _timestamp(),
                    "run_id": run_id,
                    **counts,
                    "breaker_open": breaker.open,
                }
            )
        )
        return records

    def _raise_if_no_pipeline_completed(
        self,
        records: dict[tuple[int, str], AmenityPhase1Record],
        breaker: _CircuitBreaker,
    ) -> None:
        """Run-level raise: no pipeline completed and at least one ended on a provider failure.

        Called after the records are written to state. The cause is `circuit_open` when the breaker
        is open, `availability` when every provider failure was availability, else `content`.
        """
        if not records or any(r.outcome == "completed" for r in records.values()):
            return
        failed = [r for r in records.values() if r.outcome == "resolution_call_failed"]
        if not failed:
            return
        cause: ProviderFailureCause
        if breaker.open:
            cause = "circuit_open"
        elif all(r.failed_cause == "availability" for r in failed):
            cause = "availability"
        else:
            cause = "content"
        raise MetricResolutionProviderError(
            f"no amenity pipeline completed its LLM steps ({len(failed)} provider failures)",
            stage="run_specific_metric_resolution",
            cause=cause,
        )

    def _log_pipeline_event(
        self,
        level: int,
        event: str,
        run_id: str,
        key: tuple[int, str],
        **fields: object,
    ) -> None:
        """One structured STEP 4 log line, threaded by run_id + (category_id, place_id)."""
        logger.log(
            level,
            json.dumps(
                {
                    "event": event,
                    "timestamp": _timestamp(),
                    "run_id": run_id,
                    "category_id": key[0],
                    "place_id": key[1],
                    **fields,
                },
                ensure_ascii=False,
            ),
        )

    # ---- logging helpers -----------------------------------------------------------------------
    def _log_object_finalized(
        self, batch_id: str, key: tuple[int, str], obj_name: str, obj: object
    ) -> None:
        """DEBUG: one R3.M1.3 object recorded the moment it is finalized (a state-change node)."""
        payload: dict = {"object": obj_name}
        if isinstance(obj, OfficialGateRecord):
            payload.update(
                verdict=obj.verdict,
                reason_code=obj.reason_code,
                host=obj.host,
                registered_domain=obj.registered_domain,
                sld=obj.sld,
                suffix=obj.suffix,
                compact_name=obj.compact_name,
                compact_sld=obj.compact_sld,
            )
        elif isinstance(obj, WebsiteSearchResult):
            payload.update(website_origin=obj.website_origin, website_url=obj.website_url)
        elif isinstance(obj, DiscoverySearchRecord):
            payload.update(
                objective=obj.objective,
                search_queries=list(obj.search_queries),
                candidate_count=len(obj.candidates),
                selected_id=obj.selected_id,
                resolved_url=obj.resolved_url,
                retrieved_at=obj.retrieved_at,
            )
        elif obj_name == "discovery_candidates" and isinstance(obj, tuple):
            payload.update(
                count=len(obj),
                ids=[c.id for c in obj],
                urls=[c.url for c in obj],
            )
        logger.debug(
            json.dumps(
                {
                    "event": DISCOVERY_OBJECT_FINALIZED_EVENT,
                    "timestamp": _timestamp(),
                    "batch_id": batch_id,
                    "category_id": key[0],
                    "place_id": key[1],
                    **payload,
                }
            )
        )

    def _log_degraded(self, batch_id: str, key: tuple[int, str], reason: str) -> None:
        """WARN for a silent drift: this item degraded to `none` (the only evidence it happened)."""
        logger.warning(
            json.dumps(
                {
                    "event": DISCOVERY_DEGRADED_EVENT,
                    "timestamp": _timestamp(),
                    "batch_id": batch_id,
                    "category_id": key[0],
                    "place_id": key[1],
                    "reason": reason,
                }
            )
        )

    def _log_batch_done(
        self,
        state: AmenitySearchState,
        work_items: list[_DiscoveryWorkItem],
        batch_id: str,
    ) -> None:
        """INFO boundary out of STEP 3: the verdict distribution across all work items."""
        google = discovered = none = 0
        for work_item in work_items:
            verdict = state.website_search_results.get(
                (work_item.category_id, work_item.place_id)
            )
            if verdict is None:
                continue
            if verdict.website_origin == "google":
                google += 1
            elif verdict.website_origin == "discovered":
                discovered += 1
            else:
                none += 1
        logger.info(
            json.dumps(
                {
                    "event": DISCOVERY_BATCH_DONE_EVENT,
                    "timestamp": _timestamp(),
                    "batch_id": batch_id,
                    "google": google,
                    "discovered": discovered,
                    "none": none,
                }
            )
        )

    async def aclose(self) -> None:
        """Close the MCP gateway, and the shared caller only when this instance owns it."""
        if self._tool_gateway is not None:
            await self._tool_gateway.aclose()
        if self._owns_caller and self._llm_caller is not None:
            await self._llm_caller.aclose()


# --------------------------------------------------------------------------------------------------
# Module-level pure helpers (R3.M1.3 Stage 1).
# --------------------------------------------------------------------------------------------------
def _index_candidates(
    result: WebSearchResult,
) -> tuple[tuple[DiscoveryCandidate, ...], dict[str, str]]:
    """Index selectable search hits under opaque ids `c1`..`cN`; drop hits with no URL.

    Returns the candidate tuple (shown to the LLM) and the app-only `id → url` map (used to resolve
    the LLM's `selected_id` to a real URL). A hit with `url is None` is non-selectable and dropped.
    """
    candidates: list[DiscoveryCandidate] = []
    id_url_map: dict[str, str] = {}
    index = 0
    for excerpt in result.excerpts:
        if excerpt.url is None:
            continue
        index += 1
        candidate_id = f"c{index}"
        candidates.append(
            DiscoveryCandidate(
                id=candidate_id,
                url=excerpt.url,
                title=excerpt.title,
                text=excerpt.text,
            )
        )
        id_url_map[candidate_id] = excerpt.url
    return tuple(candidates), id_url_map


def _resolve_verdict(
    selected_id: str | None, id_url_map: dict[str, str]
) -> WebsiteSearchResult:
    """Resolve a validated `selected_id` to the verdict: `discovered` URL, or `none`.

    `selected_id` is `None` (null sentinel or invalid-after-retry) → `none`. A non-null id is
    already known to be in the issued set (`_select_candidate` enforced membership), so it resolves
    to a verbatim search-result URL with origin `discovered`.
    """
    if selected_id is None:
        return WebsiteSearchResult(None, "none")
    return WebsiteSearchResult(id_url_map[selected_id], "discovered")


# --------------------------------------------------------------------------------------------------
# Module-level pure helpers (R3.M1.4 step 1: budget, R3.M1.2 shaping, evidence recording).
# --------------------------------------------------------------------------------------------------
def _new_ledger(metrics: Sequence[MetricSpec]) -> dict[str, MetricSearchOutcome]:
    """One `not_searched` budget row per metric, keyed by label, in plan order."""
    return {metric.label: MetricSearchOutcome(label=metric.label) for metric in metrics}


def _refusal_reason(row: MetricSearchOutcome, turn: int) -> str | None:
    """Why a call for this metric may not run in this turn, or None when it may.

    `ok` / `empty` are terminal; no metric gets more than two attempts; on the retry turn only a
    metric whose single attempt `failed` (or was rejected) may run.
    """
    if row.status in ("ok", "empty"):
        return "already_searched"
    if row.attempts_used >= PHASE1_MAX_ATTEMPTS:
        return "no_attempt_left"
    if turn > 1 and not (row.status == "failed" and row.attempts_used == 1):
        return "not_retry_eligible"
    return None


def _admit_calls(
    calls: Sequence[PreparedCall],
    ledger: dict[str, MetricSearchOutcome],
    turn: int,
) -> tuple[list[PreparedCall], list[tuple[PreparedCall, str]]]:
    """Budget check before execution: split admitted calls into executable and not-executed.

    Checked in message order. The first call for a metric in a turn may run (and spends one
    attempt); a second call for the same metric in the same turn is not executed. Mutates
    `attempts_used` for admitted calls only; statuses are set after shaping.
    """
    admitted: list[PreparedCall] = []
    refused: list[tuple[PreparedCall, str]] = []
    seen: set[str] = set()
    for call in calls:
        label = call.metric_labels[0] if call.metric_labels else None
        if label is None or label not in ledger:
            # The guard enforces a known label; trust it, but never execute an unattributable call.
            refused.append((call, "unattributed"))
            continue
        if label in seen:
            refused.append((call, "duplicate_in_turn"))
            continue
        reason = _refusal_reason(ledger[label], turn)
        if reason is not None:
            refused.append((call, reason))
            continue
        seen.add(label)
        ledger[label].attempts_used += 1
        admitted.append(call)
    return admitted, refused


def _label_from_raw(raw_arguments: str) -> str | None:
    """The `metric_label` string a rejected call carried, if its arguments decode to one."""
    try:
        decoded = json.loads(raw_arguments)
    except (ValueError, TypeError):
        return None
    if isinstance(decoded, dict) and isinstance(decoded.get("metric_label"), str):
        return decoded["metric_label"]
    return None


def _attribute_rejected_turn(
    outcomes: Sequence[RejectedCallOutcome],
    ledger: dict[str, MetricSearchOutcome],
    turn: int,
) -> tuple[str, ...]:
    """A rejected message spends one attempt for every in-set metric it named (once per metric).

    The guard is all-or-nothing, so every metric in the rejected turn loses that turn's attempt
    and is marked `failed` (kind `rejected`). Metrics that could not have run this turn (terminal,
    out of attempts, or not retry-eligible) are left unchanged. Returns the attributed labels.
    """
    attributed: list[str] = []
    for outcome in outcomes:
        label = _label_from_raw(outcome.raw_arguments)
        if label is None or label not in ledger or label in attributed:
            continue
        row = ledger[label]
        if _refusal_reason(row, turn) is not None:
            continue
        row.attempts_used += 1
        row.status = "failed"
        row.failure_kind = "rejected"
        attributed.append(label)
    return tuple(attributed)


def _retry_eligible(ledger: dict[str, MetricSearchOutcome]) -> tuple[str, ...]:
    """Labels whose single attempt failed or was rejected and whose retry is unused."""
    return tuple(
        label
        for label, row in ledger.items()
        if row.status == "failed" and row.attempts_used == 1
    )


def _status_counts(ledger: dict[str, MetricSearchOutcome]) -> dict[str, int]:
    counts = {"ok": 0, "empty": 0, "failed": 0, "not_searched": 0}
    for row in ledger.values():
        counts[row.status] += 1
    return counts


def _failure_phrase(kind: str) -> str:
    """A gateway failure kind in a few words for the LLM (no retry flag)."""
    return _FAILURE_PHRASES.get(kind, "the search did not complete")


def _tool_message(tool_call_id: str, payload: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(payload, ensure_ascii=False),
    }


def _shape_web_search(
    tool_call_id: str,
    metric_label: str,
    outcome: WebSearchResult | ToolFailure,
) -> _ShapedToolResult:
    """R3.M1.2 ordered guard: did it terminate cleanly? (no → `failed`) then content? (ok / empty).

    The result is passed through unchanged; each hit is rendered as `{url, title, text}`, which is
    exactly what evidence `shaped_text` is built from.
    """
    if isinstance(outcome, ToolFailure):
        payload = {
            "status": "failed",
            "metric_label": metric_label,
            "failure": _failure_phrase(outcome.kind),
        }
        return _ShapedToolResult(
            tool_call_id,
            metric_label,
            "failed",
            _tool_message(tool_call_id, payload),
            None,
            outcome.kind,
        )
    status: MetricSearchStatus = "ok" if outcome.excerpts else "empty"
    payload = {
        "status": status,
        "metric_label": metric_label,
        "objective": outcome.objective,
        "search_queries": list(outcome.search_queries),
        "hits": [
            {"url": hit.url, "title": hit.title, "text": hit.text} for hit in outcome.excerpts
        ],
    }
    return _ShapedToolResult(
        tool_call_id, metric_label, status, _tool_message(tool_call_id, payload), outcome, None
    )


def _shape_not_executed(
    tool_call_id: str, metric_label: str | None, reason: str
) -> _ShapedToolResult:
    """A `failed` tool message for an admitted call the budget did not let run."""
    payload = {
        "status": "failed",
        "metric_label": metric_label,
        "failure": _NOT_EXECUTED_PHRASES.get(reason, "not run"),
    }
    return _ShapedToolResult(
        tool_call_id, metric_label, "failed", _tool_message(tool_call_id, payload), None, reason
    )


def _shape_rejected(
    outcome: RejectedCallOutcome, ledger: dict[str, MetricSearchOutcome]
) -> _ShapedToolResult:
    """A `failed` tool message for one kept call of a guard-rejected message."""
    label = _label_from_raw(outcome.raw_arguments)
    if label not in ledger:
        label = None
    if outcome.category == "withheld":
        failure = "not run: another call in this message was invalid, so none ran"
    else:
        failure = "rejected by validation: " + ", ".join(outcome.reason_codes)
    payload = {"status": "failed", "metric_label": label, "failure": failure}
    return _ShapedToolResult(
        outcome.tool_call_id,
        label,
        "failed",
        _tool_message(outcome.tool_call_id, payload),
        None,
        "rejected",
    )


def _apply_shaped(row: MetricSearchOutcome, item: _ShapedToolResult) -> None:
    """Set a metric's status from its executed call's shaped result."""
    row.status = item.status
    row.failure_kind = item.failure_kind if item.status == "failed" else None


def _shaped_text(title: str | None, text: str) -> str:
    """Evidence text = the hit's title + newline + its excerpts, as the tool message carries them."""
    return f"{title}\n{text}" if title else text


def _record_web_evidence(
    shaped: Sequence[_ShapedToolResult], store: MetricsSourceContent
) -> int:
    """Record one `web` evidence item per hit of every `ok` result; returns the hits recorded."""
    recorded = 0
    for item in shaped:
        if item.status != "ok" or item.result is None:
            continue
        for hit in item.result.excerpts:
            store.record(
                "web",
                hit.url,
                _shaped_text(hit.title, hit.text),
                item.result.retrieved_at,
                item.metric_label,
            )
            recorded += 1
    return recorded


def create_specific_metric_resolution(
    settings: Settings,
    *,
    llm_caller: StructuredLLMCaller | None = None,
) -> SpecificMetricResolution:
    """Composition root for R3: build the MCP gateway and resolve caller ownership.

    The gateway opens no session here (no I/O at construction); `run_specific_metric_resolution`
    opens and closes it. Standalone (no `llm_caller`) builds its own caller and owns it; the
    DeepSearch feature injects a shared caller it closes itself.
    """
    if llm_caller is None:
        caller = create_structured_llm_caller(settings)
        owns_caller = True
    else:
        caller = llm_caller
        owns_caller = False
    return SpecificMetricResolution(
        tool_gateway=create_mcp_tool_gateway(settings),
        llm_caller=caller,
        owns_caller=owns_caller,
        breaker_threshold=settings.metric_resolution_breaker_threshold,
    )
