# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.2 (Add a Tool-Turn Call to the Shared StructuredLLMCaller)

## Context

Why this change: M3 (R2 metric resolution) needs the LLM to decide when to call `web_search` and `firecrawl_crawl`, which is a *tool-calling conversation*: tool results are appended to a message history and sent back. Two things block that today:

1. The provider-fallback funnel (`OpenAI → Groq`, `LLM_PROVIDER_ORDER`) is **private to R1** — it lives as `UserRequirementsInterpretation._call_providers` inside `requirement_interpretation.py`. `AmenitySearch` (R2) cannot reach it, and copying it would drift from R1.
2. Both provider adapters are hardwired to one `generate_structured` shape: a fixed system+user message pair with a strict-JSON `response_format`. There is **no message history and no tool path**.

What C3.1.2 delivers (and only this): one shared `StructuredLLMCaller` that holds the provider chain and serves both R1 and R2; a new `generate_turn(messages, tools, tool_choice)` on the provider protocol and both adapters; the lifted fallback funnel used by both a structured call and a tool turn; a `DeepSearch` feature class + composition root that builds the caller **once** and injects it into R1 and R2 (D6); the typed `MetricResolutionProviderError`. R1's observable behavior is unchanged.

Out of scope (later sub-components, confirmed against the C3.1.2 spec at `deep_search_context.md:2815`): building the tool JSON schemas / M6→MCP name mapping, the phase-gated resolution loop, tool-argument validation (C3.1.3), URL resolution, the crawl cache, and C3.2. The tool turn **receives** tool definitions as an input; it does not build them.

Confirmed design choice (from the user): introduce the `DeepSearch` feature class now so D6 ("built once at the composition root, passed to R1 and AmenitySearch, created and closed once") is realized here, with the composition root running the factories in the correct dependency order.

Spec anchor: `backend/src/services/deep_search/feature_context/deep_search_context.md:2815-2846`.

### Iteration note (new C3.1.2 spec → this plan)

This plan has been iterated against the updated C3.1.2 spec. The full iteration report is appended at the end of this document; the delta it found is **one narrow code change (point M1)**, grounded in a read of the already-built `clients/llm_provider.py`:

- **Already built, no change:** `strict: true` constrained decoding, non-decodable-body fallback (empty / not JSON / not object), truncation (`finish_reason == length`) fallback, `MetricResolutionProviderError(stage)` on exhaustion, the two-request-mode separation, and "no schema retry." The new spec's longer wording documents these; it does not re-open them.
- **M1 (MODIFY) — the only new work:** a **structured** turn must additionally fall back when the provider returns an OpenAI `refusal` (a decline) or a non-`stop` `finish_reason` other than `length` (e.g. `content_filter`). Today `_read_first_choice` never reads `message.refusal`, and `_decode_body` special-cases only `length`, so a decodable-but-declined/filtered body is silently accepted. M1 converts both into `LLMProviderError` so the funnel falls back, and raises the typed `MetricResolutionProviderError(stage)` if every provider declines.
- **Resolved decision (D1 → option a):** M1 lands in the **single shared** `_decode_body` / `_read_first_choice`, so R1 (its M1 inline loop *and* its M2/M4/M5/M6 calls through `call_structured`) inherits the checks. A per-call scoping flag (option b) was rejected because it re-splits the one shared funnel this sub-component exists to unify (D6). R1's happy path is unchanged; the R1 regression suites (todo #7) plus the lifted-funnel regression (#6) are re-run and confirmed green as part of M1. The defensive Pydantic parse named in the spec's strict-mode decision remains the **consumer's** job (C3.1.6 / C3.2.2), not this caller.

The sections below carry M1 into the file/module list, the method blueprint, the runtime flow, the per-method drift breakdown, the async map, the logging table, the fixture set, the architecture decisions, and the build checklist, so the plan still reads as one grounded implementation plan rather than a patch.

---

## 0. Cross-mechanism check (updates to earlier mechanisms)

