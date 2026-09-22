# Responsibility 2 — Mechanism 1, Component M1.1 (Place Discovery): Implementation Plan

Architecture and modularity decisions are in
[r2_mechanism_1_component_1_architecture_decisions.md](r2_mechanism_1_component_1_architecture_decisions.md).

Scope: **Component M1.1 (Place Discovery)** and its three sub-components only.
- M1.1.a Nearby Search Request Builder
- M1.1.b Search Execution and Failure Handling
- M1.1.c Canonical Place Set Assembly and Within-Category Dedup

M1.2 (Accessibility Enrichment) and M1.3 (Attachment) are not built here. M1.1 stops at a
frozen `discovered_places` per category.

---

## 1. File and Module Structure (Build todos)

Do not create these until the plan is confirmed (Build).

| # | File | New/Modify | Purpose and ownership |
| --- | --- | --- | --- |
| 1 | `backend/src/services/deep_search/amenity_search.py` | New | R2 responsibility class `AmenitySearch`; the M1.1 workflow (`run_place_discovery`) and its three stage methods; `create_amenity_search(settings)` composition root; owns the async Places client and an `asyncio.Semaphore(3)`; `aclose()`. |
| 2 | `backend/src/services/deep_search/feature_schemas/schemas.py` | Modify | Add R2 M1.1 contracts: `GeoPoint`, `CanonicalPlace`, `DiscoveryRequest`, `AmenitySearchState`, and the constants `DISCOVERY_MAX_RESULTS = 3`, `DEFAULT_RADIUS_KM = 2.0`. |
| 3 | `backend/src/clients/google_places.py` | Modify | Add `create_places_async_client(settings)` and `GooglePlacesAsyncClient.search_nearby_discovery(...)`: async, no `routing_parameters`, caller-supplied field mask, `included_primary_types`, explicit 2s/3s retry and 15s timeout. Leave the sync `search_nearby` (routing) unchanged for M1.2. |
| 4 | `backend/src/exceptions/deep_search.py` | Modify | Add the `PlaceDiscoveryError` tree: base (with `stage`), `PlaceDiscoveryRequestError` (invalid request), `PlaceDiscoveryCallError` (call failed after retries). |
| 5 | `backend/src/services/deep_search/feature_sample_runs/place_discovery_sample_run.py` | New | Live, stage-by-stage runner over seeded R1 output plus origin/radius; one real Places call per category; prints a titled section per stage; reads `homescout.places` records for the call trail. |
| 6 | `backend/tests/services/deep_search/test_place_discovery.py` | New | Dummy-client fixtures (no live calls): assert mask construction, request validation, dedup/freeze, retry/timeout path, and the concurrency bound. |

The live sample runner (file 5) is required by the plan format and is not part of the request
path in §E.

---

## 2. Implementation Architecture and Design Decisions

In the separate file
[r2_mechanism_1_component_1_architecture_decisions.md](r2_mechanism_1_component_1_architecture_decisions.md)
(Layers 1–4, dependency direction, composition root, the async execution map, and the two
open decisions).

---

## A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: (orchestrator, later) — sequences the three responsibilities
   └─ Responsibility 2: AmenitySearch — find real amenities and collect their facts
      └─ Mechanism 1 Workflow: run_place_discovery — plans → frozen canonical places per category
         ├─ Stage a: build_discovery_request — per category: primary type, field mask, radius m, cap
         ├─ Stage b: execute_discovery — offloaded, bounded searchNearby (no routing); response or typed error
         └─ Stage c: assemble_canonical_places — dedup by place_id within category, freeze
