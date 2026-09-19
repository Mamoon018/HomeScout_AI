# Implementation Plan Format

> **Purpose.** It describes how the compile and structure the information in the implementation plan for the feature implementation.
>
1. **File and Module Structure:** Define how the feature and its responsibilities are distributed across files and modules, using python_code_skills, including the purpose and ownership of each file. 

The files listed in Section 1 are Build work. Name them as plan `todos`.
Do not create those files until the user confirms the plan (Build).

Section 1 **must** list a live sample runner as a new file under
`backend/src/services/deep_search/feature_sample_runs/`, named for the
mechanism (e.g. `category_inference_sample_run.py`). That runner is a
manual, stage-by-stage script against a real LLM call. It is not a test
and is not part of the request path in §E.

Seed the runner's input as dummy handoff state from the previous
mechanism (the same shape that mechanism already writes). Do **not**
re-invoke earlier mechanisms; those are already implemented and sampled.
Call this mechanism's stage methods in sequence, print a titled section
after each, and read provider-attempt / raw-body logs the way
`requirement_interpretation_sample_run.py` and
`category_resolution_sample_run.py` do.

2. **Implementation Architecture and Design Decisions:** Define the architectural choices required to implement the feature using implementation_architecture_skill Here are the details that you need to provide about this part: (In a separate file)
    Layer 1 – Glance: the shape and the seams.
    Layer 2 – Justification: what was built, why, and — critically — what was deliberately not built. This is where you verify it didn't over-engineer.
    Layer 3 – Wiring: dependency direction, composition root, request flow (reference only, read when you actually touch the code).
    Layer- 4 - Backing: Reasoning for Layer 3 approaches
    You need to provide this in a separate file. And to structure the output of the file you need to use the skills architecture-decisions-plan-format.md
> - **the contracts, the class/method blueprint, and the runtime data journey** 
    Code-Level Structure and Workflow Blueprint: Translate the feature decomposition into a   code-level structure showing the Feature → Responsibilities → Mechanism Workflows → Stage
    Methods hierarchy. Show the data contracts, supporting actors/interfaces, class and method
    signatures with one-line purposes, and the runtime journey of the data object as it is
    processed and mutated end to end. Exclude internal implementation logic except where the
    plan uses pseudocode at decision points and transformations:
    You need to use the skills of Plan_output_format.md to produce and structure the information in the implementation plan.
---

## Here the complete structure of the Implementation plan section: the contracts, the class/method blueprint, and the runtime data journey

> **Running example used throughout:** Mechanism 1 (Unstructured Input Parsing) →
> Component 1 (Requirement & Persona Extraction) and its six sub-components. The agent
> replace it with the real feature.
This is just an example for structuring the implementation plan and should not push you to think about the feature implementation details.



1. **A. Feature Map** — the skeleton, top-down. *~1 min: the shape.*
2. **B. Data Contracts** — the objects/params that flow, and their fields. *The nouns.*
3. **C. Supporting Actors & Interfaces** — contracts + implementations the feature leans on.
4. **D. Class & Method Blueprint** — every class, its methods, signatures, one-line purpose. *The map.*
5. **E. Runtime Flow — Data Object Journey** — how one request moves and mutates end to end. *The verb.*
6. **F. Method Detail** — approach pointers, only for methods whose behavior isn't obvious. *The lookup.*

**Formatting rules the agent must obey (these keep it readable):**
- Tables over paragraphs; no table cell longer than one line.
- One signature notation everywhere: `name(param: Type, ...) -> ReturnType`, with side effects marked `[mutates: <object>.<field>]` and failure marked `[raises: <Error>]`.
- **No code or pseudocode anywhere** — no functions, control flow, or syntax. Decision points and non-obvious behavior are described as **approach pointers**: short bullets naming the order of operations, the condition that branches, and the outcome of each branch. Fenced blocks are allowed **only** for the structure tree (§A) and the data-shape trace (§E), which show shape, not logic.
- Each method's one-line purpose is ≤ ~12 words and describes behavior, not restated name.
- A reader who stops after **E** must still understand how the feature processes a request.

---