| Earlier piece | Finding | Action in this plan |
| --- | --- | --- |
| `requirement_interpretation.py` fallback funnel | `_call_providers` (`:1674`) is R1-private; 7 call sites (M2/M4/M5/M6 at `:484,519,661,854,996,1195,1411`) | **Lift** the funnel body into `StructuredLLMCaller.call_structured`; `_call_providers` becomes a thin delegate — same signature, same events, same return `(body, answered_by)`. Call sites untouched. |
| R1 constructor | `UserRequirementsInterpretation.__init__(providers)` (`:154`) | Takes the shared `StructuredLLMCaller` + `owns_caller: bool`. Derives `self._providers = caller.providers` so the M1 inline loop and `aclose` still read it. |
| R1 M1 inline funnel | `execute_and_validate` (`:252`) has its own loop with different events (`extraction.provider_attempt`) and `ExtractionProviderError` | **Left as-is.** A prior locked decision (`async_conversion_architecture_decisions.md:87`) rejected unifying it because event names and error types differ. It reads `self._providers`, still available. **Iteration (M1):** its loop body is untouched, but the `provider.generate_structured` it calls (`:275`) now also rejects `refusal` / non-`stop` finish_reason, so R1's extraction inherits the new fallback (D1 option a). Re-verify its suite (#7). |
| **Iteration (M1): shared structured validation** | `_read_first_choice` / `_decode_body` / `generate_structured` in `clients/llm_provider.py` are the one structured path for R1 and R2 | **Add** the refusal / non-`stop` finish_reason checks here once; both R1 structured entry points (the M1 inline loop at `:275`, and M2/M4/M5/M6 via `call_structured` at `:1696`) inherit them. No per-call opt-out flag (D1 option a; option b rejected — it re-splits the shared funnel, D6). |
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
| 1 | `backend/src/clients/llm_provider.py` | Modify | Add `ToolCall` / `AssistantTurn` contracts; add `generate_turn` to the protocol and both adapters; add `StructuredLLMCaller` (`call_structured` lifted, `call_turn` new, `aclose`); add `create_structured_llm_caller`; move the two `llm_provider.*` event-name constants here. **Iteration (M1):** also modify `_read_first_choice` to read `message.refusal`, `generate_structured` (both adapters) to thread it through, and `_decode_body` to reject a populated `refusal` and a non-`stop`/non-`length` `finish_reason` as `LLMProviderError` (the shared structured path — D1 option a). |
| 2 | `backend/src/exceptions/deep_search.py` | Modify | Add `MetricResolutionError` base + `MetricResolutionProviderError` (ClassVar `stage` + `__init__(*, stage=None)`), following the `MetricDefinitionError` trio shape. No Validation sibling yet (nothing raises it until C3.1.3). |
| 3 | `backend/src/services/deep_search/requirement_interpretation.py` | Modify | R1 takes the shared caller (`+ owns_caller`); `_call_providers` delegates to `caller.call_structured`; `aclose` closes the caller only when owned; `create_requirement_interpretation` builds/accepts the caller; re-export the two moved event constants. |
| 4 | `backend/src/services/deep_search/amenity_search.py` | Modify | `AmenitySearch.__init__` adds keyword-only `llm_caller` + `owns_caller`; `aclose` closes the caller only when owned; `create_amenity_search` builds/accepts it. |
| 5 | `backend/src/services/deep_search/deep_search.py` | **New** | `DeepSearch` feature class (owns the shared caller; holds R1 + R2; sequences R1 then R2 in correct order; `aclose` closes the caller once) + `create_deep_search(settings)` composition root that runs the factories in dependency order. |
| 6 | `backend/src/services/deep_search/feature_tests/test_c3_1_2_structured_llm_caller.py` | **New** | Offline fixtures (Section 6) with a fake provider exposing `generate_turn`/`generate_structured`. **Iteration (M1):** add refusal-fallback, `content_filter`-fallback, and both-providers-decline → `MetricResolutionProviderError(stage)` cases, plus a "decodable body still succeeds" guard so the two paths never collide. |
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

**Structured-path helpers (Iteration M1 — modify the existing ones; shared by R1 and R2).** The structured call keeps returning a raw `dict`; the only change is two more fallback triggers, added once in the shared helpers.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `_read_first_choice` | `(response) -> tuple[str \| None, str \| None, str \| None]` | now returns `(content, finish_reason, refusal)` so the decode step can see a decline |
| `_decode_body` | `(*, provider: str, model: str, content: str \| None, finish_reason: str \| None, refusal: str \| None) -> dict [raises: LLMProviderError, LLMResponseTruncatedError]` | add refusal + non-`stop`/non-`length` finish_reason rejection ahead of the existing empty/JSON checks |
| `generate_structured` (both adapters) | unchanged signature → `dict` | read `choice.message.refusal` and pass it into `_decode_body`; no change to `call_structured` |

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

**Structured-path per-call validation (Iteration M1).** The tool turn above is unchanged; the iteration only widens the structured call's per-provider accept/reject decision. Inside one `generate_structured` attempt the order is fixed — **truncation → refusal → abnormal finish_reason → empty → decode**, all before a body is accepted:

| # | Step | Reads | Produces / outcome |
| --- | --- | --- | --- |
| 1 | `finish_reason == "length"` | finish_reason | `LLMResponseTruncatedError` (an `LLMProviderError`) → next provider |
| 2 | `refusal` populated | refusal (OpenAI only) | `LLMProviderError` → next provider |
| 3 | `finish_reason` non-`stop` and non-`length` (e.g. `content_filter`) | finish_reason | `LLMProviderError` → next provider |
| 4 | empty content | content | `LLMProviderError` → next provider |
| 5 | not JSON / not an object | content | `LLMProviderError` → next provider |
| 6 | otherwise | content | `dict` body → the provider answered |

