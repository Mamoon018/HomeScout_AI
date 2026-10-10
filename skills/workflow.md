# Implementation Workflow — Using `split-into-prs` During Feature Development

How the skill is incorporated into actually building a feature. The skill partitions; this workflow is how you drive implementation with it.

---

## Phase 0 — Finalize specs

- Finalize the specs for **all** sub-components of the component(s) of the mechanism.
- Each sub-component spec must state what it **reads**, **does**, and **produces** — this *is* the READS/WRITES the skill needs.
- A spec too thin to state its reads/produces is flagged by the skill (`INSUFFICIENT SPEC`) — fix it before proceeding, or its dependencies stay invisible.

## Phase 1 — Run the skill once (global partition)

- Run `split-into-prs` across **all** finalized specs at once.
- Output: the **initial wave structure + DAG** —
  - the **initial foundation** (only the contracts the PR(s) **first under consideration** actually need — not every contract the whole feature will eventually need),
  - which fan-out PRs are **parallel-safe** (no edge between them),
  - which are **convergence** PRs,
  - each PR's spec (contract exposed/consumed, reads, writes, lands-before, assumed-contract note).
- This is the **first** partition, not the final one. The DAG derived from specs is the starting picture; the foundation **extends as PRs progress** and dependencies surface (Phases 4–6). You do **not** decide PR-5's dependencies while on PR-1 and PR-2.

## Phase 2 — Implement the initial foundation first

- **Scope rule (strict): the foundation only ever carries the dependencies of the PR(s) under consideration — nothing more.**
  - Implementing **one PR** → bring only **that PR's** dependencies into the foundation.
  - Implementing **two (or more) PRs in parallel** → consider **their** dependencies **together**, at the same time, and bring those into the foundation.
  - **Never** look at or pre-load the dependencies of a PR not yet under consideration (e.g. don't touch PR-5's dependencies while on PR-1/PR-2).
- What gets frozen: **type shapes AND function signatures** the PR(s) under consideration need.
- The foundation is **not a one-time upfront block.** It is **built incrementally** — it carries exactly the current PR(s)' dependencies and **extends via later foundation PRs** as the next PRs come under consideration and dependencies surface (Phases 4–6).
- Merge the foundation to trunk. Every later worktree branches from the current frozen base.

## Phase 3 — Implement fan-out PRs (parallel where the DAG allows)

- Fan-out PRs branch from the frozen foundation.
- PRs with **no edge between them run in parallel** — do not serialize what the DAG proved parallel-safe.
- Each PR keeps a **living implementation-plan file**:
  - the full split of classes, functions, dependencies, contracts, and how they come together,
  - **updated as implementation proceeds** — emergent decisions get written back, so the file ends as the *finalized, realized* plan.

## Phase 4 — Detect emergent dependencies (local trigger, per PR)

- **Trigger (cheap, local, no comparison):** while planning/implementing a PR, check that **every surface it READS resolves** to either its own code or the frozen foundation.
- An **unresolved READ** = a dependency has emerged (needs something that isn't in its spec and isn't in the foundation).
- Each PR runs this check **for itself, continuously** — no knowledge of other PRs required.
- No unresolved READ → nothing emerged → the PR just proceeds.

## Phase 5 — Classify the emerged dependency (comparison, only now justified)

- An unresolved READ fires → **now** run **cross-plan comparison** against other in-flight PRs' plans.
- Comparison is the **classifier**, not the detector — it answers *is this shared*:
  - **Shared** (another PR also produces/needs the same surface) → **true shared dependency** → extract into a **foundation PR**, rebase the affected PRs onto updated trunk, both import it.
  - **Local** (only this PR needs it) → just **absorb it into this PR**; no foundation change.

## Phase 6 — Progress plan (the output of a triggered reconciliation)

- Fires **on a trigger only** — **never on a schedule**. The two trigger kinds are detected differently:
  - **Emergent / shared dependency** → *detected* by the **unresolved-READ check** (Phase 4), then classified by comparison (Phase 5).
  - **Contract change** → **not detected, declared.** It originates at the **producer** by decision — a PR changes a surface it already froze/published, or you approve changing an already-frozen contract. Whoever makes the change knows it; there is nothing to "catch" at the source. Its **fan-out** (which dependents are affected) is then read from the **DAG**, and the dependents' mismatch is caught at **Phase 8** (assumed vs. realized).
- States one of:
  - **Proceed, no adjustment** — the PR continues untouched; or
  - **Adjustment required** — the exact contract to extract into a foundation PR + which on-going PRs must rebase from the updated trunk.
- After an adjustment: affected PRs rebase onto updated trunk, then continue in parallel.

## Phase 7 — Respond to an unsettled contract: extract-now vs. assume-and-note

- Applies whenever a PR needs a contract whose shape **isn't available frozen yet** — whether it's a **brand-new** contract not settled yet, or a **declared change** (Phase 6) not yet realized. *This is the response strategy, not the act of changing a contract.*
- **If the shape is settled/known** → **extract-now**: freeze it in a foundation PR, dependent imports the real thing (producer + consumer run in parallel).
- **If the shape is NOT settled yet** (genuinely still being worked out) → **assume-and-note**, as a **short-lived bridge, never a holding state**:
  - the dependent **assumes** the shape and **keeps moving**,
  - records an **Assumed-contract note** (local, write-once) — the exact assumed shape + what must be realized,
  - **as soon as the shape settles it is realized as a foundation PR** — frozen on trunk, not deferred; the dependent **rebases, converting assumed → realized**.
- **We never defer realization.** Anything implemented is treated as **finalized the moment it settles** — frozen as a foundation PR until a future change supersedes it. There is no "approved but not yet realized" state left floating, because an unrealized contract lives nowhere on trunk and every PR branching in that window would build on something frozen nowhere.
- Note the distinction from Phase 6: **declaring** a change to an already-exposed contract is the *trigger*; **this phase** is only about how a dependent *proceeds* when the shape it needs isn't frozen yet.

## Phase 8 — Merge-time reconciliation (assumed → realized check)

- A PR may have ended **differently from its initial plan** (Phase 3's emergent incorporation), so the realized contract can differ from what dependents assumed.
- **At each merge** (PR → trunk), for every not-yet-merged dependent:
  - check its **Assumed-contract note against the just-merged PR's realized contract**,
  - **Match** → merge clean,
  - **Differ** → foundation adjustment + rebase, then merge.
- This is distinct from Phase 5: Phase 5 catches dependencies emerging *during* work; Phase 8 catches the gap between *assumed* and *realized* at integration.

---

## The two checkpoints, kept distinct

| Checkpoint | When | Catches | Cost |
|---|---|---|---|
| **Unresolved-READ trigger** (Phase 4→5) | during planning/implementation | dependencies emerging mid-flight | local check cheap; comparison only on trigger |
| **Merge-time check** (Phase 8) | at each PR merge | gap between assumed and realized contract | per-dependent note check |

## Guardrails (carried from the skill)

- Only **true** dependencies enter the foundation; **tolerate incidental duplication** (private helpers nobody cross-consumes).
- Foundation stays **lean** and is **built incrementally** — it carries **only the dependencies of the PR(s) under consideration** (one at a time, or several only when implemented in parallel); never the dependencies of a PR not yet under consideration.
- **Don't re-serialize** parallel-safe PRs; run reconciliation **only on a trigger**.
- Coordination lives in the **wave/merge structure** + each PR's **local assumed-contract note** — no shared mutable plan doc.
- The upfront DAG is the **first** picture, never assumed complete — Phases 4–5 are the standing catch for what specs didn't declare.