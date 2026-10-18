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

The new spec requires the structured turn to fall back on `refusal` / non-`stop` finish_reason (M1), **and** it keeps the locked build decision *"R1 behavior is unchanged; a test covers the lifted helper against the existing R1 cases."* The build realized R1-sharing by routing R1 through the **same** `generate_structured` / `_decode_body` (the structured path was R1's own, lifted and shared, not duplicated). Confirmed in code: R1's M1 inline loop calls `provider.generate_structured` directly ([requirement_interpretation.py:275](requirement_interpretation.py:275)) and M2/M4/M5/M6 reach it via `_call_providers` → `call_structured` ([:1696](requirement_interpretation.py:1696)); both land on the one shared method. So any `refusal` / `finish_reason` check added to `_decode_body` is inherited by every R1 structured call. The decision accepts this inheritance (option a) rather than scoping it away (option b).

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