```

> M1.2 (Accessibility Enrichment) and M1.3 (Attachment) are later mechanism nodes that read
> `discovered_places`; they are not in this map.

## B. Data Contracts

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `CategoryMetricPlan` (existing, R1) | one category's metric picture, R2's input | `category_id: int` · `taxonomy_node: str` — a Google primary type · `depth: DepthLevel` · `predefined_metrics: list[PredefinedMetric]` · `specific_metrics: list[MetricSpec]` | read-only here | R1 → Stage a |
| `GeoPoint` | the listing origin | `latitude: float` · `longitude: float` | immutable | caller → Stage a |
| `DiscoveryRequest` | one validated per-category call spec | `category_id: int` · `primary_type: str` · `latitude: float` · `longitude: float` · `radius_meters: float` · `field_mask: str` — comma-joined `places.*` tokens · `max_result_count: int` | immutable | Stage a → Stage b |
| `CanonicalPlace` | one deduplicated place, fields as returned | `place_id: str` · `place: dict` — the searchNearby place serialized, no unit conversion | immutable (frozen) | Stage c → M1.2 |
| `AmenitySearchState` | R2 mutable handoff | `origin: GeoPoint` · `radius_km: float` (default 2.0) · `category_metric_plans: list[CategoryMetricPlan]` · `discovered_places: dict[int, dict[str, CanonicalPlace]]` — category_id → place_id → place | **mutable** — M1 writes `discovered_places` | caller/R1 → Stages a/c, then M1.2 |

> Rules to surface: `discovered_places` is keyed category_id then place_id, so dedup is within
> a category only (locked D7); each `CanonicalPlace` is frozen and its `place` dict holds
> basic (and operating, per depth) fields exactly as returned, with km/minute conversion
> deferred to M1.3; `DiscoveryRequest.field_mask` is built from the plan, never a global mask.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `GooglePlacesAsyncClient` | async client wrapper | `search_nearby_discovery(*, latitude, longitude, radius_meters, primary_type, field_mask, max_result_count) -> SearchNearbyResponse [raises: PlacesClientError]` · `aclose()` | one (concrete, `PlacesAsyncClient`) | Stage b |
| `asyncio.Semaphore(3)` | concurrency bound | caps concurrent in-flight discovery calls across categories | one | Stage b |
| `PlaceDiscoveryError` tree | exceptions | `PlaceDiscoveryRequestError`, `PlaceDiscoveryCallError`, each with `stage` | concrete | Stages a/b |

## D. Class & Method Blueprint

**`AmenitySearch`** — R2 responsibility entry; owns the M1.1 workflow and stages; holds the
Places client, the thread pool, and the semaphore.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | `(places_client: GooglePlacesAsyncClient, *, max_concurrency: int = 3) -> None` | bind client; build the concurrency semaphore |
| `run_place_discovery` | `(state: AmenitySearchState) -> AmenitySearchState [mutates: state.discovered_places] [raises: PlaceDiscoveryError]` | drive stages per category, concurrently bounded, write results |
| `build_discovery_request` | `(plan: CategoryMetricPlan, origin: GeoPoint, radius_km: float) -> DiscoveryRequest [raises: PlaceDiscoveryRequestError]` | assemble and validate one per-category call spec |
| `execute_discovery` | `async (request: DiscoveryRequest) -> SearchNearbyResponse [raises: PlaceDiscoveryCallError]` | await the semaphore-bounded searchNearby call; map failure typed |
| `assemble_canonical_places` | `(response: SearchNearbyResponse) -> dict[str, CanonicalPlace]` | dedup by place_id within the category, freeze |
| `aclose` | `async () -> None` | close the async Places transport |

**`GooglePlacesAsyncClient`** (new, beside the sync `GooglePlacesClient`).

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `search_nearby_discovery` | `async (*, latitude, longitude, radius_meters, primary_type, field_mask, max_result_count) -> SearchNearbyResponse [raises: PlacesClientError]` | async no-routing searchNearby, caller mask, primary type, 2s/3s retry, 15s timeout |
| `aclose` | `async () -> None` | close the grpc.aio transport |

**`create_amenity_search`** — composition root.

| Function | Signature | Purpose (one line) |
| --- | --- | --- |
| `create_amenity_search` | `(settings: Settings) -> AmenitySearch` | build the Places client and inject it |

## E. Runtime Flow — Data Object Journey

One request = one `AmenitySearchState` carrying `origin`, `radius_km`, and the R1
`category_metric_plans`. The sample runner and the dummy fixtures are excluded.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `run_place_discovery` | `state.category_metric_plans`, `origin`, `radius_km` | schedules one bounded task per plan | state unchanged until tasks resolve |
| 2 | `build_discovery_request` | one `CategoryMetricPlan`, `origin`, `radius_km` | `DiscoveryRequest` | `{category_id, primary_type, lat, lng, radius_meters, field_mask, max_result_count}` |
| 3 | `execute_discovery` | `DiscoveryRequest`, async Places client | `SearchNearbyResponse` **or** `PlaceDiscoveryCallError` | raw places for that category |
| 4 | `assemble_canonical_places` | `SearchNearbyResponse` | `dict[str, CanonicalPlace]` | one frozen place per unique place_id |
| 5 | `run_place_discovery` | gathered per-category dicts | `[mutates: state.discovered_places[category_id]]` | `discovered_places` filled per category |

**Transformation trace (shape only):**
```
AmenitySearchState{ origin, radius_km, category_metric_plans[], discovered_places: {} }
 → per plan: DiscoveryRequest{ category_id, primary_type, lat, lng, radius_meters, field_mask, max_result_count }
 → SearchNearbyResponse{ places[] }            # per category, or PlaceDiscoveryCallError
 → dict[place_id → CanonicalPlace{ place_id, place }]   # deduped within the category, frozen
 → AmenitySearchState.discovered_places{ category_id → { place_id → CanonicalPlace } }
