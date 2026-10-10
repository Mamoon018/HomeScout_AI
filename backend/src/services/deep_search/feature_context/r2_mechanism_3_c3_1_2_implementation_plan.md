# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.2 (Add a Tool-Turn Call to the Shared StructuredLLMCaller)

## Context

Why this change: M3 (R2 metric resolution) needs the LLM to decide when to call `web_search` and `firecrawl_crawl`, which is a *tool-calling conversation*: tool results are appended to a message history and sent back. Two things block that today:

1. The provider-fallback funnel (`OpenAI → Groq`, `LLM_PROVIDER_ORDER`) is **private to R1** — it lives as `UserRequirementsInterpretation._call_providers` inside `requirement_interpretation.py`. `AmenitySearch` (R2) cannot reach it, and copying it would drift from R1.
2. Both provider adapters are hardwired to one `generate_structured` shape: a fixed system+user message pair with a strict-JSON `response_format`. There is **no message history and no tool path**.

What C3.1.2 delivers (and only this): one shared `StructuredLLMCaller` that holds the provider chain and serves both R1 and R2; a new `generate_turn(messages, tools, tool_choice)` on the provider protocol and both adapters; the lifted fallback funnel used by both a structured call and a tool turn; a `DeepSearch` feature class + composition root that builds the caller **once** and injects it into R1 and R2 (D6); the typed `MetricResolutionProviderError`. R1's observable behavior is unchanged.

Out of scope (later sub-components, confirmed against the C3.1.2 spec at `deep_search_context.md:2815`): building the tool JSON schemas / M6→MCP name mapping, the phase-gated resolution loop, tool-argument validation (C3.1.3), URL resolution, the crawl cache, and C3.2. The tool turn **receives** tool definitions as an input; it does not build them.

Confirmed design choice (from the user): introduce the `DeepSearch` feature class now so D6 ("built once at the composition root, passed to R1 and AmenitySearch, created and closed once") is realized here, with the composition root running the factories in the correct dependency order.

Spec anchor: `backend/src/services/deep_search/feature_context/deep_search_context.md:2815-2846`.

---

## 0. Cross-mechanism check (updates to earlier mechanisms)

| Earlier piece | Finding | Action in this plan |
| --- | --- | --- |
| `requirement_interpretation.py` fallback funnel | `_call_providers` (`:1674`) is R1-private; 7 call sites (M2/M4/M5/M6 at `:484,519,661,854,996,1195,1411`) | **Lift** the funnel body into `StructuredLLMCaller.call_structured`; `_call_providers` becomes a thin delegate — same signature, same events, same return `(body, answered_by)`. Call sites untouched. |
| R1 constructor | `UserRequirementsInterpretation.__init__(providers)` (`:154`) | Takes the shared `StructuredLLMCaller` + `owns_caller: bool`. Derives `self._providers = caller.providers` so the M1 inline loop and `aclose` still read it. |
| R1 M1 inline funnel | `execute_and_validate` (`:252`) has its own loop with different events (`extraction.provider_attempt`) and `ExtractionProviderError` | **Left as-is.** A prior locked decision (`async_conversion_architecture_decisions.md:87`) rejected unifying it because event names and error types differ. It reads `self._providers`, still available. |
| Event constants | `LLM_PROVIDER_ATTEMPT_EVENT` / `LLM_PROVIDER_RAW_BODY_EVENT` (`:122-123`) imported by 4 sample runners | **Move** the string constants into `clients/llm_provider.py`; re-export them from `requirement_interpretation.py` so the 4 runners' imports keep working unchanged. |
| `create_requirement_interpretation` (`:1862`) | builds providers only | Build the shared caller; accept an optional injected `llm_caller`. |
| `AmenitySearch.__init__` / `aclose` / `create_amenity_search` (`amenity_search.py:104,692,715`) | no LLM caller today | Add keyword-only `llm_caller` + `owns_caller`; `aclose` closes it only when owned; `create_amenity_search` builds/accepts it. |
| R1 unit tests | `UserRequirementsInterpretation([provider])` in `test_mechanism_2/4/5/6` | Wrap: `UserRequirementsInterpretation(StructuredLLMCaller([provider]))`. The `FakeStructuredProvider` needs **no** `generate_turn` (structured-only tests never call it). |
| `deep_search_context.md` "Current code" (`:2766-2770`) | says the chain fallback is "private to R1"; C3.1.1 guessed "tool-name mapping is C3.1.2's job" | Add one C3.1.2 **build note** (mirroring the C3.1.1 note): funnel lifted into the shared caller; correct that tool-schema/name mapping is a *later* sub-component, not C3.1.2. Locked C3.1.2 spec text untouched. |
| Historical mechanism plan docs (M4/M5/M6 reuse `_call_providers`) | describe `_call_providers(... ) -> tuple[dict,str]` | **No change** — that signature and behavior are preserved by the delegate, so those records stay accurate. |

