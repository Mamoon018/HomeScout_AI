# R3 Promotion — Implementation Plan

> **Status: IMPLEMENTATION PLAN.** Built on `R3_Specific_Metric_Resolution_proposal.md` (the agreed
> initial spec). Execute phases in order; each phase is independently reviewable and leaves the
> tree green.

---

## Scope

This plan executes the **structural promotion** of "R2 Mechanism 3" into its own responsibility
class, **R3 — `SpecificMetricResolution`**. It does **not** implement R3's workflow
(the C3.1.3–C3.1.7 / C3.2.1–C3.2.5 sub-components). Per the draft spec, each sub-component's spec is
finalized before it is built, and several carry open decisions (proposal §8). So R3 lands here as a
**skeleton**: it owns the MCP gateway and exposes `run_specific_metric_resolution(state)` as a
not-yet-implemented entry point — the same placeholder role `AmenitySearch` plays for M3 today
(gateway held, never opened). Sub-component implementation is the *next* plan (see "After this plan").

**Not in scope:** implementing any R3 stage; wiring R3 into `DeepSearch.run()` as a live call
(the entry method is a stub until its workflow exists); resolving the proposal §8 open decisions.

## Assumptions (verified against live code)

- RC9 record contracts + state fields already exist in `schemas.py` — **no schema work** (proposal §6).
- The MCP gateway (`src/clients/mcp_tools.py`) and the shared caller's tool turn
  (`src/clients/llm_provider.py`) are already built — unchanged here, only re-injected.
- `DeepSearch.run()` runs R1 only; R2 is not wired into it — so no live call graph breaks.
- `AmenitySearch` keeps `llm_caller`/`owns_caller` (D-F): R2's unbuilt relevance/narrowing may need it.

---

## Phase 1 — Spec & context-doc refactor

Pure documentation; no code. Can run first (or in parallel with code) so the specs match the target
before/while code moves.

1.1 **Rename the draft spec.** `R2_Mechanism_3_draft_spec.md` → `R3_Specific_Metric_Resolution_spec.md`
    (retitle header accordingly). Keep the "Carried forward under the R3 promotion" block.

1.2 **Apply the ID crosswalk** (proposal §5) across that spec: `C3.1.3→R3.M1.1`, `C3.1.4→R3.M1.2`,
    `C3.1.5→R3.M1.3`, `C3.1.6→R3.M1.4`, `C3.1.7→R3.M1.5`, `C3.2.1→R3.M2.1` … `C3.2.5→R3.M2.5`.
    `C3.1.1`/`C3.1.2` stay flagged as already-built client prerequisites (not R3 stages).
    Mechanical sweep; a cross-reference check afterwards (no dangling `C3.x`).

1.3 **Retarget bindings** in that spec: every "on/into `AmenitySearch`" (C3.1.1 test seam, C3.1.7
    placement/wiring, `create_amenity_search`) → `SpecificMetricResolution` /
    `create_specific_metric_resolution`; the entry method is `run_specific_metric_resolution`.

1.4 **Context doc (`deep_search_context.md`):**
    - Add a new **R3 — Specific Metric Resolution** responsibility section (Scope, User, Environment,
      Problem relevance, Actual Problem Statement, Workflow, Mechanisms), seeded from proposal §3,
      mirroring the R1/R2 section structure.
    - **Trim R2** to "Amenity Discovery & Baseline Profiling" (proposal §3): drop the LLM-defined
      resolution and merge clauses from R2's problem statement/wants/environment.
    - Update the "R2 is its own class" framing (`:2240`) — R2 no longer owns metric resolution.
    - Update the feature-coordination note: sequence R1 → R2 → R3; R3 owns the combined
      `AmenityMetricsSet`.

**Verify:** no remaining `C3.x` in the renamed spec; R2 and R3 sections are symmetric; grep for stale
"R2 Mechanism 3" references across both docs.

---

## Phase 2 — Create the R3 class + factory

2.1 **New file `backend/src/services/deep_search/specific_metric_resolution.py`:**
    - `class SpecificMetricResolution` with `__init__(self, *, tool_gateway: ToolGateway,
      llm_caller: StructuredLLMCaller | None = None, owns_caller: bool = True, <semaphore/config
      defaults>)`. Store deps; build no sessions at construction (mirrors current gateway contract).
    - `async def run_specific_metric_resolution(self, state: AmenitySearchState) -> AmenitySearchState`
      — **skeleton**: raise `NotImplementedError("R3 workflow not yet implemented; see "
      "R3_Specific_Metric_Resolution_spec.md")`. (Keeps the entry point and signature fixed; the
      gateway `open()`/`aclose()` session scope and the two-mechanism orchestration land with the
      sub-components.)
    - `async def aclose(self)` — close the gateway (`await self._tool_gateway.aclose()`); close the
      caller only if `owns_caller`.
    - `def create_specific_metric_resolution(settings, *, llm_caller=None)` — build the gateway via
      `create_mcp_tool_gateway(settings)`; `owns_caller` logic identical to `create_amenity_search`
      (own the caller when none injected, else `owns_caller=False`).

**Verify:** module imports; `create_specific_metric_resolution(settings)` constructs without I/O;
`aclose()` is safe on a never-opened gateway.