## A. Feature Map

Top-down tree following the fixed hierarchy. Each node = `Name — one-line responsibility`.
No signatures here; this is orientation only.

```
Feature: Requirements Interpretation
└─ FeatureClass: RequirementsInterpreter — entry point; owns responsibility wiring
   └─ Responsibility: UserRequirementsInterpretation — turn raw input into structured requirements
      └─ Mechanism 1 Workflow: RequirementParsingWorkflow — unstructured input → separated buckets
         ├─ Stage 1: intake_and_assemble_payload — normalize + bound raw input
         ├─ Stage 2: (contract) IntermediateRepresentation schema — see §B, not a runtime method
         ├─ Stage 3: build_extraction_instruction — assemble prompt + bucket rules
         ├─ Stage 4: execute_and_validate — one constrained call → valid IR or typed error
         ├─ Stage 5: assemble_handoff — wrap validated IR as the mutable handoff object
         └─ Stage 6: (harness) extraction fixture checks — test-only, not in request path
```

> Note the two annotated nodes: not every sub-component becomes a runtime method. A schema
> is a **contract** (§B); a test harness is **test-only** and excluded from the flow (§E).

## B. Data Contracts

The objects and parameters that move through the feature. One block per contract.
This is need #1 (I/O structure) and the foundation for the runtime journey (§E).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `PayloadRecord` | bounded input for the call | `normalized_text: str` — cleaned input · `raw_text: str` — preserved original | immutable | Stage 1 → Stage 3, 4 |
| `IntermediateRepresentation` | the four separated buckets | `categories: list[Category]` · `ambiguity_flags: list[str]` · `persona_facts: list[str]` | **mutable** — 2A/2B append later | Stage 4/5 → Component 2A, 2B |
| `Category` | one stated category + its traits | `name: str` · `characteristics: list[str]` (empty `[]`, never null) | with parent | inside IR |
| `ExtractionError` | typed failure signal | `code: str` · `message: str` · `stage: str` | immutable | Stage 1/4 → caller |

> Rules to surface here: empty bucket = `[]` not omitted; closed schema (`additionalProperties:false`);
> which object is mutable and why (the IR is read more than once and accumulated across 2A/2B).

## C. Supporting Actors & Interfaces

Contracts the feature depends on but does not implement inline. Need #4. Signatures only —
the *why it's abstracted* lives in the architecture file.

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `LLMProvider` | interface | `generate_structured(schema: Schema, prompt: str) -> dict [raises: ProviderError]` | `OpenAIProvider` (primary), `GroqProvider` (fallback) | Stage 4 |
| `IRSchema` | schema/contract | derived from the Pydantic IR model; passed to provider to constrain output | one (the IR model) | Stage 3, 4 |
| `ResponseValidator` | component | `validate(raw: dict) -> IntermediateRepresentation [raises: ValidationError]` | one (concrete) | Stage 4 |

## D. Class & Method Blueprint

The static structure with signatures. One block per class, ordered by the hierarchy in §A.
Need #1 (params) + need #3 (purpose, one line). No logic here — that's §F.

**`RequirementParsingWorkflow`** — orchestrates Mechanism 1 stages; holds an `LLMProvider`.
| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `run` | `run(raw_input: str) -> IntermediateRepresentation [raises: ExtractionError]` | drive stages 1→5 for one request |
| `intake_and_assemble_payload` | `(raw_input: str) -> PayloadRecord [raises: ExtractionError]` | validate length/encoding, normalize, keep raw |
| `build_extraction_instruction` | `(schema: IRSchema) -> str` | assemble bucket rules + few-shot prompt |
| `execute_and_validate` | `(payload: PayloadRecord, prompt: str) -> IntermediateRepresentation` | run constrained call, primary→fallback, validate |
| `assemble_handoff` | `(ir: IntermediateRepresentation) -> IntermediateRepresentation` | return the mutable object 2A receives |

## E. Runtime Flow — Data Object Journey

How one request travels and how the object changes at each step. Need #2. This is the
section that shows *how the feature processes a user request.*