---

## 1. File and Module Structure (Build todos)

| # | File | New/Modify | Purpose and ownership |
| --- | --- | --- | --- |
| 1 | `backend/src/clients/llm_provider.py` | Modify | Add `ToolCall` / `AssistantTurn` contracts; add `generate_turn` to the protocol and both adapters; add `StructuredLLMCaller` (`call_structured` lifted, `call_turn` new, `aclose`); add `create_structured_llm_caller`; move the two `llm_provider.*` event-name constants here. |
| 2 | `backend/src/exceptions/deep_search.py` | Modify | Add `MetricResolutionError` base + `MetricResolutionProviderError` (ClassVar `stage` + `__init__(*, stage=None)`), following the `MetricDefinitionError` trio shape. No Validation sibling yet (nothing raises it until C3.1.3). |
| 3 | `backend/src/services/deep_search/requirement_interpretation.py` | Modify | R1 takes the shared caller (`+ owns_caller`); `_call_providers` delegates to `caller.call_structured`; `aclose` closes the caller only when owned; `create_requirement_interpretation` builds/accepts the caller; re-export the two moved event constants. |
| 4 | `backend/src/services/deep_search/amenity_search.py` | Modify | `AmenitySearch.__init__` adds keyword-only `llm_caller` + `owns_caller`; `aclose` closes the caller only when owned; `create_amenity_search` builds/accepts it. |
| 5 | `backend/src/services/deep_search/deep_search.py` | **New** | `DeepSearch` feature class (owns the shared caller; holds R1 + R2; sequences R1 then R2 in correct order; `aclose` closes the caller once) + `create_deep_search(settings)` composition root that runs the factories in dependency order. |
| 6 | `backend/src/services/deep_search/feature_tests/test_c3_1_2_structured_llm_caller.py` | **New** | Offline fixtures (Section 6) with a fake provider exposing `generate_turn`/`generate_structured`. |
| 7 | `backend/tests/services/deep_search/test_mechanism_2_clarification.py`, `_4_inference.py`, `_5_depth.py`, `_6_metrics.py` | Modify | Wrap the fake provider in a `StructuredLLMCaller` at the one `UserRequirementsInterpretation(...)` construction line each. |
| 8 | `backend/src/services/deep_search/feature_context/deep_search_context.md` | Modify | One C3.1.2 build note (see Section 0). |

No prompt module and no new schema types: the turn carries provider-neutral `dict` messages/tools in, an `AssistantTurn` out; tool schemas and resolved-metric records belong to later sub-components. `StructuredLLMCaller`, `ToolCall`, `AssistantTurn` live in `clients/` (never import `services/`), exactly as the C3.1.1 result contracts do.

**No live sample runner** (per user direction): Plan_output_format's required `feature_sample_runs/` runner is intentionally omitted for C3.1.2. C3.1.2 is a caller-level capability with no `AmenitySearch` stage method of its own; it is verified deterministically by the offline fixtures (Section 6) and will be exercised against a real provider by the C3.1.3 resolution-loop runner that consumes it.

---

## 2. Implementation Architecture

### A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: DeepSearch — owns the shared StructuredLLMCaller; sequences R1 then R2
   ├─ Responsibility 1: UserRequirementsInterpretation — raw text → per-category spec (reused; now caller-injected)
   └─ Responsibility 2: AmenitySearch — find amenities and collect facts (now caller-injected)
      └─ Mechanism 3 Workflow: run_llm_metric_resolution (later sub-components)
         └─ Component C3.1: evidence-acquisition tool loop (later)
            └─ Sub-component C3.1.2 (this plan): the tool-turn call on the shared caller
               ├─ Actor: StructuredLLMCaller.call_turn — provider-fallback funnel over generate_turn
               ├─ Actor: StructuredLLMCaller.call_structured — the lifted funnel over generate_structured
               └─ Actor: provider.generate_turn — one tools request → typed AssistantTurn
