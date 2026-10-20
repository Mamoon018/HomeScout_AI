# R3.M1.1 — Implementation & Dry-Run Traceflow

> Companion to `R3_Specific_Metric_Resolution_spec.md` (sub-component **R3.M1.1 — Build the
> Phase-Scoped Tool Catalog and Call Guard**). Supersedes the earlier **C3.1.3** dry-run
> traceflow. Renames applied: `C3.1.3` → **R3.M1.1**; the two client prerequisites keep their
> IDs (**C3.1.1** MCP gateway, **C3.1.2** shared-caller tool turn); the gateway's M3 path is now
> `search_web` / `map_site` / `scrape_page` / `scrape_pages` (map→scrape), not crawl; the catalog
> `context` is one of four values: `website_discovery`, `metric_web_search`, `site_map`,
> `metric_scrape`.

---

## 0. What this dry run is for

Prove the **two R3.M1.1 abstractions** work as a reusable unit *before* any core-workflow
sub-component (R3.M1.3 discovery, R3.M1.4 phase loop) is built to call them:

1. **Build LLM-Facing Tool Catalog** — `build_tool_catalog(raw_tool_definitions, context)` *(name
   illustrative)*. Pure schema derivation; no LLM, no execution.
2. **Guard Proposed Calls** — `guard_proposed_calls(proposed_tool_calls, tool_catalog, context,
   validation_context)` *(name illustrative)*. Whole-message validation; no execution, no history
   mutation, no retry decision.

Both are **reusable** and not tied to `website_discovery` or `web_search`; the dry run exercises
them through two contexts to prove that.

---

## 1. Dry-run strategy (satisfies the stated requirement)

**Requirement:** prefer *limited-scoped live calls (MCP + LLM)* plus the dummy data needed to make
those calls work, and have a sample dry run that **genuinely works** through both abstractions.

So this plan is **not** fully simulated. It makes real, tightly-bounded live calls at exactly the
two boundaries that the abstractions depend on, and injects dummy data only where the *core
workflow* (not yet built) would normally provide it.

| Element | Dry-run treatment | Why |
|---|---|---|
| **C3.1.1 gateway `open()` + `tools/list`** | **LIVE** (real MCP handshake to Parallel; Firecrawl optional) | The catalog builder's whole job is to restrict a **real** raw MCP schema. A hand-written fixture can't prove `$ref`/`$defs` preservation against the server's actual schema. One `open()` ≈ no billed search calls, just `tools/list`. |
| `raw_tool_definitions` | **REAL** (captured from the live `tools/list`) | This is abstraction #1's primary input. |
| `context` | **DUMMY/selected by harness** (`website_discovery`, then `metric_web_search`) | The core workflow (R3.M1.3/R3.M1.4) normally picks this; the harness stands in for that caller. |
| **C3.1.2 `call_turn()`** | **LIVE** (real OpenAI→Groq tool turn) | Produces abstraction #2's primary input — a *genuine* assistant `tool_calls` message, not a fixture. Proves the catalog we built is actually accepted and used by a real model. |
| Amenity identity / address, search instructions, metric set | **DUMMY** (hard-coded in harness) | Supplied by R3.M1.3/R3.M1.5 in production; the harness injects a representative amenity + a small metric set. |
| `validation_context` (metric-label membership facts) | **DUMMY** (small metric-label set) | Normally built from amenity state; harness supplies `{"metric_labels": [...]}` for the metric pass and `None` for discovery. |
| **The two abstractions themselves** | **REAL** | The thing under test. |
| Execute one accepted call (`search_web`) | **LIVE, mandatory** | Closes the loop end-to-end so the run genuinely works, not just validates. 1 billed Parallel call. Sits beyond the two abstractions' contract boundary (execution is R3.M1.2/R3.M1.4), but is a required part of this dry run. |
| Downstream Guard steps 3/4/5, R3.M1.2 result shaping, gateway dispatch, retries | **NOT RUN** | Out of R3.M1.1 contract scope; the harness only inspects the two abstractions' outputs. |

