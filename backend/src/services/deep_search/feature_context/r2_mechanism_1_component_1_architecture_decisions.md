# Responsibility 2 — Mechanism 1, Component M1.1 (Place Discovery): Architecture and Modularity Decisions

Section 2 of the M1.1 plan. File and workflow structure is in
[r2_mechanism_1_component_1_implementation_plan.md](r2_mechanism_1_component_1_implementation_plan.md).

Scope of this file: **Component M1.1 (Place Discovery) only** — its three sub-components
(M1.1.a Request Builder, M1.1.b Execution and Failure Handling, M1.1.c Canonical Set
Assembly and Dedup). Accessibility Enrichment (M1.2) and Attachment (M1.3) are out of scope
and are named only where M1.1 must leave a seam for them.

## Baseline this fits into

- Responsibility 1 already produces `state.category_metric_plans: list[CategoryMetricPlan]`
  (see [schemas.py](../feature_schemas/schemas.py)). Each plan carries `category_id`,
  `taxonomy_node`, `depth`, `predefined_metrics: list[PredefinedMetric]`, and
  `specific_metrics`. This list is R2's only requirement input.
- `taxonomy_node` values are now Google place-type strings (e.g. `swimming_pool`, `bakery`,
  `dog_park`), so a node is used directly as a Google `primaryType`. No taxonomy→type
  resolver is built (former sub-component M1.1.a is removed).
- A synchronous Places wrapper already exists:
  [google_places.py](../../../clients/google_places.py) exposes
  `create_places_client(settings) -> GooglePlacesClient` and `search_nearby(...)`. That
  method always attaches `routing_parameters` and bills every call at one broad
  `SEARCH_NEARBY_FIELD_MASK`, and maps SDK errors to the
  [places.py](../../../exceptions/places.py) tree
  (`PlacesClientError`, `PlacesTimeoutError`, `PlacesRateLimitError`,
  `PlacesInvalidRequestError`). It is consumed today only by
  `services/google_places_sample_run.py`.
- Config is `pydantic-settings` with `google_maps_api` present and an `@lru_cache
  get_settings()`. Composition roots are `create_x(settings)` factories beside the class
  they build (R1 uses `create_requirement_interpretation` / `create_llm_providers`).
- In-process state is a mutable `@dataclass`; contracts live in one
  `feature_schemas/schemas.py`; service failures are a typed tree carrying a `stage`
  ClassVar; stage methods log JSON under `homescout.places` / `homescout.deep_search` and a
  sample runner prints.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** one concrete R2 responsibility class whose methods are the M1.1 workflow and its
  stages, calling one injected Places capability. Per-category discovery runs concurrently,
  bounded, over independent categories; the call is awaited directly on the async-native
  Places client.
- **Seams (where things can change independently):**
  - Places capability — the discovery call is a method behind the existing client wrapper,
    so the SDK stays inside the wrapper and the service depends on the wrapper.
  - Discovery field selection — the field mask is built per category from the plan's
    `predefined_metrics`, so a change to which pre-defined metrics exist changes the mask
    with no service edit.
  - Enrichment seam — `discovered_places` is the frozen input M1.2 reads; M1.1 does not
    fetch routing or transit.
- **Component list:**
  - `AmenitySearch` — R2 responsibility entry; owns the M1.1 workflow and its stages; holds
    the async Places client and a concurrency semaphore.
  - `AmenitySearchState` — mutable handoff carrying `origin`, `radius_km`, the input
    `category_metric_plans`, and the produced `discovered_places`.
  - `DiscoveryRequest` — the validated per-category call spec the builder produces.
  - `CanonicalPlace` — one deduplicated place, `place_id` plus its returned fields.
  - `GooglePlacesAsyncClient.search_nearby_discovery` — a new async, no-routing, caller-masked,
    primary-type searchNearby method beside the existing sync routing client, with explicit
    retry and timeout.
  - `PlaceDiscoveryError` tree — the typed failure surface for the component.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `AmenitySearch` | M1.1 workflow, per-category concurrency, three stages, `aclose` | `GooglePlacesAsyncClient`, contracts | — (concrete) |
| `AmenitySearchState` | mutable handoff; input plans + origin/radius + `discovered_places` | `CanonicalPlace`, `CategoryMetricPlan` | — (dataclass) |
| `DiscoveryRequest` | one validated per-category call spec (primary type, mask, radius m, caps) | — | — (dataclass) |
| `CanonicalPlace` | one place: `place_id` + returned fields, no unit conversion | — | — (frozen dataclass) |
| `GooglePlacesAsyncClient.search_nearby_discovery` | async no-routing searchNearby, caller field mask, primary types, explicit retry/timeout | `PlacesAsyncClient` SDK | new async wrapper beside the sync one |
| `PlaceDiscoveryError` tree | request-invalid vs call-failed exits, each with `stage` | — | — (exception tree) |