When every provider trips one of 1–5, `call_structured`'s existing exhaustion branch raises `provider_error_cls(stage)` (`MetricResolutionProviderError` for M3). Steps 2–3 are the new ones; 1, 4, 5, 6 already exist. A returned, decodable, non-refused, `stop` body is a success and its schema contents never trigger fallback (strict mode guarantees schema validity).

### F. Method Detail

**`generate_turn` (both adapters)** — call `self._client.chat.completions.create(model=self._model, messages=messages, tools=tools, tool_choice=tool_choice)` inside the same SDK-exception mapping used by `generate_structured` (timeout / rate-limit / auth / catch-all → `LLMProviderError`). Read the first choice; if `finish_reason == _TRUNCATED_FINISH_REASON` raise `LLMResponseTruncatedError`. Else build `AssistantTurn`: copy `content`; map each `message.tool_calls[i]` to `ToolCall(id, function.name, function.arguments)`; build `message` as `{"role":"assistant","content":content}` plus a `"tool_calls"` list in OpenAI shape when present. No `response_format` is sent.

**`call_turn`** — loop `self._providers`; `try generate_turn`; on `LLMProviderError` log `LLM_PROVIDER_ATTEMPT_EVENT` (`outcome:"failed"`, `stage`, `provider`, `model`, `detail` from `exc`+`__cause__`) and continue; on success log `outcome:"answered"` and return; after the loop log `llm_provider.rejected` and raise `provider_error_cls(msg, stage=stage)`. Mirrors `call_structured` exactly (same events, same logger).

**`call_structured`** — the current `_call_providers` body verbatim (events, `__cause__` detail, raw-body debug line, `(body, answered_by)` return), with `provider_error_cls` and `stage` as required parameters (no service-exception default — `clients/` must not import a `services`-owned default). **Iteration M1 touches nothing here** — the new rejections live one layer down in `generate_structured`/`_decode_body`, so `call_structured`'s exhaustion branch raises the same typed error with no edit.

**`_decode_body` (Iteration M1 — modified, shared by R1 and R2).** Keep the existing order and add two checks at the front so a declined/filtered response never reaches the decode step. Order: (1) `finish_reason == "length"` → `LLMResponseTruncatedError` (unchanged); (2) **`refusal` non-empty → `LLMProviderError`** (OpenAI sets `message.refusal` on a decline; Groq never sets it, so the check is a no-op there); (3) **`finish_reason` is neither `stop` nor `length` (`content_filter`, and any other non-`stop` stop) → `LLMProviderError`** (do not accept a filtered/odd-stop body even when its partial content decodes); (4) empty content → `LLMProviderError` (unchanged); (5) `json.loads` / non-dict → `LLMProviderError` (unchanged); else return the `dict`. The exact non-`stop` set to reject is "anything other than `stop` or `length`" — `tool_calls` as a stop reason cannot occur because `tools` is never sent on a structured call (flag F4). Inputs: `content`, `finish_reason`, `refusal`. Outputs: `dict`. Failure: `LLMProviderError` / `LLMResponseTruncatedError`, both of which the funnel treats as "this provider did not answer" and falls back.

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