**Step-by-step trace** (test harness Stage 6 excluded — not in the request path):

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `intake_and_assemble_payload` | `raw_input: str` | `PayloadRecord` | `{normalized_text, raw_text}` |
| 2 | `build_extraction_instruction` | `IRSchema` | `prompt: str` | payload unchanged |
| 3 | `execute_and_validate` | payload, prompt, `LLMProvider` | validated `IntermediateRepresentation` **or** `ExtractionError` | 4 buckets populated, empties = `[]` |
| 4 | `assemble_handoff` | validated IR | same IR, marked mutable | handed to Component 2A |

**Transformation trace (shape only):**
```
str
 → PayloadRecord{ normalized_text, raw_text }
 → (+ prompt)
 → dict (raw provider output)
 → IntermediateRepresentation{ categories[], ambiguity_flags[], persona_facts[] }   # valid
   | ExtractionError{ code, message, stage }                                          # invalid → whole response rejected
```

**Approach at the real decision point (primary→fallback + reject-on-invalid):**
- Providers are tried in a fixed order: primary (OpenAI) first; the fallback (Groq) is attempted only if the primary fails to return a response.
- Which provider is primary is a bound dependency, decided at the composition root — not inside this stage (see the architecture file).
- The schema constrains the output **at generation time** (structured output / strict tool use), so the response is shaped to the contract before it is inspected.
- Whatever provider responds, the response is then validated as an **independent second check**.
- Validation is all-or-nothing: any invalid or out-of-contract field rejects the **whole** response — no partial or best-effort acceptance.
- Two distinct exits, each a typed error naming the stage: one for "no provider returned a response," a separate one for "response failed validation."

## F. Method Detail

Deep reference, **selective** — include only methods whose behavior a signature can't convey.
One block per such method: Purpose · What it does (approach pointers, no code) · Inputs · Outputs · Failure.

**`intake_and_assemble_payload`**
- **Purpose:** produce one bounded, normalized payload so behavior tracks content, not formatting.
- **What it does:** reject non-English; reject `< 100 words` and empty/whitespace with the under-limit error; normalize while **preserving** line breaks/bullets/quotes; keep a copy of raw text; no character offsets.
- **Inputs:** `raw_input: str` · **Outputs:** `PayloadRecord` · **Failure:** `ExtractionError("under_limit"|"non_english")`.

---

### Checklist the agent runs before emitting this section

- [ ] Every contract in §B that a method passes appears in that method's signature in §D.
- [ ] Every actor in §C is depended on by at least one class in §D.
- [ ] The mutable object is identified in §B and its accumulation shown in §E.
- [ ] §E excludes test-only and construction-only steps; it is the request path only.
- [ ] No code or pseudocode anywhere; decision points are described as approach pointers. Fenced blocks appear only for the §A tree and the §E shape trace.
- [ ] A reader can stop after §E and still explain how a request is processed.
- [ ] No "why it's abstracted" reasoning here — that stays in the architecture file.
- [ ] Section 1 lists a live sample runner under `feature_sample_runs/`.
- [ ] Section 4 describes how to run that sample runner and what it prints.

---

# 4. Sample Runner and Dummy-Provider Fixture Set

Every mechanism plan has this section. Two distinct checks; neither is in the
request path in §E.

## 4.1 Live sample runner (required)

A new file in `feature_sample_runs/`. Manual, stage-by-stage, one real LLM
call for **this** mechanism only.

**How to run it** — from `backend/`, the `python -m ...` command.

**What it seeds** — dummy handoff state as after the previous mechanism.
Earlier mechanisms are not called. The seeded input must **not** reuse the
mechanism's prompt worked-pair inputs (same persona facts, explicit nodes,
or payload wording). The live call is a new use case for judgement, not a
replay of the few-shots.

**What it prints** — one titled section per stage (input state, schema,
instruction, provider attempts, validated body, written state). On typed
failure: exception class, `stage`, message; non-zero exit. Nothing written
to disk.

## 4.2 Dummy-provider fixture set

Pytest with a fake `StructuredLLMProvider`. No live calls. Asserts strip,
stamp, reject-body, and other code-path rules the live runner cannot prove
deterministically.