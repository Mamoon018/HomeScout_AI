---
name: Iteration Report skill
description: Use when given an old component spec, the implementation plan that built it, and an updated spec, and asked what changes in the existing implementation. Produces independent ADD / MODIFY / REMOVE points, each with its artifacts and a before/after top-down tree traceflow. Does not write the new implementation plan.
---

# Spec Iteration Report

## Purpose

An implemented component is being iterated. The new spec mixes already-built behaviour with new requirements. Produce a Report: which independent points are added, modified or removed, which technical artifacts each point touches, and how the component's traceflow changes for each. This is stage one. The implementation plan for the new spec comes later and is not written here.

Answer **what changes and where**, never **how to implement it**. No code.

## Inputs

- **Old spec** and **old implementation plan**: together they define what is built.
- **New spec**: the target.

If any of the three is missing or unreadable, stop and ask for it. Do not work from memory.

Artifact names come only from the old plan. Anything not in the plan is marked `(illustrative)`. A change the new spec implies but does not state is marked `(inferred)`.

## Method

1. Draw the component's current traceflow from the old spec and plan, stage by stage, naming the artifact behind each stage.
2. Split both specs into **independent points**. A point is independent if it could be built, tested or reverted without the others. Example: "open and close a session in the same task" is one point. Split a requirement that bundles several.
3. Match old points to new points by meaning and classify each (below).
4. For each point, list its artifacts from the plan, including supporting ones: tests, fixtures, sample runner, config, exceptions, docs.
5. Draw a before/after traceflow for each point.

## Point classes

| Class | Meaning |
|---|---|
| **ADD** | In the new spec, not in the old. Needs new artifacts and a place in the flow. |
| **MODIFY** | In both, changed. Needs changes to existing artifacts, plus supporting ones. |
| **REMOVE** | In the old spec, not in the new. State the **code fate**: `deleted` or `retained` (only the requirement or check goes away). |
| **DECISION-GATED** | The new spec contradicts something the build already decided or rejected, such as a build-time correction. Do not classify. Show both outcomes. |
| **UNCHANGED** | Same in both. List for confirmation only. |

Check the new spec against the build-time corrections in the old spec and plan. A correction the new spec drops or contradicts is DECISION-GATED, not an assumption.

## Traceflow rules

Every traceflow is a **top-down tree** in a fenced text block. Never side-by-side columns.

**Format**
- Draw it with box-drawing characters: `├─`, `└─`, `│`, and `──►` for "returns" or "leads to". Do not use `+--`, `|` or `->`. (These characters are not ASCII; that is intended. The point is a monospace diagram a reader can scan.)
- The root is the component entry point, or the artifact the point touches. Children are the steps it runs, indented one level per call depth.
- One step per line, written as a short action phrase or a method name. Outcomes (ok, failure, branch) are child lines with `──►`, and the arrows of sibling lines are aligned.
- Keep lines under about 95 characters.

**Markers**
- Tag every line that is new, changed or removed, not only the root of the change.
- Use `◄── NEW`, `◄── CHANGED`, `◄── GONE`. In the current-flow and final-summary diagrams use the point ID instead (`◄── A1`, `◄── M2, R1`).
- All markers in one diagram start in the same column: pad each tagged line to the longest tagged line plus three spaces. Untagged lines get no marker.
- Unchanged lines stay untagged. A short plain note after the text is allowed ("kept, unused").

**Scope and layout**
- Show each point inside the surrounding component flow, so the reader sees where it attaches, with only the siblings needed for that.
- BEFORE and AFTER are two separate fenced blocks, each headed by its label on its own line. DECISION-GATED points use AS BUILT and IF INTENDED the same way.
- Keep each diagram scoped to its own point. If two points touch one artifact, show the combined result once, in the final summary flow.
- Show behaviour as well as structure: what the caller now gets, what now fails and where, what now costs more, each as a child line.

Example AFTER block:

~~~
AFTER
```
Exporter
├─ export(report_id)
├─ export_csv(report_id)                       ◄── NEW
│    ├─ load the report                        ◄── NEW
│    └─ write the rows                         ◄── NEW
│         ├─ file written  ──► ExportResult    ◄── NEW
│         └─ write fails   ──► ExportFailure   ◄── NEW
└─ cleanup()
```
~~~

## Output

1. **Confirmation.** Inputs read; what "implemented" means; what was not available (for example the repo); counts per class.
2. **Current traceflow with change locations.** Mark each point's ID where it lands. Add an index table: `ID | Class | one-line summary`.
3. **ADD points.**
4. **MODIFY points.**
5. **REMOVE points.**
6. **DECISION-GATED points.**
7. **Unchanged.** Short list.
8. **Component traceflow after all points.** One combined flow, each change tagged with its ID.
9. **Flags.** Conflicts, silent drops, facts that disagree across documents, values the new spec leaves open, assumptions that affect scope.

Each point uses this block:

~~~
### <ID>: <short name>

| Artifact | Change |
|---|---|
| <file> (<plan #>) · <symbol> | <action>: what changes in this artifact and why this point needs it |

BEFORE
```
<top-down tree of the current flow, no markers>
```

AFTER
```
<top-down tree with ◄── NEW / ◄── CHANGED / ◄── GONE, markers in one column>
```

Behaviour change: <one sentence>
~~~

The Change cell is a short description, not a label. Start with the action (`add`, `modify`, `remove`, `check only`), then say **what** changes in that artifact (the behaviour, contract or value) and **why** this point needs it. One or two sentences, no code. A bare "add" or "modify" is not enough.

REMOVE points add `Code fate: deleted | retained`.
DECISION-GATED points show **AS BUILT** and **IF INTENDED** as two stacked blocks (same rules as BEFORE and AFTER), list the artifacts the second would touch, and say it was not planned for.

IDs: `A1…` ADD, `M1…` MODIFY, `R1…` REMOVE, `D1…` DECISION-GATED, `F1…` flags. Keep them stable across follow-ups.

## Before answering

- Every new-spec requirement is in exactly one point or in Unchanged.
- Every old-spec requirement is in Unchanged, MODIFY or REMOVE.
- Every artifact comes from the plan or is labelled.
- Every point has BEFORE/AFTER and a `Behaviour change` line.
- Every traceflow is a top-down tree; BEFORE and AFTER are separate blocks; markers sit in one aligned column.
- No code and no implementation steps.

After delivering, offer the next stage (the implementation plan) and wait for the answer.

## Sample output

An abridged sample for an invented component, showing shape only. Do not reuse its names or wording.

````text
# Report Exporter: old spec -> new spec

## 1. Confirmation
I read the old spec, the old plan and the new spec. "Implemented" means old spec + plan,
including the plan's build-time note "a failed render is never re-rendered automatically".
The repo was not available, so artifact names come from the plan (#n = plan item number).
Names marked (illustrative) are not in the plan. Result: 1 ADD, 1 MODIFY, 1 REMOVE,
1 DECISION-GATED.

## 2. Current traceflow, change locations
```
caller ──► Exporter.export(report_id)               exporter.py (#3)
│
├─ load_report ──► ReportRepo.get                   (#4)
│     └─ CSV branch attaches here                          ◄── A1
├─ render_pdf ──► RenderClient.call                 (#5)
│     ├─ timeout 30 s                                      ◄── M1
│     └─ failure ──► ExportFailure                         ◄── D1
├─ write_temp ──► TempStore.save                    (#6)
├─ notify ──► Mailer.send                           (#7)   ◄── R1
└─ return ExportResult(path)
```

| ID | Class          | Summary                                   |
|----|----------------|-------------------------------------------|
| A1 | ADD            | CSV export alongside PDF                  |
| M1 | MODIFY         | PDF render timeout 30 s -> 60 s           |
| R1 | REMOVE         | Email on completion                       |
| D1 | DECISION-GATED | New spec: re-render on failure            |

## 3. ADD
### A1: CSV export
| Artifact | Change |
|---|---|
| exporter.py (#3) · Exporter.export_csv (illustrative) | add: a second entry point that loads the report, converts it to CSV without calling the render service, and returns the same ExportResult shape |
| ExportFormat contract (illustrative) | add: a small typed value (pdf or csv) so callers choose the format and the exporter can branch on it |
| CsvWriter (illustrative) | add: turns report rows into a CSV file and hands it to the existing temp-file step |
| test_exporter.py (#9) | add: a CSV fixture that checks the output file and confirms the render service is never called |

BEFORE
```
Exporter.export
├─ load_report
├─ render_pdf ──► write_temp
└─ return ExportResult
```

AFTER
```
Exporter.export
├─ load_report
├─ render_pdf ──► write_temp
├─ CsvWriter.write ──► write_temp       ◄── NEW
│     └─ RenderClient is never called   ◄── NEW
└─ return ExportResult
```

Behaviour change: callers can request CSV and get a file without the render service.

## 4. MODIFY
### M1: PDF render timeout 30 s -> 60 s
| Artifact | Change |
|---|---|
| render_client.py (#5) · timeout value | modify: the per-call render timeout goes from 30 s to 60 s so slow reports finish instead of failing |
| test_exporter.py (#9) · timeout case | modify: the forced-timeout test must use the new 60 s limit, otherwise it checks the old behaviour |
| config.py (#2) | check only: confirm the timeout is a constant in the client and not a setting; no change expected |

BEFORE
```
RenderClient.call
└─ timeout 30 s ──► ExportFailure
```

AFTER
```
RenderClient.call
└─ timeout 60 s ──► ExportFailure   ◄── CHANGED
```

Behaviour change: slow renders that used to fail at 30 s now succeed up to 60 s.

## 5. REMOVE
### R1: Email on completion
Code fate: deleted
| Artifact | Change |
|---|---|
| mailer.py (#7) · Mailer | remove: the class is no longer used because the new spec drops email on completion |
| exporter.py (#3) · notify step | remove: the call after the temp-file step goes, so export ends by returning the result |
| .env.example (#8) · SMTP keys | remove (inferred): only Mailer read these keys, so they have no reader left |

BEFORE
```
Exporter.export
├─ write_temp
├─ notify ──► Mailer.send
└─ return ExportResult
```

AFTER
```
Exporter.export
├─ write_temp
├─ notify removed   ◄── GONE
└─ return ExportResult
```

Behaviour change: no email is sent when an export finishes.

## 6. DECISION-GATED
### D1: Re-render on failure
The new spec says a failed render is retried by re-rendering. The plan's build-time note
says this was rejected (it created duplicate billed renders).

AS BUILT
```
render_pdf fails
└─ ExportFailure is returned
     └─ no automatic re-render
```

IF INTENDED
```
render_pdf fails
└─ re-render once                       ◄── NEW
     └─ still fails ──► ExportFailure   ◄── NEW
touches: Exporter.export, RenderClient, the "failure" tests (#9),
         the plan's rejected-options table
```

Not planned for. Confirm before anything else.

## 7. Unchanged
PDF rendering, temp storage, repository lookup, ExportResult contract.

## 8. After all points
```
caller ──► Exporter.export
│
├─ load_report
├─ render_pdf, timeout 60 s         ◄── M1
├─ CsvWriter.write ──► write_temp   ◄── A1
├─ write_temp
├─ notify removed                   ◄── R1
└─ return ExportResult(path)
```

## 9. Flags
| #  | Flag                                                              |
|----|-------------------------------------------------------------------|
| D1 | Re-render sentence contradicts the plan's build-time note          |
| F1 | New spec does not say whether CSV needs its own size limit         |
````
