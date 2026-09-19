# Section 7 — Architecture Decisions in the Implementation Plan (Output Format)

> **Purpose.** This is the *presentation layer* for Sections 3–6. The agent has already
> *reasoned* about structure (§3), boundaries (§4), approach (§4), and justification (§6).
> This section defines how it *reports* those choices inside the implementation plan, so a
> reader can grasp the architecture in ~1 minute and confirm nothing was over-built.
>
> **When to produce it.** During the **Review** step of the Workflow, after Section 6 has
> generated the per-abstraction justifications. The agent renders those justifications into
> the format below and places this block in the implementation plan under a heading such as
> *"Architecture & Modularity Decisions."*

---

## How to read this format

Three layers, ordered by increasing detail. A reader may stop after any layer and still
have a coherent picture. The agent must produce them in this order.

- **Layer 1 — Glance (A):** the shape and the seams. ~30 seconds.
- **Layer 2 — Justification (B, C, D):** what was built, why, and what was deliberately *not* built.
- **Layer 3 — Wiring (E, F, G):** dependency direction, composition root, request flow.

**Formatting rules the agent must obey (these are what keep it skimmable):**
- Tables over paragraphs. No table cell longer than one line.
- Every "why" is capped at ~12 words and stated as a **concrete, current requirement** — never "cleaner", "scalable", or "best practice."
- Layer 1 must fit on one screen with no scrolling.
- All examples below use one running case (a triage service calling an LLM and a web search) so the shape is visible; the agent replaces it with the real components.

---

## A. Architecture at a Glance

- **Shape:** one sentence naming the overall structure.
  *e.g., "A domain service behind two capability interfaces; infrastructure adapters are chosen at the composition root."*
- **Seams (where things can change independently):** 2–4 bullets, each naming one boundary and what varies across it.
  *e.g., "LLM provider — OpenAI vs on-prem model, selected per deployment."*
- **Component list:** `Name — one-line responsibility`, one per line.

## B. Component Map

Condenses the full §3 per-component detail into one scannable row each. Keep the full §3
breakdown (Interface, Integration Flow, etc.) below this table only if the reader asks.

| Component        | Owns                              | Depends on                       | Abstracted?              |
| ---------------- | --------------------------------- | -------------------------------- | ------------------------ |
| HospitalService  | triage / orchestration logic      | LLMProvider, WebSearchProvider   | — (concrete)             |
| LLMProvider      | contract for text generation      | —                                | Yes: 2 providers needed  |
| OpenAIProvider   | OpenAI SDK calls, auth, formats   | LLMProvider                      | implements               |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with its reason · `implements` = an implementation of an interface.

## C. Decisions & Justifications  ← the part that proves it isn't over-built

One row per **abstraction / interface / layer / pattern** introduced. This is Section 6's
*Cost Disclosure*, tabulated. If the last column cannot be filled with something that
breaks **today**, the item is removed from the design — not listed here as "optional."

| Decision                        | Current requirement that forced it        | What breaks today without it                              |
| ------------------------------- | ----------------------------------------- | -------------------------------------------------------- |
| Introduce `LLMProvider` interface | must support OpenAI *and* on-prem (stated) | service couples to one SDK; 2nd provider needs service edits |
| Inject providers at runtime     | provider selected per deployment (stated)  | deployment choice hard-coded into the service            |

## D. Kept Concrete / Rejected

The mirror of C, and the fastest signal that the guard did its job. Lists abstractions
that were *considered and declined*.

| Considered                        | Decision       | Reason                                          |
| --------------------------------- | -------------- | ----------------------------------------------- |
| Interface for `HospitalService`   | kept concrete  | one implementation, no stated second consumer   |
| Single generic `Provider` interface | rejected     | would merge unrelated capabilities (LLM vs search) |
| Repository / persistence layer    | not added      | no persistence requirement stated               |

## E. Dependency Direction

One or two lines. Arrows point **toward abstractions**; domain depends on contracts,
infrastructure implements them.

```
HospitalService → [LLMProvider]       ← OpenAIProvider, OnPremProvider
HospitalService → [WebSearchProvider] ← BingProvider
```

## F. Composition Root

- **Where:** the module/file that wires everything (e.g., `main` / `bootstrap` / DI container).
- **Selects:** which concrete implementation is bound to each interface, and on what input (env var, config, flag).

## G. End-to-End Flow

Numbered, entry point → result. One clause per step.

1. Request enters at `<entry point>`.
2. Calls `HospitalService`.
3. Which calls `LLMProvider` (bound to `OpenAIProvider` at the composition root).
4. Provider-specific response is mapped to an application-level contract and returned.

---

### Checklist the agent runs before emitting this section

- [ ] Layer 1 fits on one screen.
- [ ] Every row in **C** has a "breaks today" consequence; anything speculative was cut, not softened.
- [ ] **D** is non-empty if any abstraction was considered and declined (it usually should be).
- [ ] No justification uses "cleaner", "scalable", "flexible", or "best practice."
- [ ] The composition root (**F**) is named explicitly.
- [ ] Every interface in **B** appears as a row in **C** with a passing justification.