**Scope caps (keep it "limited"):** one amenity; two context passes; at most **1 live LLM tool
turn per pass**; exactly **1** billed search call (the mandatory end-to-end leg); one
gateway `open()`/`close()`. Firecrawl is not required — `site_map`/`metric_scrape` can be covered
with a captured Firecrawl `tools/list` if its key is present, otherwise skip to keep scope tight.

**Pass A** proves the happy path on the simplest context (`website_discovery`, no `metric_label`,
`validation_context=None`). **Pass B** reuses the *same two functions* on `metric_web_search` to
exercise `metric_label` and the separate validator in **both directions** — case **B1** forces a
genuine rejection (one invalid label withholds a valid sibling) and case **B2** proves acceptance
when every label is valid. Both cases use crafted proposed-calls fixtures (the run's only fixtures,
no second live LLM call) so the two validator branches fire deterministically.

---

## 2. Traceflow — Pass A (`website_discovery`, live MCP + live LLM)

```text
R3.M1.1 — IMPLEMENTATION & DRY-RUN TRACEFLOW
Pass A context: website_discovery
══════════════════════════════════════════════════════════════════════

IMPLEMENT NOW (under test)
  • Build LLM-Facing Tool Catalog          (R3.M1.1 step 1)
  • Guard Proposed Calls                   (R3.M1.1 step 2)
  • RawToolDefinition type + context union + additional-validator interface

LIVE IN THIS DRY RUN
  • C3.1.1 gateway open() + tools/list     → real raw_tool_definitions
  • C3.1.2 call_turn()                      → real assistant tool_calls

SIMULATED (harness stands in for the not-yet-built caller)
  • R3.M1.3 / R3.M1.5 role: context selection, dummy amenity identity,
    search instructions, validation_context


┌─ DRY-RUN HARNESS — ACTS AS THE R3.M1.3 DISCOVERY CALLER ────────────┐
│                                                                     │
│ (1) gw = Gateway(settings); await gw.open()      ◀── LIVE MCP       │
│     • real streamable-HTTP handshake to Parallel                    │
│     • capability check passes (web_search present)                  │
│     • raw_tool_definitions captured from tools/list:                │
│                                                                     │
│       raw_tool_definitions = {                                      │
│         "parallel": {                                               │
│           "web_search": RawToolDefinition(                          │
│             name="web_search",                                      │
│             description="…server text…",                            │
│             input_schema={ …COMPLETE live JSON Schema… })           │
│         }                                                           │
│       }                                                             │
│                                                                     │
│ (2) context = "website_discovery"   (harness selects; MCP/LLM do    │
│     not choose this)                                                │
│                                                                     │
│ Server grouping preserved (parallel/web_search); the live schema    │
│ carries fields discovery must exclude, so restriction is really     │
│ exercised against a real schema, not a fixture.                     │
└─────────────────────────────────────────────────────────────────────┘
  │
  │ REAL CALL  ── build_tool_catalog(raw_tool_definitions, context)
  ▼
┌─ REAL STEP 1 — BUILD LLM-FACING TOOL CATALOG ──────────────────────┐
│ • Select server+tool by context policy → parallel / web_search.     │
│   Missing selected server/tool ⇒ catalog-construction failure       │
│   (no other server, no invented schema, no LLM).                    │
│ • Derive a restricted copy of the live input_schema:                │
│     - allowlist: objective, search_queries  (required)              │
│     - ≥1 search query; additionalProperties disallowed              │
│     - preserve retained fields' types/descriptions/compatible        │
│       constraints and any $ref + transitive $defs; do not inline     │
│     - validate refs resolve; fail explicitly if not                 │
│     - NO metric_label in this context                               │
│     - raw definition in state left UNCHANGED                        │
│ • Adapt to C3.1.2 function-tool shape:                              │
│     {type:"function", function:{name, description, parameters}}     │
└─────────────────────────────────────────────────────────────────────┘
  │ ACTUAL OUTPUT  tool_catalog: list[dict]
  ▼
tool_catalog = [
  { "type":"function",
    "function":{
      "name":"web_search",
      "description":"…preserved…",
      "parameters":{
        "type":"object",
        "properties":{
          "objective":{"type":"string", …},
          "search_queries":{"type":"array","items":{"type":"string"},
                            "minItems":1, …}
        },
        "required":["objective","search_queries"],
        "additionalProperties":false
      }}}
]
  │
  ▼
┌─ CHECKPOINT A1 — CATALOG CONTRACT ─────────────────────────────────┐
│ • Only web_search exposed.                                          │
│ • objective + search_queries present with discovery constraints.    │
│ • metric_label and app-controlled fields absent.                    │
│ • Any retained $ref resolves against carried $defs.                 │
│ • raw_tool_definitions unchanged (deep-equality vs captured copy).  │
│ • Shape matches what C3.1.2 call_turn() accepts as `tools`.         │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ LIVE C3.1.2 HANDOFF — call_turn() ───────────────── LIVE LLM ──────┐
│ messages   = discovery instructions + DUMMY amenity identity        │
│              e.g. {"name":"Example Zoo","city":"Berlin"}            │
│ tools      = the ACTUAL tool_catalog from Step 1                    │
│ tool_choice= caller-selected (e.g. "required")                      │
│                                                                     │
│ Real OpenAI→Groq tool turn. Response adapter yields the genuine     │
│ assistant tool_calls, e.g.:                                         │
│ proposed_tool_calls = [                                             │
│   { id:"call_disc_1", name:"web_search",                            │
│     arguments: '<JSON STRING>'  // e.g.                             │
│       {"objective":"Find the official site for Example Zoo",        │
│        "search_queries":["Example Zoo Berlin official website"]} } ]│
│                                                                     │
│ This proves the built catalog is accepted/used by a real model.     │
└─────────────────────────────────────────────────────────────────────┘
  │
  │ REAL CALL  ── guard_proposed_calls(
  │                 proposed_tool_calls,
  │                 tool_catalog   = actual Step-1 output,
  │                 context        = "website_discovery",
  │                 validation_context = None)
  ▼
┌─ REAL STEP 2 — GUARD PROPOSED CALLS (generic call guard) ──────────┐
│ 1 no calls → no_tool_calls (category null)                          │
│ 2 outer fields + unique tool-call IDs → else invalid_call_structure │
│ 3 name exact-match vs catalog → else out_of_catalog                 │
│ 4 decode arguments JSON string → else in_catalog/invalid_argument_json│
│ 5 validate decoded args vs tool schema → else in_catalog            │
│ 6 validation_context is None here ⇒ skip data-dependent validator   │
│ 7 collect ALL detectable errors; skip checks whose prereqs failed;  │
│   no trim/dedupe/normalize; no blank-string checks                  │
│ 8 any error ⇒ REJECT whole message; else ACCEPT all calls in order  │
└─────────────────────────────────────────────────────────────────────┘
  │
  ├─ ACCEPTED
  │   { decision:"accepted",
  │     validated_calls:[{ tool_call_id:"call_disc_1",
  │                        tool_name:"web_search",
  │                        arguments:{objective:"…",
  │                                   search_queries:["…"]} }],
  │     errors:[] }
  │
  └─ REJECTED
      { decision:"rejected", validated_calls:[],
        errors:[{reason_code, explanation, call_index, tool_call_id,
                 tool_name, category, field_path}, …] }
  │
  ▼
┌─ CHECKPOINT A2 — GUARD CONTRACT ───────────────────────────────────┐
│ Accepted: all calls in order; arguments decoded & preserved         │
│           (no normalization); errors == [].                         │
│ No execution, no history mutation, no retry decision occurred.      │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼  (MANDATORY end-to-end leg — 1 billed call, beyond R3.M1.1 contract)
┌─ LIVE EXECUTION (REQUIRED) — prove "genuinely works" ──────────────┐
│ For the single accepted call, the harness calls the gateway op the  │
│ app would run (NOT the LLM-supplied anything the app owns):         │
│   await gw.search_web(objective=…, search_queries=…)   ◀── LIVE MCP │
│ Assert a typed SearchResults comes back. Then gw.close().           │
│ (In production this dispatch + its tool-message shaping is R3.M1.2 / │
│  R3.M1.4, not R3.M1.1 — run here to close the loop end-to-end.)     │
└─────────────────────────────────────────────────────────────────────┘

DRY RUN (Pass A) ENDS AT THE CONTRACT BOUNDARY
──────────────────────────────────────────────────────────────────────
Accepted output → ready for future R3.M1.1 step 5 (prepare admitted calls)
                  → gateway dispatch (R3.M1.4) / result shaping (R3.M1.2)
Rejected output → ready for future R3.M1.1 steps 3 (rejection outcomes)
                  and 4 (replay-history sanitize)
The harness inspects outputs only; it builds none of those downstream steps.
```