```

C3.1.2 adds **no** stage method to `AmenitySearch` (the resolution workflow is later). Its deliverable is the shared caller, the tool-turn provider method, and the `DeepSearch` wiring.

### B. Data Contracts

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `ToolCall` | one tool call the model emitted | `id: str` — tool_call_id · `name: str` — function name · `arguments: str` — raw JSON args (unvalidated; strict off) | immutable (frozen) | `generate_turn` → C3.1.3 |
| `AssistantTurn` | one assistant turn result | `provider: str` · `finish_reason: str \| None` · `content: str \| None` · `tool_calls: tuple[ToolCall, ...]` (empty `()` never null) · `message: dict` — OpenAI-format assistant message, re-appendable to history | immutable (frozen) | `generate_turn` → `call_turn` → caller |
| messages | provider-neutral history | `list[dict]` in OpenAI chat format (system/user/assistant+`tool_calls`/`tool`+`tool_call_id`) | caller-owned list | caller → `generate_turn` |
| tools | function tool defs | `list[dict]` OpenAI function-tool shape | immutable input | caller → `generate_turn` |
| `MetricResolutionProviderError` | typed M3 provider exhaustion | message · `stage: str` | immutable | `call_turn` (via injected class) → R2 |

Rules: an empty tool-call list is `tool_calls=()`, not a failure (the model answered with content only). `message` is built provider-neutrally by the adapter so a fallback provider and C3.1.3 both consume the same shape. Secrets never appear in any contract, log, or exception.

### C. Supporting Actors & Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | Protocol (extended) | `name` · `model` · `generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict` · **`generate_turn(*, messages, tools, tool_choice) -> AssistantTurn`** · `aclose() -> None` | `OpenAIStructuredProvider`, `GroqStructuredProvider`; test fake | `StructuredLLMCaller` |
| `StructuredLLMCaller` | concrete | `providers` · `call_structured(...) -> tuple[dict,str]` · `call_turn(...) -> AssistantTurn` · `aclose()` | one | R1, R2, `DeepSearch` |
| `Settings` | existing config | `llm_provider_order`, keys, models | one | `create_structured_llm_caller` |

### D. Class & Method Blueprint

**`StructuredLLMCaller`** (new, `clients/llm_provider.py`) — holds the ordered provider chain; the single fallback funnel for both call kinds.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | `(providers: Sequence[StructuredLLMProvider])` | store the immutable ordered chain |
| `providers` | `-> tuple[StructuredLLMProvider, ...]` | expose the chain (R1 reads it for the M1 loop) |
| `call_structured` | `(*, instruction: str, user_content: str, json_schema: dict, schema_name: str, stage: str, provider_error_cls: type[Exception]) -> tuple[dict, str] [raises: provider_error_cls]` | lifted funnel: first body + provider, or typed exhaustion |
| `call_turn` | `(*, messages: list[dict], tools: list[dict], tool_choice: str \| dict, stage: str, provider_error_cls: type[Exception]) -> AssistantTurn [raises: provider_error_cls]` | tool-turn funnel over `generate_turn` |
| `aclose` | `() -> None` | close every provider once; idempotent |

**`OpenAIStructuredProvider` / `GroqStructuredProvider`** — add one method each.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `generate_turn` | `(*, messages: list[dict], tools: list[dict], tool_choice: str \| dict) -> AssistantTurn [raises: LLMProviderError, LLMResponseTruncatedError]` | one `chat.completions.create` with `tools` (no `response_format`) → typed turn |

**Module helpers** (new, pure): `_build_assistant_turn(provider, model, choice) -> AssistantTurn` (SDK choice → neutral turn + message dict; raises `LLMResponseTruncatedError` on `finish_reason == "length"`).

**`DeepSearch`** (new, `deep_search.py`).

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | `(*, interpretation: UserRequirementsInterpretation, amenity_search: AmenitySearch, llm_caller: StructuredLLMCaller)` | hold the two responsibilities and the owned shared caller |
| `interpret` | `(raw_input: str) -> RequirementInterpretationState` | run R1 (delegates) |
| `run` | `(raw_input: str) -> RequirementInterpretationState` | sequence R1 then R2 in correct order; R2 stages attach as later sub-components build the handoff (documented boundary — not fabricated here) |
| `aclose` | `() -> None` | close R1 and R2 owned resources, then the shared caller once |

**Composition root** `create_deep_search(settings) -> DeepSearch`: build the shared caller first, then R1 and R2 via their factories with the caller injected, then the feature.

**R1 / R2 changed signatures**

| Change | Signature | Purpose |
| --- | --- | --- |
| `UserRequirementsInterpretation.__init__` | `(caller: StructuredLLMCaller, *, owns_caller: bool = True)` | hold the caller; `self._providers = caller.providers` |
| `UserRequirementsInterpretation._call_providers` | unchanged signature; body → `return await self._caller.call_structured(...)` | delegate; same events, same return |
| `UserRequirementsInterpretation.aclose` | `() -> None` | `if self._owns_caller: await self._caller.aclose()` |
| `create_requirement_interpretation` | `(settings, *, llm_caller: StructuredLLMCaller \| None = None) -> UserRequirementsInterpretation` | build caller if not injected |
| `AmenitySearch.__init__` | `(... , *, tool_gateway, llm_caller: StructuredLLMCaller, owns_caller: bool = True, ...)` | hold the caller |
| `AmenitySearch.aclose` | `() -> None` | existing closes + `if self._owns_caller: await self._llm_caller.aclose()` |
| `create_amenity_search` | `(settings, *, llm_caller: StructuredLLMCaller \| None = None) -> AmenitySearch` | build caller if not injected |

### E. Runtime Flow — Data Object Journey

The request path for C3.1.2's capability is one tool turn (the resolution loop that repeats it is C3.1.3).

| # | Step | Reads | Produces / mutates | Shape after |
| --- | --- | --- | --- | --- |
| 1 | caller `call_turn` picks provider 0 | messages, tools, tool_choice | — | — |
| 2 | `provider.generate_turn` | messages, tools, tool_choice | SDK response → `AssistantTurn` **or** `LLMProviderError` | `AssistantTurn{provider, finish_reason, content, tool_calls[], message}` |
| 3 | on `LLMProviderError` (incl. truncation) | — | log attempt `failed`; try next provider | — |
| 4 | first success | — | log attempt `answered`; return turn | returned to caller |
| 5 | all providers failed | — | log `rejected`; raise `provider_error_cls(..., stage=...)` | `MetricResolutionProviderError` |

**Transformation trace (shape only):**
```
(messages[], tools[], tool_choice)
 → provider.generate_turn → chat.completions.create(model, messages, tools, tool_choice)   # no response_format
 → SDK response → first choice
 → finish_reason == "length" → LLMResponseTruncatedError → fallback (not executed)
 | → AssistantTurn{ content?, tool_calls[], finish_reason, message{role:"assistant", tool_calls?} }
 → LLMProviderError on any provider → next provider
 → all failed → provider_error_cls(stage)
