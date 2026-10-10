Split sub-components into branches — instructions

Goal: group the sub-components into branches. Each sub-component goes entirely into one branch. Do not default to one branch per sub-component — put coupled sub-components in the same branch.

Step 1 — List produces/consumes (by name).
For each sub-component, read its spec and write two lists:

Produces — the surfaces it exposes that another could use (named operations, outputs, shared types). Names only; no signatures needed.
Consumes — the surfaces it uses that another sub-component produces.

Step 2 — Draw the edges.
For every consumes that matches another sub-component’s produces, record a link producer → consumer. These links are the only facts the grouping uses.

Step 3 — Group by coupling (the one decision).
Default: each sub-component is its own branch. Put two sub-components in the same branch only when a structural test fires:

Mutual link — they consume each other (A → B and B → A). They can’t be cleanly separated → same branch.
Pair-private shared surface — they share a mutable surface used only by the two of them (no third consumer). Splitting them would duplicate or strand it → same branch.

Grouping is transitive: if A couples with B and B couples with C, all three go in one branch.

Not grounds for bundling:

“Feels cohesive” or “easier to understand together” — no.
“Easier to test together” — no; almost anything is testable in isolation, so it decides nothing.
A shared helper that a third sub-component also uses — that’s not pair-private, so leave them separate.

Step 4 — Output the branches.
List each branch with: the sub-components in it, and (for any bundled branch) which structural test put them together — the mutual link, or the pair-private surface.