**`_decode_body` (Iteration M1 — modified)**
- Core behavior: turn one provider's structured response into a `dict`, or reject it so the funnel falls back.
- Drifts handled: **model declines the request** (OpenAI `refusal` populated, with decodable content that would otherwise be accepted as a real answer) → caught in this **core** helper (the dependency's response is a boundary into the funnel) → **rejected** as `LLMProviderError`, so the next provider is tried and, if all decline, `MetricResolutionProviderError(stage)` is raised rather than a decline being mistaken for an answer. · **response filtered / abnormally stopped** (`finish_reason` of `content_filter` or any non-`stop`, non-`length` value, possibly carrying partial-but-decodable content) → caught here → **rejected** as `LLMProviderError` (de-masks a filtered body that would otherwise pass the JSON check). · **shared-path regression** (R1 inherits these checks) → handled by **re-verifying** the R1 suites (#7) + lifted-funnel regression (#6), since the happy path is untouched and only a decline/filter edge changes — a signalled change, not a silent one.
- Left out: a same-provider retry on refusal/filter — *imaginary* (locked rule: provider fallback is the recovery, never a retry on the same provider). · reading a provider-specific refusal shape beyond OpenAI's `message.refusal` — *not live* (Groq exposes no refusal field; F1). · widening the rejected finish_reason set to speculative values — *wrong boundary / not live* ("anything other than `stop`/`length`" already covers `content_filter`; `tool_calls` cannot occur with no `tools` sent — F4). · defensive Pydantic validation of the decoded body — *wrong boundary* (the consumer C3.1.6/C3.2.2 owns it; `call_structured` returns a raw `dict` — F3).

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
| M1 refusal / finish_reason checks | read `refusal` + `finish_reason` off the already-awaited response | depends only on that one response | event loop (inline in the coroutine) | sequential, before the body is accepted | none — trivial string/None comparisons, no I/O and no offload |
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

**Iteration M1 — no new log node.** A refusal / abnormal-finish_reason rejection raises `LLMProviderError` inside `generate_structured`, which `call_structured` already catches and records as `llm_provider.attempt` (`outcome:"failed"`) with the exception message carried in `detail`. The distinguishing text ("…returned a refusal", "…finish_reason content_filter") goes into that existing `detail`, so the degrade is already visible on the path (the silent-drift rule is satisfied) without adding a line that would be re-logged at two layers (cost rule). `_decode_body`'s existing `llm.generate_structured` INFO node already carries `finish_reason`; no change there.

---

## 6. Offline Fixture Set

No live sample runner (see the note under Section 1). The tool turn is proven deterministically here.

`feature_tests/test_c3_1_2_structured_llm_caller.py` — pytest, a hand-written `FakeStructuredProvider` exposing `name`/`model`/`generate_structured`/`generate_turn`/`aclose` (queued bodies/turns; raises `LLMProviderError` when told to fail). No live calls. Asserts:

| Area | Assertion |
| --- | --- |
| Turn fallback | provider 0 raises `LLMProviderError` → provider 1's `AssistantTurn` returned; attempt trail logged |
| Truncation | `finish_reason=="length"` → `LLMResponseTruncatedError` from `generate_turn` → funnel falls back; both truncated → `MetricResolutionProviderError(stage=...)` |
| Exhaustion | all providers raise → `MetricResolutionProviderError` with the given `stage`; no silent swallow |
| Refusal fallback (M1) | provider 0's `generate_structured` returns a populated `refusal` (decodable content present) → `LLMProviderError` → provider 1's body returned; both refuse → `MetricResolutionProviderError(stage)`; `content` was decodable so this proves the refusal, not the body, drove the fallback |
| Filtered finish_reason (M1) | `finish_reason == "content_filter"` with decodable content → `LLMProviderError` → fallback; a `stop` finish_reason with the *same* content is accepted (guards against over-rejection — the check is finish_reason-driven, not content-driven) |
| No over-reach (M1) | a normal `stop` + decodable body + no `refusal` returns the body with no fallback, confirming M1 adds no regression to the happy path (the R1-shared surface) |
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
| M1: refusal / non-`stop` finish_reason rejected in the shared `_decode_body` | new spec: a structured turn falls back on a decline or a filtered/odd stop | a declined or `content_filter` body with decodable content is accepted as a real answer, then corrupts the downstream resolution on garbage |

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
| Scope M1's refusal / finish_reason checks to M3 only via a per-call flag (D1 option b) | rejected | re-splits the one shared funnel this sub-component exists to unify (D6); option a chosen — R1 inherits the checks, which only improves its decline/filter handling, with the R1 regression suites (#7) + lifted-funnel regression (#6) re-verified green |
| A new "refusal" exception type distinct from `LLMProviderError` | rejected | the funnel already recovers on `LLMProviderError`; a refusal is just "this provider did not produce a usable body," so it reuses that signal — no new type earns its place |

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

1. `clients/llm_provider.py`: add `ToolCall`/`AssistantTurn`; move the two `llm_provider.*` event constants here; add `generate_turn` to the protocol + both adapters + `_build_assistant_turn`; add `StructuredLLMCaller` (`call_structured` lifted, `call_turn`, idempotent `aclose`, `providers`); add `create_structured_llm_caller`. **Iteration M1:** modify `_read_first_choice` to also return `refusal`, `_decode_body` to reject a populated `refusal` and a non-`stop`/non-`length` `finish_reason`, and both adapters' `generate_structured` to thread `choice.message.refusal` through (shared path — D1 option a).
2. `exceptions/deep_search.py`: add `MetricResolutionError` base + `MetricResolutionProviderError`.
3. `requirement_interpretation.py`: R1 takes the caller (`+ owns_caller`), derives `self._providers`; `_call_providers` delegates; `aclose` owns-guarded; `create_requirement_interpretation` builds/accepts the caller; re-export the two event constants.
4. `amenity_search.py`: `AmenitySearch` gains keyword-only `llm_caller` + `owns_caller`; `aclose` owns-guarded; `create_amenity_search` builds/accepts the caller.
5. `deep_search.py` (new): `DeepSearch` feature class + `create_deep_search` composition root (factories in order).
6. Update the 4 R1 unit tests to wrap the fake in a `StructuredLLMCaller`.
7. `feature_tests/test_c3_1_2_structured_llm_caller.py` (new): the offline fixture set (Section 6).
8. `deep_search_context.md`: add the one C3.1.2 build note (Section 0).
9. Run the offline tests and the full existing deep_search suite; confirm green. **Iteration M1:** re-run the 4 R1 suites (#7) and the lifted-funnel regression (#6) specifically, confirming R1's inherited structured-path behavior is unchanged on the happy path and only declines/filters now fall back (D1 option a).

## Verification

- **Offline:** `python -m pytest tests/services/deep_search/ backend/src/services/deep_search/feature_tests/test_c3_1_2_structured_llm_caller.py` (from `backend/`) — new fixtures pass; the 4 updated R1 suites and all prior suites stay green (regression). The fixtures cover turn fallback, truncation→fallback, exhaustion→`MetricResolutionProviderError`, no-fallback-on-returned-turn, tool-call parsing, `tools`/`tool_choice` passthrough with no `response_format`, the lifted-funnel regression, the ownership/idempotent-close lifecycle, and (Iteration M1) refusal→fallback, `content_filter`→fallback, both-decline→`MetricResolutionProviderError(stage)`, and the no-over-reach happy-path guard.
- **Regression spot check:** run one existing R1 runner (e.g. `python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run`) to confirm the moved event constants and the delegated funnel still print the same attempt trail.

---
---

# Appendix: Iteration Report (source of the M1 changes woven above)

> Verbatim stage-one iteration report that this plan was updated against. The sections above are the implementation decisions derived from it; this appendix is the report as delivered.

# Iteration Report: C3.1.2 — Tool-Turn Call on the Shared `StructuredLLMCaller` (old spec → new spec)

## 1. Confirmation

I read all three inputs — no memory, no guessing:

- **Old spec:** the committed (HEAD) C3.1.2 section of `deep_search_context.md` (the plan's anchor, `:2811-2846`). The working tree of this file already carries the new-spec edits, so HEAD is the genuine old spec; `git diff HEAD` isolates the delta exactly.
- **Old implementation plan:** `r2_mechanism_3_c3_1_2_implementation_plan.md` (artifact numbers below use its Section 1 todo numbers: **#1** `clients/llm_provider.py`, **#2** `exceptions/deep_search.py`, **#3** `requirement_interpretation.py`, **#4** `amenity_search.py`, **#5** `deep_search.py`, **#6** `feature_tests/test_c3_1_2_structured_llm_caller.py`, **#7** the 4 R1 unit tests, **#8** the `deep_search_context.md` build note).
- **New spec:** `R2_Mechanism_3_draft_spec.md`, C3.1.2 section (`:134-155`).

"Implemented" means old spec + plan. The repo **was** available, so I grounded the classification by reading the built code (`clients/llm_provider.py`): `generate_structured`→`_read_first_choice`→`_decode_body`, `_build_assistant_turn`, `call_structured`, `call_turn`. Symbols named from that read that are not in the plan's todo list are marked `(illustrative)`. A change the new spec implies but does not state is marked `(inferred)`.

**Result: 1 MODIFY (carrying a recorded scope decision, D1 — resolved), 0 ADD, 0 REMOVE, the rest UNCHANGED.** The spec grew substantially in words, but almost every new sentence either *documents behaviour the build already has* or *imposes no code change*. The one genuine code delta is narrow: the structured path must treat an OpenAI `refusal` and a non-`stop` / `content_filter` `finish_reason` as provider failures that fall back. D1 (where that check lives, given the path is shared with R1) was open; it is now **resolved — option (a): R1 inherits the checks, regression re-verified** (see §6).

Why the delta is this small — grounded in the built code:

| New-spec element | Already built? | Evidence |
|---|---|---|
| `strict: true` constrained decoding | **Yes** | `_build_response_format` sends `strict: True` (#1) |
| Non-decodable body (empty / not JSON / not object) → fallback | **Yes** | `_decode_body` raises `LLMProviderError` on each (#1) |
| Truncation (`finish_reason == length`) → fallback | **Yes** | `_decode_body` + `_build_assistant_turn` raise `LLMResponseTruncatedError` (#1) |
| `MetricResolutionProviderError(stage)` on exhaustion | **Yes** | `call_structured` raises `provider_error_cls` when no provider answers (#1) |
| Two request modes never combined | **Yes (structural)** | `call_turn` sends `tools` only; `generate_structured` sends `response_format` only (#1) |
| No schema retry / no schema-driven fallback | **Yes** | no retry branch exists in `call_structured` (#1) |
| **OpenAI `refusal` → fallback (structured turn)** | **No** | `_read_first_choice` reads only `content`, `finish_reason` — never `message.refusal` (#1) |
| **non-`stop` / `content_filter` `finish_reason` → fallback (structured turn)** | **No** | `_decode_body` special-cases only `length`; any other non-`stop` reason with decodable content is accepted (#1) |

---

## 2. Current traceflow, change locations

```
StructuredLLMCaller                                              clients/llm_provider.py (#1)
│
├─ call_structured(instruction, user_content, json_schema, schema_name, stage, err_cls)
│   └─ loop providers in LLM_PROVIDER_ORDER
│        ├─ provider.generate_structured  ──► chat.completions.create(response_format strict:true)
│        │    ├─ SDK timeout/ratelimit/auth/other ──► LLMProviderError ──► next provider
│        │    └─ _read_first_choice ──► (content, finish_reason)
│        │         └─ _decode_body
│        │              ├─ finish_reason == length ──► LLMResponseTruncatedError ──► next
│        │              ├─ (refusal populated) ──► accepted today, no check            ◄── M1
│        │              ├─ (finish_reason content_filter / non-stop) ──► accepted today ◄── M1
│        │              ├─ empty content ──► LLMProviderError ──► next
│        │              ├─ non-JSON / non-object ──► LLMProviderError ──► next
│        │              └─ ok ──► dict body
│        ├─ a provider answered ──► (body, answered_by)
│        └─ all providers failed ──► provider_error_cls(stage)   [MetricResolutionProviderError]  ◄── D1
├─ call_turn(messages, tools, tool_choice, stage, err_cls)
│   └─ loop providers
│        ├─ provider.generate_turn ──► _build_assistant_turn
│        │    ├─ finish_reason == length ──► LLMResponseTruncatedError ──► next
│        │    ├─ no content & no tool_calls ──► LLMProviderError ──► next
│        │    └─ ok ──► AssistantTurn{content, tool_calls, message}
│        └─ all providers failed ──► provider_error_cls(stage)
└─ aclose()  (idempotent, _closed flag)
```

| ID | Class          | Summary                                                                                  |
|----|----------------|------------------------------------------------------------------------------------------|
| M1 | MODIFY         | Structured turn falls back on OpenAI `refusal` and non-`stop`/`content_filter` finish_reason |
| D1 | DECISION-GATED (resolved → a) | Check lives on the structured path **shared with R1**; decided: R1 inherits it, regression re-verified |

---

## 3. ADD points

None. The new spec adds no new artifact, stage, or entry point. Every new sentence lands on the existing structured path or is documentation.

---

## 4. MODIFY points

### M1: Structured turn falls back on `refusal` and abnormal `finish_reason`

Old spec: *"Fallback happens on `LLMProviderError`, including a response cut short by the token limit. It never happens for a returned invalid body."* New spec: the structured turn **additionally** falls back on a populated OpenAI `refusal` field (a decline) and on a `finish_reason` that is `length`, `content_filter`, or any non-`stop` stop. `length` is already handled; `refusal` and the other non-`stop` reasons are not. The defensive Pydantic parse named in the same new-spec decision is the **consumer's** job (C3.1.6 triage, C3.2.2 resolution), not this caller — `call_structured` still returns a raw `(dict, str)`.

**Decided scope (D1, option a — approved).** The check goes into the single shared `_decode_body` / `_read_first_choice`, so **R1 inherits it** on every structured call — the M1 inline `execute_and_validate` loop *and* the M2/M4/M5/M6 calls through `_call_providers` → `call_structured` (both land on `provider.generate_structured`). This is preferred over a per-call opt-out flag because one shared funnel is the whole point of C3.1.2 (D6: "a second copy would drift"); a flag would re-split the validation into R1-rules vs M3-rules. It is safe for R1: the happy path (`stop` + content, no refusal) is unchanged, and the only new R1 behaviour is falling back on a decline/`content_filter` that returns non-empty decodable content (today accepted, then validated downstream on a declined body) — strictly more correct. "R1 behaviour unchanged" holds on every tested case; re-verification is rerunning #7 + the lifted-funnel regression and confirming green.

| Artifact | Change |
|---|---|
| `clients/llm_provider.py` (#1) · `_read_first_choice` (illustrative) | modify: also read `choice.message.refusal` and return it, so the decode step can see a decline. Today it returns only `(content, finish_reason)`, so a refusal is invisible to the funnel. |
| `clients/llm_provider.py` (#1) · `_decode_body` (illustrative) | modify: before the empty/JSON checks, raise `LLMProviderError` when `refusal` is populated (OpenAI-only; Groq has no such field, so absent → no effect) and when `finish_reason` is a non-`stop` value other than `length` (e.g. `content_filter`). This converts "declined / filtered" into a fallback trigger instead of silently accepting a decodable-but-filtered body. |
| `clients/llm_provider.py` (#1) · `generate_structured` (both adapters) | modify (inferred): pass the refusal through from the SDK choice into `_decode_body` (the SDK exposes it on `choice.message.refusal`). No signature change to `call_structured`. |
| `feature_tests/test_c3_1_2_structured_llm_caller.py` (#6) | modify: add fake-provider cases — a populated `refusal` → fallback, both refuse → `MetricResolutionProviderError(stage=…)`; a `content_filter` finish_reason → fallback. Keep the existing "no fallback on a returned decodable body" case so the two never collide. |
| `deep_search_context.md` (#8) · C3.1.2 build note | modify: record that the structured path now rejects `refusal` / non-`stop` finish_reason as provider failures (the working tree already rewrote the note's `MetricResolutionValidationError` justification; this extends it to the implemented behaviour). |

BEFORE
```
call_structured
└─ provider.generate_structured
     └─ _decode_body
          ├─ finish_reason == length ──► LLMResponseTruncatedError ──► next provider
          ├─ empty content           ──► LLMProviderError ──► next provider
          ├─ non-JSON / non-object   ──► LLMProviderError ──► next provider
          └─ ok                      ──► dict body
```

AFTER
```
call_structured
└─ provider.generate_structured
     └─ _decode_body
          ├─ refusal populated       ──► LLMProviderError ──► next provider   ◄── CHANGED
          ├─ finish_reason not stop  ──► LLMProviderError ──► next provider   ◄── CHANGED
          │     (length still ──► LLMResponseTruncatedError)                  ◄── CHANGED
          ├─ empty content           ──► LLMProviderError ──► next provider
          ├─ non-JSON / non-object   ──► LLMProviderError ──► next provider
          ├─ ok                      ──► dict body
          └─ both providers declined ──► MetricResolutionProviderError(stage) ◄── CHANGED
```

Behaviour change: a structured turn where the model declines (`refusal`) or is cut off/filtered (non-`stop` finish_reason) now falls back to the other provider, and raises the typed `MetricResolutionProviderError(stage)` if both do — instead of today's path, where a decodable-but-filtered body could be accepted as success.

---

## 5. REMOVE points

None. The old "open verification: whether each provider accepts `tools` and `response_format` in one request" is dropped from the new spec, but it was never implemented (no combined-mode request exists in the code), so there is nothing to delete. See Unchanged (mode separation) and flag F3.

---

## 6. DECISION-GATED points

### D1: The new structured-turn validation lives on the path shared with R1 — RESOLVED (option a)

**Decision (approved):** option (a) — R1 inherits the checks; the R1 regression is re-verified. Rationale and safety analysis are in M1's "Decided scope" block. D1 stays recorded here for traceability; it is no longer open.

The new spec requires the structured turn to fall back on `refusal` / non-`stop` finish_reason (M1), **and** it keeps the locked build decision *"R1 behavior is unchanged; a test covers the lifted helper against the existing R1 cases."* The build realized R1-sharing by routing R1 through the **same** `generate_structured` / `_decode_body` (the structured path was R1's own, lifted and shared, not duplicated). Confirmed in code: R1's M1 inline loop calls `provider.generate_structured` directly (`requirement_interpretation.py:275`) and M2/M4/M5/M6 reach it via `_call_providers` → `call_structured` (`:1696`); both land on the one shared method. So any `refusal` / `finish_reason` check added to `_decode_body` is inherited by every R1 structured call. The decision accepts this inheritance (option a) rather than scoping it away (option b).

(Note: R1 already falls back when a refusal yields *empty* content, because `_decode_body` rejects empty content today. The new behaviour changes R1 only in the edge where a decline/filter returns **non-empty, decodable** content — rare, but a real behaviour change on a shared method.)

AS BUILT
```
_decode_body  (one shared helper)
├─ R1 extraction calls ──► uses it unchanged
└─ M3 structured calls ──► uses it unchanged
     └─ refusal / content_filter with decodable content ──► accepted as success
```

IF INTENDED (new spec applied)
```
_decode_body  (shared)
├─ refusal populated       ──► LLMProviderError          ◄── NEW
├─ finish_reason not stop  ──► LLMProviderError          ◄── NEW
├─ R1 extraction calls ──► now inherit the two checks    ◄── NEW  (regression surface)
└─ M3 structured calls ──► get the intended fallback     ◄── NEW
touches: clients/llm_provider.py (#1) _decode_body / _read_first_choice / generate_structured,
         the R1 unit tests (#7) and the lifted-funnel regression test (#6),
         the plan's "R1 behavior unchanged" regression decision
```

**Resolution: option (a), approved.** R1's structured calls inherit the two new checks; the R1 regression cases (#7) and the lifted-funnel regression (#6) are re-verified green before M1 is considered done. Option (b) (a per-call/per-stage flag scoping the checks to M3) was rejected because it re-splits the shared funnel the C3.1.2 build exists to unify (D6). The new spec named the behaviour but not the scope; the scope is now fixed by this decision.

---

## 7. Unchanged (confirm only)

Already built, and the new spec either documents the existing behaviour or imposes no code change:

- **`strict: true` constrained decoding** — `_build_response_format` already sends it (#1).
- **No schema retry / no schema-driven fallback** — no such branch exists (#1).
- **Non-decodable body (empty / not JSON / not object) → fallback** — already in `_decode_body` (#1). The old spec's "never for a returned invalid body" simply mis-described the code; the new spec corrects the text. Code fate: none. See flag F2.
- **Truncation → fallback** (`finish_reason == length`) — `_decode_body` and `_build_assistant_turn` already raise `LLMResponseTruncatedError` (#1).
- **`MetricResolutionProviderError(stage)` on exhaustion** — `call_structured` already raises the injected `provider_error_cls` (#1). M1 widens its trigger set automatically (refusal / finish_reason now reach exhaustion); the error contract itself is unchanged.
- **`MetricResolutionValidationError` deferred to C3.1.3** — still unbuilt (#2); unchanged.
- **Two request modes never combined** — structurally true today (`call_turn` → `tools` only; `generate_structured` → `response_format` only) (#1). Renamed from "Tools and structured output are separate requests"; the open-verification question is now "moot by construction." No code change.
- **Ownership / `DeepSearch` / `create_deep_search` / `owns_caller`** — unchanged (#5, #3, #4).
- **Message format (OpenAI chat, provider-neutral), `parallel_tool_calls` on, truncated tool calls not executed** — unchanged in `call_turn` / `_build_assistant_turn` (#1).
- **Regression: R1 behaviour unchanged** — still asserted by the new spec; see D1 for the tension M1 introduces.

---

## 8. Component traceflow after all points

```
StructuredLLMCaller                                              clients/llm_provider.py (#1)
│
├─ call_structured(...)
│   └─ loop providers (LLM_PROVIDER_ORDER)
│        └─ generate_structured ──► _read_first_choice (now also refusal)          ◄── M1
│             └─ _decode_body
│                  ├─ refusal populated        ──► LLMProviderError ──► next       ◄── M1, D1
│                  ├─ finish_reason not stop    ──► LLMProviderError ──► next       ◄── M1, D1
│                  │     (length ──► LLMResponseTruncatedError)
│                  ├─ empty / non-JSON / non-object ──► LLMProviderError ──► next
│                  └─ ok ──► dict body
│        └─ all failed ──► MetricResolutionProviderError(stage)
├─ call_turn(...)   (unchanged: truncation + empty-turn fallback, AssistantTurn)
└─ aclose()  (unchanged)
```

---

## 9. Flags

| #  | Flag |
|----|------|
| D1 | **Resolved (option a).** New refusal / finish_reason fallback sits on `_decode_body`, which is **shared with R1**. Decided: R1 inherits it; re-verify #7 + the lifted-funnel regression (#6). Option (b), a scoping flag, was rejected (re-splits the shared funnel, D6). |
| F1 | `refusal` is an **OpenAI-only** field; Groq's `generate_structured` has no refusal to read. The check is a no-op on Groq, so the fallback precision applies to the OpenAI leg only. Confirm this is acceptable (new spec says "an OpenAI `refusal`," so yes — flagging for visibility). |
| F2 | Old-spec vs built-code discrepancy, now resolved by the new spec: the old spec said fallback "never happens for a returned invalid body," but `_decode_body` has always fallen back on empty / non-JSON / non-object bodies. New spec text matches the code. No code change; noted so the reconciliation is explicit. |
| F3 | The new spec's "defensive Pydantic parse" in the strict-mode decision is the **consumer's** responsibility (C3.1.6 triage, C3.2.2 resolution), not C3.1.2 — `call_structured` returns a raw `dict`. This is out of C3.1.2's scope; confirm it is tracked on those later sub-components, not here. |
| F4 | `content_filter` is the clearest non-`stop` reason to reject, but "any non-`stop`" could include provider-specific reasons (e.g. `tool_calls` on a structured turn should not occur, since `tools` is never sent). Confirm the exact non-`stop` set M1 should treat as failure, so the check is neither too narrow nor too broad. |

---

*Stage one only. The implementation plan for the new C3.1.2 spec is the next stage and is not written here.*