```

**Approach at the real decision points:**
- Field mask (Stage a): take `plan.predefined_metrics`, keep every metric whose
  `resolution_source.target` starts with `places.`, and comma-join those targets. This
  yields the basic (and operating, per depth) place fields plus `places.id`, and drops
  routing (`routingSummaries.*`) and transit (Routes API) targets because they are not
  `places.*`. No routing means the call needs no `routingParameters`.
- Request validation (Stage a): reject when `origin` lacks a finite lat/lng, when
  `radius_km <= 0`, or when `taxonomy_node` is empty, raising `PlaceDiscoveryRequestError`.
  Convert `radius_km` to meters (× 1000). Set `primary_type = taxonomy_node`,
  `max_result_count = DISCOVERY_MAX_RESULTS`.
- Concurrency (entry): category pipelines are independent, so each runs under the shared
  `asyncio.Semaphore(3)` and all are awaited together; within one category, execute is
  awaited before assemble.
- Execution and failure (Stage b): await `search_nearby_discovery` on the async client under
  the shared semaphore; the client bounds each attempt with a 15s timeout and retries
  transient failures with a 2s then 3s backoff; on exhaustion `execute_discovery` raises
  `PlaceDiscoveryCallError`. Failure is Nearby-only: the retry re-issues the same request and
  never switches to Text Search.
- Dedup and freeze (Stage c): index returned places by `places.id`; the first occurrence of
  a `place_id` wins and later duplicates within the same category are dropped; each kept
  place is wrapped in a frozen `CanonicalPlace` and the per-category dict is not mutated after
  this stage.

A reader who stops here knows: R2 takes the R1 plans plus an origin and radius, searches each
category once (no routing), keeps a small deduplicated set of real places per category, and
hands a frozen `discovered_places` to enrichment.

## F. Method Detail

**`build_discovery_request`**
- **Purpose:** turn one category plan plus origin/radius into a validated, no-routing call
  spec.
- **What it does:** validate origin, radius, and node; select `places.*` targets from
  `plan.predefined_metrics` and comma-join them into the field mask; convert km to meters;
  set the primary type from `taxonomy_node` and the cap from `DISCOVERY_MAX_RESULTS`.
- **Inputs:** `plan`, `origin`, `radius_km`. **Outputs:** `DiscoveryRequest`. **Failure:**
  `PlaceDiscoveryRequestError` (stage `build_discovery_request`).

**`execute_discovery`**
- **Purpose:** run one bounded searchNearby and return the raw response.
- **What it does:** acquire the semaphore; `await` the async `search_nearby_discovery`, which
  bounds each attempt with a 15s timeout and re-issues on a transient failure with a 2s then
  3s backoff; on total failure map the `PlacesClientError` to the typed error.
- **Inputs:** `DiscoveryRequest`. **Outputs:** `SearchNearbyResponse`. **Failure:**
  `PlaceDiscoveryCallError` (stage `execute_discovery`), wrapping the `PlacesClientError`
  subtype.

**`assemble_canonical_places`**
- **Purpose:** produce the frozen, deduplicated canonical set for one category.
- **What it does:** iterate `response.places`; key by `places.id`; keep the first per id and
  drop later duplicates within the category; store each as `CanonicalPlace(place_id, place)`
  with the returned fields unchanged (no km/minute conversion).
- **Inputs:** `SearchNearbyResponse`. **Outputs:** `dict[str, CanonicalPlace]`. **Failure:**
  none (a place missing an id is dropped and logged).

---

### Checklist run before emitting

- [x] Every §B contract a method passes appears in that method's §D signature.
- [x] Every §C actor is depended on by a §D class.
- [x] The mutable object (`AmenitySearchState.discovered_places`) is identified in §B and its
      write shown in §E.
- [x] §E is the request path only; the sample runner and fixtures are excluded.
- [x] No code or pseudocode; decision points are approach pointers; fenced blocks only for the
      §A tree and §E shape trace.
- [x] A reader can stop after §E and explain how a request is processed.
- [x] No "why it's abstracted" reasoning here; that is in the architecture file.
- [x] Section 1 lists the live sample runner under `feature_sample_runs/`.
- [x] Section 4 describes how to run it and what it prints.

---

## 4. Sample Runner and Dummy-Provider Fixture Set

Two checks, neither in the §E request path.

### 4.1 Live sample runner (required)

`feature_sample_runs/place_discovery_sample_run.py`. Manual, stage-by-stage, one real Places
call per category for M1.1 only.

- **How to run** — from `backend/`:
  `python -m src.services.deep_search.feature_sample_runs.place_discovery_sample_run`
- **What it seeds** — an `AmenitySearchState` as after R1: a small `category_metric_plans`
  list (e.g. `swimming_pool` at `specific_attributes`, `bakery` at `operating_details`) plus a
  real `origin` (a known lat/lng) and `radius_km = 2.0`. R1 is not re-invoked. The seeded plans
  must not reuse a metric few-shot's wording; this is a new use case.
- **What it prints** — one titled section per stage: input state, the built `DiscoveryRequest`
  (with the derived field mask), the Places call attempts and outcome read from
  `homescout.places` records via a collecting handler, and the assembled `discovered_places`
  (place ids and counts per category). On a typed failure: exception class, `stage`, message,
  and a non-zero exit. Nothing is written to disk.

### 4.2 Dummy-client fixture set

`tests/services/deep_search/test_place_discovery.py`. Pytest with a fake `GooglePlacesClient`
(no live calls) asserting the code-path rules the live runner cannot prove deterministically:

- field mask is exactly the plan's `places.*` targets for the category's depth, and excludes
  routing and transit targets;
- request validation rejects a bad origin, a non-positive radius, and an empty node;
- km is converted to meters and `max_result_count` is `DISCOVERY_MAX_RESULTS`;
- duplicate `place_id`s within one category collapse to one `CanonicalPlace`, and distinct ids
  are all kept;
- the async client re-issues on a transient error with a 2s/3s backoff and succeeds, and
  exhaustion raises `PlacesTimeoutError`;
- a failed call surfaces as `PlaceDiscoveryCallError` with `stage == "execute_discovery"`;
- concurrent per-category calls never exceed the semaphore bound of 3.