> `Abstracted?` legend matches the R1 file: `—` = concrete · `method on wrapper` = added to
> the existing client, not a new abstraction.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| New `AmenitySearch` class in its own file | R2 is a second responsibility with its own state and injected client | R1's class would take a Places dependency it never uses |
| Reuse one `schemas.py` for R2 contracts | contracts are read across R2 mechanisms, as in R1 | a per-contract file makes one data journey span modules |
| `search_nearby_discovery` beside `search_nearby` | M1.1 excludes routing and needs a narrow, per-call field mask | the routing-coupled broad-mask method cannot omit routing (routingSummaries in the mask requires routingParameters) |
| Field mask built from `plan.predefined_metrics` | the mask must carry exactly basic (+ operating) place fields + `places.id` | a hard-coded mask drifts from the pre-defined metric set R1 owns |
| `included_primary_types=[taxonomy_node]` | one primary type per node (locked M1.1.a) | `included_types` matches secondary types and admits mislabeled places |
| Async-native `PlacesAsyncClient`, awaited directly | R2 is async; an async-native searchNearby exists | offloading to a thread would add worker overhead the async client removes |
| Explicit retry in the async client (2s, 3s, 15s timeout) | the generated searchNearby carries no default retry (D-A2) | a transient failure fails the category with no re-issue |
| Per-category concurrency, semaphore of 3 | categories are independent; tool limits are finite | serial calls stack their waits; unbounded fan-out trips rate limits |
| `PlaceDiscoveryError` with a `stage` | the runner reports which stage exited, as in R1 | the caller parses a traceback to tell invalid-request from call-failed |
| Freeze `discovered_places` after dedup | M1.2 enriches a fixed set; nothing may re-discover | a later stage re-searches and the canonical set shifts |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| Taxonomy → primaryType resolver (old M1.1.a) | **removed** | taxonomy nodes are Google place-type strings; the node is the primary type |
| Thread-offload of the sync client | rejected | an async-native `PlacesAsyncClient` exists, so the call is awaited directly with no worker |
| Converting the existing sync `search_nearby` to async | not done | it and its sample run are sync and out of M1.1 scope; the async discovery client is added beside it |
| Text Search fallback on a weak result | rejected | locked M1.1.b: Nearby stays the path, retry re-issues the same Nearby request |
| Separate `DISCOVERY_FIELD_MASK` constant | rejected | the mask is derived per category from the plan, so a constant would duplicate that set |
| New R2 schemas module | rejected | one `schemas.py` per service already holds R1's contracts |
| Retry/backoff framework | not added | one call, bounded retries (2s, 3s) plus a 15s timeout suffice |
| `AmenitySearch` interface | kept concrete | one implementation, no second consumer stated |
| Persisting `discovered_places` | not added | handoff is in-process and in-memory, as in R1 |
| Unbounded per-category fan-out | rejected | a semaphore of 3 caps in-flight calls so the tool's rate limit is not overrun |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
AmenitySearch → GooglePlacesAsyncClient.search_nearby_discovery → PlacesAsyncClient SDK (awaited)
AmenitySearch → AmenitySearchState, DiscoveryRequest, CanonicalPlace, CategoryMetricPlan (contracts)
AmenitySearch → PlaceDiscoveryError (typed exits)
```

### F. Composition Root

- **Where:** `create_amenity_search(settings)` in `amenity_search.py`, which calls
  `create_places_async_client(settings)` in `clients/google_places.py`. `AmenitySearch` owns
  the `asyncio.Semaphore(3)`.
- **Selects:** `google_maps_api` key (already in `Settings`); the discovery caps
  `DISCOVERY_MAX_RESULTS = 3` and `DEFAULT_RADIUS_KM = 2.0` as module constants
  (configurable later, mirroring `MIN_INPUT_WORD_COUNT`).
- **Lifecycle:** `AmenitySearch.aclose()` calls the async client's `aclose()`, which closes the
  grpc.aio transport channel the SDK opened.
- **Later:** when a request path needs discovery, this factory is called from the app
  `lifespan` and exposed via `app/api/dependencies/`, matching `create_access_token_verifier`
  and R1's planned wiring.

### G. Async Execution Map (per the async skill)

Placement is set by blocking behavior; ordering is set by data dependency. The two are
decided separately.

- **`run_place_discovery` (entry).** Operations: for each plan, build then execute then
  assemble. Data dependency: category pipelines are independent of each other. Ordering:
  concurrent (scheduled with `gather`, each guarded by `asyncio.Semaphore(3)`). Placement:
  the coroutine itself runs on the event loop. Shared-state handling:
  partial-results-and-merge, each task returns its category's canonical dict and the entry
  coroutine writes `state.discovered_places[category_id]` after the task resolves, so no two
  tasks write shared state at once.
- **`build_discovery_request`.** Operation: string join and arithmetic (km to meters).
  Data dependency: none. Placement: inline on the event loop (trivial CPU work that finishes
  quickly). Ordering: sequential before its own execute.
- **`execute_discovery`.** Operation: one `await search_nearby_discovery` on the async-native
  client (the awaiting coroutine yields, the function pauses and lets other coroutines run,
  during the network wait). Placement: on the event loop as a coroutine; no worker, because
  the SDK call is itself awaitable. Ordering: within a category it is awaited before assemble
  (data-dependent); across categories the calls are scheduled together with `gather` and
  their network waits overlap. Bounding: each in-flight call is guarded by the shared
  `asyncio.Semaphore(3)`; each attempt is bounded by a 15s library timeout, and the client
  re-issues on a transient failure with a 2s then 3s backoff.
- **`assemble_canonical_places`.** Operation: dict build and dedup by `place_id`. Data
  dependency: needs its own execute result. Placement: inline on the event loop (trivial CPU
  work). Ordering: sequential after execute.

### H. End-to-End Flow

1. Caller invokes `AmenitySearch.run_place_discovery(state)` with `origin`, `radius_km`, and
   `category_metric_plans` set on the state.
2. For each plan, the entry coroutine schedules a bounded task: `build_discovery_request`
   assembles the primary type, the per-category field mask, the radius in meters, and the
   result cap, validating the inputs.
3. `execute_discovery` awaits `search_nearby_discovery` on the async client, guarded by the
   semaphore and the 15s timeout, retrying on transient failure; total failure raises
   `PlaceDiscoveryError`.
4. `assemble_canonical_places` dedups the returned places by `place_id` within the category
   and returns the frozen canonical dict.
5. The entry coroutine gathers the per-category results and writes
   `state.discovered_places[category_id]`, then returns the state for M1.2.

---

## Layer 4 — Backing

- **New file for R2, not a method on R1's class:** R1's `UserRequirementsInterpretation` is
  the unit that owns the interpretation workflow and its injected LLM providers. R2 owns a
  different workflow and a different injected capability (Places), so extending R1's class
  would give it a dependency none of its mechanisms use.
- **One `schemas.py` for both responsibilities:** the deep-search service reads one contract
  module across its mechanisms, so R2's `AmenitySearchState`, `DiscoveryRequest`, and
  `CanonicalPlace` sit beside R1's contracts rather than in a second module a reader would
  have to cross-reference to see the data journey.
- **A discovery method beside the routing method, not a rewrite:** the existing
  `search_nearby` couples `routing_parameters` and the broad mask, and its `routingSummaries`
  field forces `routingParameters` to be present, so a no-routing discovery call cannot reuse
  it. A second method keeps the routing path intact for M1.2 and gives discovery its own
  narrow, caller-supplied mask.
- **Mask from the plan, not a constant:** the pre-defined metric set is code-owned in
  `PREDEFINED_METRICS_BY_DEPTH`, and the discovery mask is exactly its `places.*` targets for
  the category's depth, so building the mask from `plan.predefined_metrics` means the two
  cannot drift, and routing (`routingSummaries.*`) and transit (Routes API) targets fall out
  because they are not `places.*` fields.
- **Async-native rather than thread-offload:** an async-native `PlacesAsyncClient` exists, so
  the discovery call is awaited directly and the coroutine yields during the network wait
  without a worker. A new async wrapper (`GooglePlacesAsyncClient`) is added beside the sync
  one, so the existing sync `search_nearby` and its sample run are untouched.
- **Semaphore, not fire-and-forget:** every in-flight call is guarded by `asyncio.Semaphore(3)`,
  so scheduling more categories than the bound waits for a slot rather than overrunning the
  tool's rate limit.
- **Freeze after dedup:** M1.2 enriches a fixed set keyed by `place_id`, so the canonical
  dict is built once per category and not re-searched, and dedup is within a category only
  because a place that matches two categories is one record per category (locked D7).
- **Typed error with a stage:** the component has two exits, an invalid request the builder
  rejects and a call that fails after retries, and naming the stage lets the runner report
  which one fired without reading a traceback, matching R1's error tree.

---

## Decisions taken (previously open)

- **D-A1 — Async placement of the discovery call. Resolved: async-native.** The discovery
  call is awaited on a new `GooglePlacesAsyncClient` backed by `PlacesAsyncClient`; no thread
  pool. The sync `GooglePlacesClient` and its sample run are left in place.
- **D-A2 — Retry ownership. Resolved: explicit retry in the wrapper.** The generated
  `searchNearby` is not relied on for retry; `search_nearby_discovery` re-issues on a transient
  failure with a 2s then 3s backoff, each attempt bounded by a 15s timeout, and maps the
  exhausted error to `PlacesTimeoutError` / `PlacesRateLimitError`.
