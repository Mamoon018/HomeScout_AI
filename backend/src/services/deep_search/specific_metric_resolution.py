"""Responsibility 3 — Specific Metric Resolution.

This module holds the `SpecificMetricResolution` responsibility class. Its entry method
`run_specific_metric_resolution` is being built sub-component by sub-component, following
`feature_context/R3_Specific_Metric_Resolution_spec.md` and `feature_context/R3_M1_Traceflow.md`.

**Built so far: through STEP 3 (R3.M1.3 — website-URL discovery).** `run_specific_metric_resolution`
opens the gateway, builds `plan_index` (STEP 1), derives the eligible work items (STEP 2, RC7), runs
the R3.M1.3 discovery batch (STEP 3) to populate `state.website_search_results` /
`state.discovery_search_results` / `state.official_gate_results`, then closes the gateway and returns
`state`. **Not yet built:** STEP 4 amenity pipelines (R3.M1.4), STEP 5 post-gather sweep, STEP 6
combine (R3.M2). `state.amenity_records` is therefore still `None` after this partial run.

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
from dataclasses import dataclass
from datetime import datetime, timezone
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
)
from src.services.deep_search.feature_prompts.website_discovery_instruction import (
    build_discovery_search_instruction,
    build_website_selection_instruction,
)
from src.services.deep_search.feature_schemas.schemas import (
    WEBSITE_SELECTION_SCHEMA_NAME,
    AmenitySearchState,
    CategoryMetricPlan,
    DepthLevel,
    DiscoveryCandidate,
    DiscoverySearchRecord,
    MetricSpec,
    OfficialGateRecord,
    PredefinedMetricsRecord,
    WebsiteSearchResult,
    WebsiteSelectionResult,
    website_selection_json_schema,
)
from src.services.deep_search.official_url_gate import official_url_gate
from src.services.deep_search.phase_tool_catalog import (
    build_tool_catalog,
    guard_proposed_calls,
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
    ) -> None:
        # Injected (C3.1.1). It is the locked test seam, so the service never sees MCP types. No
        # session is opened at construction; `run_specific_metric_resolution` opens and closes it.
        self._tool_gateway = tool_gateway
        # Shared caller for the R3.M1 tool turns and R3.M2 structured turns (C3.1.2). When the
        # DeepSearch feature injects one, `owns_caller` is False and the feature closes it.
        self._llm_caller = llm_caller
        self._owns_caller = owns_caller

    async def run_specific_metric_resolution(
        self, state: AmenitySearchState
    ) -> AmenitySearchState:
        """R3 entry point — built through STEP 3 (R3.M1.3 website-URL discovery) only.

        Opens the gateway, builds `plan_index` (STEP 1), derives the eligible work items (STEP 2),
        runs the discovery batch (STEP 3) to fill `state.website_search_results` /
        `.discovery_search_results` / `.official_gate_results`, then closes the gateway. STEP 4–6
        (amenity pipelines, sweep, combine) are not yet implemented, so `state.amenity_records`
        stays `None`.
        """
        if self._llm_caller is None:
            # Discovery Stage 1 needs the shared caller; a None caller is a composition-root bug.
            raise MetricResolutionProviderError(
                "SpecificMetricResolution has no LLM caller; cannot run discovery",
                stage="run_specific_metric_resolution",
            )
        await self._tool_gateway.open()
        try:
            raw_tool_definitions = self._tool_gateway.get_tool_definitions()
            plan_index = self._build_plan_index(state)  # STEP 1
            work_items = self._derive_work_items(state, plan_index)  # STEP 2
            await self._run_discovery_batch(state, work_items, raw_tool_definitions)  # STEP 3
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
                        work_item, rec, raw_tool_definitions, batch_id
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
    ) -> tuple[WebsiteSearchResult, DiscoverySearchRecord | None]:
        """Stage 1 for one declined item: search → index → select → resolve. Degrades to `none`."""
        key = (work_item.category_id, work_item.place_id)
        search = await self._run_discovery_search(rec, raw_tool_definitions, key, batch_id)
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
            rec.name, rec.address, candidates, id_url_map, key, batch_id
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
            turn = await self._llm_caller.call_turn(
                messages=messages,
                tools=catalog,
                tool_choice="required",
                stage="r3_m1_3_discovery_search",
                provider_error_cls=MetricResolutionProviderError,
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
                body, _answered_by = await self._llm_caller.call_structured(
                    instruction=instruction,
                    user_content=user_content,
                    json_schema=schema,
                    schema_name=WEBSITE_SELECTION_SCHEMA_NAME,
                    stage="r3_m1_3_website_selection",
                    provider_error_cls=MetricResolutionProviderError,
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
    )