---

## 3. Traceflow — Pass B (`metric_web_search`, reuse + validator + rejection)

Same two functions, different context — proves reuse and exercises the pieces Pass A can't:
`metric_label` in the catalog, the **separate validator** via `validation_context`, and **both
guard decisions** — a genuine **whole-message rejection** with a withheld valid sibling (**B1**) and
a clean **acceptance** when every label is valid (**B2**). The catalog is built once; two crafted
proposed-calls fixtures (the run's only fixtures) drive the two branches deterministically.

```text
R3.M1.1 — DRY RUN Pass B
context: metric_web_search     validation_context: {"metric_labels":["ticket_price","opening_hours"]}
══════════════════════════════════════════════════════════════════════

HARNESS (reuses live raw_tool_definitions captured in Pass A — no 2nd open)
  context = "metric_web_search"
  │
  │ REAL CALL build_tool_catalog(raw_tool_definitions, "metric_web_search")
  ▼
tool_catalog' = [ web_search with objective + search_queries + metric_label ]
  │
  ▼ CHECKPOINT (CATALOG): metric_label now REQUIRED by the schema; still only web_search;
                          app-owned fields still absent; raw defs still unchanged.
  │
  ├──────────────────── CASE B1 — REJECT (any invalid label) ─────────────────────┐
  │                                                                               │
  │  CRAFTED fixture: one valid label + one not in the set, to force rejection:    │
  │  proposed_tool_calls = [                                                       │
  │    { id:"c1", name:"web_search",                                              │
  │      arguments:'{"objective":"price","search_queries":["x"],                  │
  │                  "metric_label":"ticket_price"}' },        // schema+label valid │
  │    { id:"c2", name:"web_search",                                              │
  │      arguments:'{"objective":"hours","search_queries":["y"],                  │
  │                  "metric_label":"wheelchair_access"}' } ]  // label NOT in set  │
  │    │                                                                          │
  │    │ REAL CALL guard_proposed_calls(..., context="metric_web_search",          │
  │    │              validation_context={"metric_labels":[...]})                  │
  │    ▼                                                                          │
  │  Steps 1–5 pass schema for both; step 6 fires the metric-label validator:     │
  │   • c2's "wheelchair_access" ∉ metric_labels ⇒ in_catalog issue,              │
  │     field_path="arguments.metric_label".                                      │
  │   • step 8: one error ⇒ REJECT whole message; c1 (valid) is WITHHELD.         │
  │    ▼                                                                          │
  │  { decision:"rejected", validated_calls:[],                                   │
  │    errors:[{ reason_code:"metric_label_not_in_set" (validator's code),         │
  │              explanation:"…", call_index:1, tool_call_id:"c2",                 │
  │              tool_name:"web_search", category:"in_catalog",                    │
  │              field_path:"arguments.metric_label" }] }                         │
  │  ┌─ CHECKPOINT B1 (REJECT) ───────────────────────────────────────────────┐   │
  │  │ • Validator fired only because validation_context was supplied.         │   │
  │  │ • Whole-message rejection: valid sibling c1 NOT admitted.               │   │
  │  │ • Error carries category in_catalog + explicit field_path.              │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  └───────────────────────────────────────────────────────────────────────────────┘
  │
  ├──────────────────── CASE B2 — ACCEPT (every label valid) ─────────────────────┐
  │                                                                               │
  │  CRAFTED fixture: both labels in the set, to prove the positive path:          │
  │  proposed_tool_calls = [                                                       │
  │    { id:"d1", name:"web_search",                                              │
  │      arguments:'{"objective":"price","search_queries":["x"],                  │
  │                  "metric_label":"ticket_price"}' },        // valid            │
  │    { id:"d2", name:"web_search",                                              │
  │      arguments:'{"objective":"hours","search_queries":["y"],                  │
  │                  "metric_label":"opening_hours"}' } ]      // valid            │
  │    │                                                                          │
  │    │ REAL CALL guard_proposed_calls(..., context="metric_web_search",          │
  │    │              validation_context={"metric_labels":[...]})                  │
  │    ▼                                                                          │
  │  Steps 1–5 pass; step 6 validator passes BOTH labels; step 8: no errors.      │
  │    ▼                                                                          │
  │  { decision:"accepted",                                                       │
  │    validated_calls:[                                                           │
  │      { tool_call_id:"d1", tool_name:"web_search",                             │
  │        arguments:{objective:"price", search_queries:["x"],                    │
  │                   metric_label:"ticket_price"} },                             │
  │      { tool_call_id:"d2", tool_name:"web_search",                             │
  │        arguments:{objective:"hours", search_queries:["y"],                    │
  │                   metric_label:"opening_hours"} } ],                          │
  │    errors:[] }                                                                │
  │  ┌─ CHECKPOINT B2 (ACCEPT) ───────────────────────────────────────────────┐   │
  │  │ • A correct metric_label genuinely PASSES the validator.                │   │
  │  │ • Both calls admitted in original order; metric_label PRESERVED on each. │   │
  │  │ • No normalization; no execution / history mutation / retry.            │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  └───────────────────────────────────────────────────────────────────────────────┘

Together B1 + B2 prove the validator gate in both directions: reject on an invalid label,
accept (and preserve) on valid ones. Reuse is shown by both running the same two functions
on metric_web_search. Optional 3rd check: same B2 fixture with validation_context=None still
accepts (membership check skipped).
```

> **Optional Firecrawl coverage.** If `FIRECRAWL_API_KEY` is present, repeat Step 1 only for
> `site_map` (expect **no** LLM-settable args) and `metric_scrape` (expect candidate `id` +
> required `metric_label`, URL/formats absent) against a live Firecrawl `tools/list`. No live
> scrape needed — this is a catalog-shape assertion, so it stays within scope.

---

## 4. What the harness must provide vs. assert

**Provides (dummy / selection):** `context` per pass; dummy amenity identity + discovery/metric
instructions for the message; `validation_context` (`None` for A; a small `metric_labels` set for
B); the metric-label additional-validator implementation (the `validate(arguments,
validation_context) -> list[ValidationIssue]` contract); the two Pass-B crafted proposed-calls fixtures (B1 reject, B2 accept).

**Asserts (the two abstractions' contract):** catalog contents/shape and raw-schema immutability
(A1, Pass-B catalog checkpoint); guard decision, ordering, argument preservation, and error
metadata — acceptance (A2, B2) and whole-message rejection with a withheld sibling (B1); that no
execution/history-mutation/retry happened inside either abstraction.

**Keys needed:** `OPENAI_API_KEY` + `GROQ_API_KEY` (live `call_turn`), `PARALLEL_API_KEY` (live
`open()`/`tools/list` **and** the mandatory execution leg). `FIRECRAWL_API_KEY` only for the
optional Firecrawl catalog-shape pass.

**Cost envelope:** 1 gateway `open()` (`tools/list`, unbilled search-wise) + 1 live LLM tool turn
(Pass A) + exactly 1 billed Parallel `search_web` (the mandatory end-to-end leg). Pass B adds no
live calls (fixture-driven).