---

## Phase 3 — Strip the gateway from `AmenitySearch`

3.1 `amenity_search.py` `__init__`: remove the `tool_gateway: ToolGateway` keyword param and its M3
    comments. **Keep** `llm_caller`/`owns_caller`.

3.2 `aclose()`: remove the gateway-close branch. Keep places/routes/caller closing.

3.3 `create_amenity_search`: remove the `tool_gateway=create_mcp_tool_gateway(settings)` argument and
    the now-unused `ToolGateway`/`create_mcp_tool_gateway` imports.

**Verify:** `AmenitySearch` no longer references the gateway; M1 methods untouched; imports clean.

---

## Phase 4 — Rewire `DeepSearch`

4.1 `DeepSearch.__init__`: add `specific_metric_resolution: SpecificMetricResolution`; store it.

4.2 `create_deep_search`: build R3 via `create_specific_metric_resolution(settings,
    llm_caller=llm_caller)` (shared caller injected, `owns_caller=False`); keep injecting the shared
    caller into R1 and R2 (D-F). Pass R3 into `DeepSearch`.

4.3 `aclose()`: close R1, R2, **R3**, then the shared caller once (D6 — the feature is the single
    owner).

4.4 `run()`: **unchanged** (R1 only) — R3's entry method is a stub, so no live R2→R3 call yet. Add a
    one-line comment that R1 → R2 → R3 sequencing lands when R3's workflow exists.

**Verify:** `create_deep_search(settings)` wires all three; `aclose()` closes R3's gateway exactly
once; D6 single-owner intact.

---

## Phase 5 — Fix the regression surface (proposal §9)

All breaks are construction-only — drop the `tool_gateway` kwarg, no behaviour change. Only callers
that **pass** `tool_gateway` break; anything that goes through `create_amenity_search()` or
`create_mcp_tool_gateway()` is unaffected. Verified against the tree, the real break set is **4
files, one line each**:

5.1 **M1 tests** (in `backend/tests/services/deep_search/`, *not* `feature_tests/`):
    - `test_result_attachment.py:30` — drop `tool_gateway=None` from the direct `AmenitySearch(...)`.
    - `test_place_discovery.py:73` — remove the `kwargs.setdefault("tool_gateway", None)` line in the
      `_search` helper (and its comment).
    - `test_accessibility_enrichment.py:125` — remove the `kwargs.setdefault("tool_gateway", None)`
      line in the `_search` helper (and its comment).
    Re-run each; expect green (M1 behaviour unchanged).

5.2 **Sample run:** `result_attachment_sample_run.py:233` — drop `tool_gateway=None` from the direct
    `AmenitySearch(...)`. **No other sample run changes:** `place_discovery_sample_run.py:91` and
    `accessibility_enrichment_sample_run.py:142` build via `create_amenity_search(settings)`, and
    `mcp_tool_gateway_sample_run.py:576` builds the gateway directly via `create_mcp_tool_gateway` —
    none passes `tool_gateway`, so all three are untouched.

5.3 **Sanity re-run (no change expected):** `test_c3_1_1_mcp_tool_gateway.py` and
    `test_c3_1_2_structured_llm_caller.py` (both use the gateway / caller directly, never through
    `AmenitySearch`), and the R1 tests.

---

## Phase 6 — Verify

6.1 Run the full `deep_search` test suite: M1 (discovery/enrichment/attachment) green, gateway/caller
    green, no import/collection errors.

6.2 Grep sweep: no remaining `tool_gateway` reference on `AmenitySearch`; no dangling `C3.x` in the
    renamed spec; no stale "R2 Mechanism 3" where R3 is now meant.

6.3 Confirm `create_deep_search(settings)` constructs and `await deep_search.aclose()` runs clean
    (add a minimal construction/teardown test for the coordinator — the gap noted in proposal §9).

---

## Does-not-close (carried forward)

Proposal §8 open decisions stay open — they are R3 **workflow** concerns, untouched by this
structural plan: C3.1.5 postal-code degrade path; C3.2.2 body validation; C3.2.3 conformer; C3.2.4
provenance match. Recorded in both specs under "Carried forward under the R3 promotion".

## After this plan — sub-component implementation

Implement R3's workflow sub-component by sub-component in the draft spec's dependency order, each
after its open decision is resolved: **R3.M1** (R3.M1.1 catalog+guard → R3.M1.2 shape → R3.M1.3
website discovery → R3.M1.4 phase loop+triage → R3.M1.5 pipelines/entry) then **R3.M2** (R3.M2.1
schema+instruction → R3.M2.2 resolution turn → R3.M2.3 conform → R3.M2.4 provenance → R3.M2.5
combine → `AmenityMetricsSet`). The entry method's `NotImplementedError` is replaced when R3.M1.5
lands; `DeepSearch.run()` gains the R2 → R3 call at that point.

## Suggested commit/PR slicing

- **PR 1 — Phase 1** (spec/doc refactor). Docs only.
- **PR 2 — Phases 2–6** (R3 skeleton, AmenitySearch strip, DeepSearch rewire, test/sample fixes,
  verify). One self-contained code refactor, tree green.

(Or a single PR if you prefer the docs and the structural move to land together.)