```

**Approach at the decision points:**
- Providers are tried in the bound `LLM_PROVIDER_ORDER`; the fallback is attempted only when the current provider raises `LLMProviderError`. This is the *same* funnel as `call_structured`.
- Fallback fires on `LLMProviderError` only — including `LLMResponseTruncatedError` (a turn with `finish_reason == "length"` and partial tool args is treated as a provider failure, never executed). It never fires for a returned-but-unwanted body.
- `parallel_tool_calls` stays default-on, so one turn may carry several `ToolCall`s; all are surfaced in `tool_calls`.
- The history is provider-neutral OpenAI chat format, so a fallback provider receives the identical messages including prior `tool_calls` and `tool` messages with their `tool_call_id`s.

### F. Method Detail

**`generate_turn` (both adapters)** — call `self._client.chat.completions.create(model=self._model, messages=messages, tools=tools, tool_choice=tool_choice)` inside the same SDK-exception mapping used by `generate_structured` (timeout / rate-limit / auth / catch-all → `LLMProviderError`). Read the first choice; if `finish_reason == _TRUNCATED_FINISH_REASON` raise `LLMResponseTruncatedError`. Else build `AssistantTurn`: copy `content`; map each `message.tool_calls[i]` to `ToolCall(id, function.name, function.arguments)`; build `message` as `{"role":"assistant","content":content}` plus a `"tool_calls"` list in OpenAI shape when present. No `response_format` is sent.

**`call_turn`** — loop `self._providers`; `try generate_turn`; on `LLMProviderError` log `LLM_PROVIDER_ATTEMPT_EVENT` (`outcome:"failed"`, `stage`, `provider`, `model`, `detail` from `exc`+`__cause__`) and continue; on success log `outcome:"answered"` and return; after the loop log `llm_provider.rejected` and raise `provider_error_cls(msg, stage=stage)`. Mirrors `call_structured` exactly (same events, same logger).

**`call_structured`** — the current `_call_providers` body verbatim (events, `__cause__` detail, raw-body debug line, `(body, answered_by)` return), with `provider_error_cls` and `stage` as required parameters (no service-exception default — `clients/` must not import a `services`-owned default).

---

## 3. Drift breakdown (per method)

**`generate_turn` (OpenAI / Groq adapters)**
- Core behavior: one tools request → typed `AssistantTurn`.
- Drifts handled: **SDK transport/timeout/rate-limit/auth error** → caught at this **edge** (SDK boundary) → **rejected** as `LLMProviderError` so the funnel falls back (same mapping as `generate_structured`). · **Truncated turn** (`finish_reason=="length"`, partial tool args) → caught in this method → **rejected** as `LLMResponseTruncatedError` (de-masks a half-built tool call instead of executing garbage). · **Empty/absent choices** → caught here → treated as a provider failure (`LLMProviderError`), so fallback runs rather than returning a null turn.
- Left out: re-validating tool `arguments` JSON — *wrong boundary* (C3.1.3 validates args in code; strict is off by design). · a separate tool-turn model/setting — *not live* (reuse the bound extraction model; no requirement for a second). · retry inside the adapter — *trust* (the funnel's provider fallback is the recovery; no retry requirement stated).

**`StructuredLLMCaller.call_turn`**
- Core behavior: return the first provider's `AssistantTurn`, else typed exhaustion.
- Drifts handled: **every provider raises** → caught in this **core** funnel → **rejected** as `provider_error_cls(stage=...)` (the one place that converts "no provider answered" into a typed M3 signal). · **a degrade must stay visible** → each failed attempt is logged `WARN`-equivalent `outcome:"failed"` before moving on (never a silent swallow).
- Left out: fallback on a *returned* turn we dislike — *imaginary* (the locked rule: fallback only on `LLMProviderError`). · concurrency guard on the shared caller — *not live* (the chain is stateless per call; providers hold their own SDK clients; C3.1.2 makes one turn at a time, the loop's concurrency is C3.1.3). · caller-level timeout — *wrong boundary* (per-call timeouts are the SDK's / the provider's).

**`StructuredLLMCaller.call_structured`** (lifted)
- Core behavior: unchanged from `_call_providers`.
- Drifts handled: identical to today (provider exhaustion → typed error; `__cause__` carried into `detail`).
- Left out: any behavior change — *trust* (regression decision: R1 behavior unchanged; a test pins it).

**`StructuredLLMCaller.aclose`**
- Core behavior: close each provider's SDK client.
- Drifts handled: **double close** (the feature owns it; a stray second close via an owned path) → guarded in **core** with a one-line `_closed` flag → **recover** (no-op on the second call). This is the atomicity guard that makes "created and closed once" safe under the shared-vs-standalone two-lifecycle design.
- Left out: swallowing a provider's close error — *imaginary* (let it propagate; close failures are rare and loud).

**`DeepSearch.aclose` / `create_deep_search`**
- Core behavior: build caller once, inject into both, close once in order.
- Drifts handled: **shared caller closed by a responsibility that does not own it** → prevented by constructing R1/R2 with `owns_caller=False` → the feature is the sole closer (**reject** the double-ownership at construction). · **partial build** (gateway/clients built, a later step raises) → `create_deep_search` builds the caller and dependents in order; a failure propagates (**propagate**) — no half-open sessions because the gateway opens nothing at construction (C3.1.1).
- Left out: a retry/health-check on construction — *not live*. · ordering of R1-before-R2 as a runtime data dependency — *documented boundary* (the R1→R2 handoff is a later sub-component; `run` does not fabricate it).

**R1 `_call_providers` delegate / `AmenitySearch` wiring** — no new drift; pure delegation and field wiring.

---

## 4. Async Execution Map

| Operation group | Operations / I/O | Data dependency | Placement | Ordering | Blocking / worker |
| --- | --- | --- | --- | --- | --- |
| `generate_turn` | one awaited `chat.completions.create` (async SDK) | self-contained | event loop (coroutine) | sequential await | none; HTTP is async on `AsyncOpenAI`/`AsyncGroq` |
| `call_turn` funnel | await provider 0, on failure await provider 1 | fallback depends on the previous attempt failing | event loop | **sequential** (primary then Groq; no `gather`) | none |
| `call_structured` funnel | same as today | same | event loop | sequential | none |
| turn → append → turn (C3.1.3 loop) | await turn, append tool result, await turn | each turn depends on the prior turn + appended results | event loop | sequential | none |
| `aclose` | await each provider `.close()`; feature closes caller once | independent closes | event loop | sequential await (small, bounded) | none |

The funnel stays sequential by data dependency: the fallback cannot start until the primary has failed. The `AssistantTurn`/`ToolCall` build is short in-loop CPU (dict/tuple construction), not offloaded. No shared mutable state across providers; each provider owns its own SDK client.

---

## 5. Logging

Reuse the established shape: `logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)` in `clients/llm_provider.py` (already present), one `logger.info(json.dumps({...}))` per node with `"event"` first and a `"stage"` field for correlation (this codebase correlates by `stage`, not a correlation id).

| Node | Level | Event | Driving state |
| --- | --- | --- | --- |
| boundary: LLM turn response in | INFO | `llm.generate_turn` | provider, model, finish_reason, tool_call_count, content_length |
| boundary: full turn content (zoom) | DEBUG | `llm.generate_turn.content` | provider, model, content, tool-call names+arguments |
| drift: a provider turn failed | INFO | `llm_provider.attempt` (`outcome:"failed"`) | stage, provider, model, detail (`exc` + `__cause__`) |
| path: a provider answered | INFO | `llm_provider.attempt` (`outcome:"answered"`) | stage, provider, model |
| endpoint: no provider answered | INFO | `llm_provider.rejected` | stage, reason, attempted[] |

`call_structured` keeps emitting the identical `llm_provider.attempt` / `llm_provider.raw_body` lines it does today (constants moved to `clients/`, values unchanged), so the 4 R1 runners' collectors still read them. Keys are never logged. No per-turn narration beyond these nodes.

---

## 6. Offline Fixture Set

No live sample runner (see the note under Section 1). The tool turn is proven deterministically here.

`feature_tests/test_c3_1_2_structured_llm_caller.py` — pytest, a hand-written `FakeStructuredProvider` exposing `name`/`model`/`generate_structured`/`generate_turn`/`aclose` (queued bodies/turns; raises `LLMProviderError` when told to fail). No live calls. Asserts:

| Area | Assertion |
| --- | --- |
| Turn fallback | provider 0 raises `LLMProviderError` → provider 1's `AssistantTurn` returned; attempt trail logged |
| Truncation | `finish_reason=="length"` → `LLMResponseTruncatedError` from `generate_turn` → funnel falls back; both truncated → `MetricResolutionProviderError(stage=...)` |
| Exhaustion | all providers raise → `MetricResolutionProviderError` with the given `stage`; no silent swallow |
| No fallback on content | a returned turn (even empty `tool_calls`) is returned, not retried |
| Tool-call parsing | multiple `tool_calls` → `tool_calls` tuple with correct `id`/`name`/`arguments`; `message` is re-appendable OpenAI shape |
| tool_choice / tools passthrough | the fake records the `tools` and `tool_choice` it received; no `response_format` is passed |
| Lifted funnel regression | `call_structured` returns `(body, answered_by)`, falls back on `LLMProviderError`, raises the injected error on exhaustion, and emits the same `llm_provider.attempt`/`raw_body` events as before |
| Lifecycle | `aclose` idempotent; `owns_caller=False` means the responsibility does not close the shared caller; `DeepSearch.aclose` closes it exactly once |

---

## 7. Architecture & Modularity Decisions

### Layer 1 — Glance

- **Shape:** one concrete `StructuredLLMCaller` holds the provider chain and the single fallback funnel; both provider adapters gain a second method behind the existing `StructuredLLMProvider` protocol; a `DeepSearch` feature class owns one caller and injects it into R1 and R2.
- **Seams (what varies independently):**
  - Provider — OpenAI vs Groq, order by `LLM_PROVIDER_ORDER` (reused).
  - Call kind — structured JSON vs tool turn, two methods on the same protocol and caller.
  - Caller ownership — built once by `create_deep_search`, or standalone per responsibility for the per-responsibility runners.
- **Component list:** `StructuredLLMProvider` (protocol, extended) · `StructuredLLMCaller` · `ToolCall`/`AssistantTurn` · `MetricResolutionProviderError` · `DeepSearch` + `create_deep_search`.

### Layer 2 — Justification

**Component map**

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `StructuredLLMProvider` | the two call contracts | `AssistantTurn` | Yes: two providers, reused seam |
| `StructuredLLMCaller` | fallback funnel for both call kinds; chain lifetime | the protocol | — (concrete) |
| `OpenAI/GroqStructuredProvider` | SDK calls, auth, turn/structured mapping | the protocol | implements |
| `ToolCall` / `AssistantTurn` | neutral turn result | none | — (frozen dataclasses) |
| `MetricResolutionProviderError` | typed M3 exhaustion with `stage` | none | — (exception) |
| `DeepSearch` | one shared caller; R1→R2 ordering; single close | R1, R2, caller | — (concrete) |

**Decisions & justifications**

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| One shared `StructuredLLMCaller` | D6: R1 and R2 must use one chain and one funnel | R2 copies R1's funnel; the two drift |
| Lift `_call_providers` into it | "a second copy would drift from R1" | the duplicate exists the moment R2 is wired |
| `generate_turn` on the existing protocol | M3 needs a tool conversation; no tool path exists | `AmenitySearch` can make no tool call |
| `AssistantTurn`/`ToolCall` in `clients/` | callers must not parse SDK message objects | SDK types leak into `services/` |
| Inject `provider_error_cls`/`stage` into the funnel | `clients/` must not own a `services` default error | `clients/` imports a `deep_search` exception |
| `owns_caller` flag | two lifecycles: shared feature + standalone responsibility runners | the shared caller is closed twice, or a standalone runner leaks it |
| `DeepSearch` + `create_deep_search` | D6: built once, closed once; correct factory order | nothing builds one caller for both; ownership is ambiguous |

**Kept concrete / rejected**

| Considered | Decision | Reason |
| --- | --- | --- |
| Unify R1's M1 inline loop onto the shared funnel | rejected | prior locked decision; event names + error type differ, would change R1 behavior |
| `MetricResolutionValidationError` sibling now | not added | nothing raises it until C3.1.3 (arg validation) |
| Separate tool-turn model/setting | not added | reuse the bound extraction model; no second requirement |
| A new protocol just for the tool turn | rejected | the existing protocol has exactly these two consumers |
| Rely on `aclose` idempotency alone for "closed once" | rejected as the primary mechanism | `owns_caller` makes ownership explicit; idempotency is only the cheap backstop |
| Build tool JSON schemas / M6→MCP name mapping here | rejected | the C3.1.2 spec takes tool defs as input; mapping is a later sub-component |
| Fabricate the R1→R2 data handoff in `DeepSearch.run` | rejected | unspecified; belongs to later assembly work |

### Layer 3 — Wiring

**Dependency direction**
```
DeepSearch → UserRequirementsInterpretation → [StructuredLLMCaller] ← StructuredLLMProvider ← OpenAI/Groq adapters
DeepSearch → AmenitySearch ───────────────────┘              │
DeepSearch → [StructuredLLMCaller] (owns)                    └→ AssistantTurn / ToolCall
create_deep_search → create_structured_llm_caller → Settings
```

**Composition root**
- **Where:** `create_deep_search(settings)` in `deep_search.py`.
- **Order it runs the factories:** (1) `create_structured_llm_caller(settings)` → the one shared caller; (2) `create_requirement_interpretation(settings, llm_caller=caller)`; (3) `create_amenity_search(settings, llm_caller=caller)` (which also builds the C3.1.1 gateway + Google clients); (4) `DeepSearch(interpretation=…, amenity_search=…, llm_caller=caller)`.
- **Selects:** provider order/models/keys from `Settings`; `owns_caller=False` on both responsibilities so the feature is the sole closer.
- **Lifecycle:** created once; `DeepSearch.aclose()` closes R1 and R2 owned resources, then the shared caller once. Per-responsibility runners keep their standalone factories (which build and own their own caller).

**End-to-end flow**
1. `create_deep_search(settings)` builds the shared caller, then R1 and R2 with it injected, then the feature.
2. `DeepSearch.run(raw_input)` runs R1 (`interpret`) first.
3. R2's metric-resolution stages (built in C3.1.3+) run next, in order, using the same injected caller's `call_turn`; the R1→R2 handoff attaches there.
4. `call_turn` tries providers in `LLM_PROVIDER_ORDER`, falls back on `LLMProviderError`/truncation, returns an `AssistantTurn` or raises `MetricResolutionProviderError(stage)`.
5. `DeepSearch.aclose()` closes everything once.

### Layer 4 — Backing

- **Shared caller, one funnel:** D6 and the stated drift risk make the shared funnel the only non-duplicating option; lifting (not copying) is what the spec's "lifted helper" names.
- **`owns_caller` over idempotency:** the standalone runners must keep closing their own caller, and the feature must be the single closer of the shared one; an explicit flag states which, and idempotency only covers an accidental extra call.
- **Turn typed in `clients/`:** nothing above the client layer sees an SDK message, matching the C3.1.1 rule that result contracts live in `clients/`.
- **No R1 behavior change:** the delegate preserves `_call_providers`'s signature, events, and return; the M1 inline loop is untouched; a regression test pins both.
- **Honest `run`:** the feature realizes ownership and ordering now; it does not invent the R1→R2 data path, which is later and unspecified.

---

## 8. Build checklist (todos — execute in order after approval)

1. `clients/llm_provider.py`: add `ToolCall`/`AssistantTurn`; move the two `llm_provider.*` event constants here; add `generate_turn` to the protocol + both adapters + `_build_assistant_turn`; add `StructuredLLMCaller` (`call_structured` lifted, `call_turn`, idempotent `aclose`, `providers`); add `create_structured_llm_caller`.
2. `exceptions/deep_search.py`: add `MetricResolutionError` base + `MetricResolutionProviderError`.
3. `requirement_interpretation.py`: R1 takes the caller (`+ owns_caller`), derives `self._providers`; `_call_providers` delegates; `aclose` owns-guarded; `create_requirement_interpretation` builds/accepts the caller; re-export the two event constants.
4. `amenity_search.py`: `AmenitySearch` gains keyword-only `llm_caller` + `owns_caller`; `aclose` owns-guarded; `create_amenity_search` builds/accepts the caller.
5. `deep_search.py` (new): `DeepSearch` feature class + `create_deep_search` composition root (factories in order).
6. Update the 4 R1 unit tests to wrap the fake in a `StructuredLLMCaller`.
7. `feature_tests/test_c3_1_2_structured_llm_caller.py` (new): the offline fixture set (Section 6).
8. `deep_search_context.md`: add the one C3.1.2 build note (Section 0).
9. Run the offline tests and the full existing deep_search suite; confirm green.

## Verification

- **Offline:** `python -m pytest tests/services/deep_search/ backend/src/services/deep_search/feature_tests/test_c3_1_2_structured_llm_caller.py` (from `backend/`) — new fixtures pass; the 4 updated R1 suites and all prior suites stay green (regression). The fixtures cover turn fallback, truncation→fallback, exhaustion→`MetricResolutionProviderError`, no-fallback-on-returned-turn, tool-call parsing, `tools`/`tool_choice` passthrough with no `response_format`, the lifted-funnel regression, and the ownership/idempotent-close lifecycle.
- **Regression spot check:** run one existing R1 runner (e.g. `python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run`) to confirm the moved event constants and the delegated funnel still print the same attempt trail.
