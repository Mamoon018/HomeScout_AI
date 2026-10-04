---
name: diagnostic-logger
description: Use when the implementation agent writes or extends backend code, to decide what that code should log. Produces logs that let a person or a debugging agent reconstruct the path to a failure after the fact, without re-running — by recording the boundary crossings, silent drifts, and state changes that form the path, each with the state that drove it, threaded by a correlation id. Opinionated about what earns a log line AND what must not, so the trail stays readable because every line is always visible.
---

# Diagnostic Logger

Logging is the program writing down what it did, as it did it, so the story can be read back by someone who wasn't there. Its one goal here: **let a reader reconstruct the path to a failure after the fact, without re-running the program.** Not auditing, not metrics — those are separate concerns with separate tooling, and a log that tries to be all three serves none.

Two readers consume these logs, and both must be served:

- **A person** — brings outside context, tolerates some prose, scans.
- **A debugging agent** — has only the trace, needs structure it can filter and correlate mechanically.

They agree on substance (both need the path's events and the cause) and diverge on form, so the resolution is **structured data that is also human-legible** — one stream, not two.

The discipline in one line:

> **Log the path, not the point: the boundary crossings, silent drifts, and state-changes that led to an outcome — each carrying the state that drove it, all threaded by a correlation id — and nothing that merely narrates success.**

---

## Core principle: a failure is a point, a cause is a path

An exception tells you *where* the program fell and *what* broke. It almost never tells you *why* — the cause is usually several steps upstream, in a dependency's response or a silent drift that finished running and left no trace in the stack. Logging exists to capture that upstream path, so the reader can walk back from the symptom to the cause.

So two honest expectations bound everything below:

- **Logs localize; they do not state the cause.** A good log narrows "something is wrong somewhere" down to "here, under these conditions." The final inference — and confirmation at the source — is still the reader's. A log is testimony, not a confession.
- **Logs can only reveal what the code recorded.** You cannot conjure, after a failure, a line the code never wrote — and code that was skipped (an early raise, a missed release) logs nothing. For failures that emerge across requests or over time (resource exhaustion, leaks), event logs localize but run out; the drift skill (prevention) and metrics (time-series) finish the job. Logging does its share and stops at its boundary.

---

## What earns a log line: the path is three node types

A log line is earned only where **knowing what happened here would change where a debugger looks next** — and, crucially, where that knowledge *could not be recovered by re-running the code from inputs already logged.* That last clause is what keeps the list short: a purely internal, deterministic step is reproducible, so logging it adds nothing. The three node types are exactly the things that are **not** reproducible that way:

1. **Boundary crossings** — data or control entering/leaving the system or a major component: request in, call out to a dependency, its response, a commit. The data from *outside* is non-deterministic and unrecoverable after the fact, so it must be captured as it crosses. These also answer the first debugging question — *is the fault mine, or did it arrive from across the boundary?*
2. **Silent drifts** — a **recover/degrade** raises nothing and continues, so its line is the *only* evidence it happened — it always earns a node. A **reject** rides its exception and is logged once at the boundary where it's handled, so it is *not* a separate drift line. (Expanded in the Drift check rule.)
3. **State changes / side effects** — the program changed the world: a row written, a status transitioned, a message published. The world-change isn't in any input and can't be replayed, so record it. Half of debugging is "what state did we leave behind."

The failure itself is the endpoint (an ERROR with its driving state). The three above are the path *to* it, and they are what the skill must fight for — they're the ones people skip.

**Why there is no "decisions" node.** A branch is not its own node. Either its condition came from *outside* — in which case that value is already captured at the **boundary** it crossed — or it was computed *internally and deterministically*, in which case it is reproducible from inputs already logged, and writing its output would be logging a *point* (a result), not a *path* (a cause). A branch driven by **accumulated or shared mutable state** that *isn't* reproducible from this run's inputs is the one real exception — and that belongs under **state changes** (log the state where it is established), not as a branch line. So you never log "took branch X"; you log the boundary data, the drift, or the state change that the branch acted on.

### Each node logs the *why*, not the *that*

A node records **the state that mattered, not that it happened** — the few fields that let a reader judge whether this step was right. For a boundary: the request's key inputs, or a dependency response's meaningful fields (status, count, error) — not the whole payload. For a state change: what changed and the value it changed to. Log tightly: the handful of fields that explain the event, never a dumped object that buries them, and never a bare label (`"saved"`, `"done"`) that a reader can't act on.

### The thread

Every node in one run carries the same **correlation id** plus minimal shared context (which user, which resource). This is what lets either reader pull the failing run out of thousands of interleaved lines — and lets the agent do it mechanically. Without the thread, concurrency turns the log into confetti: all the right events, no way to reassemble one story.

---

## Levels classify; they do not hide

All logs are kept and visible — there is no gate that suppresses lines in normal operation, because the trail must be there for the one-off failure you cannot reproduce. Levels label *how far a node sits from a failure*, so a reader can sort — they do not decide whether a line exists:

- **ERROR** — a failure happened (the endpoint).
- **WARN** — a drift was handled (recover/degrade): abnormal, but survived.
- **INFO** — the backbone of the path: boundaries and state changes. Always on.
- **DEBUG** — fine detail for zooming into a specific problem.

Because nothing is hidden, **the write-time node filter is the only defense against noise.** That raises the bar for it, rather than lowering it: every line written is a line the reader always pays for.

---

## Workflow

1. **Write the operation** (happy path + its handled drifts, per the implementer skill).
2. **Walk the three node types** against this operation: which boundary crossings, silent drifts, and state changes are present?
3. **Filter each candidate:** would this line help a reader answer *what did the program do and why* if something downstream breaks? If it records a node → keep. If it records mere position/success → drop.
4. **For each kept line, attach the driving state** (the few fields that explain it) and the **correlation id + context**.
5. **Set the level** by distance-from-failure (ERROR / WARN / INFO / DEBUG).
6. **Confirm the silent drifts are covered:** every recover/degrade has a WARN line (see rules).

---

## Rules

Named checks; apply each with context, not as a recited line.

### Node check — *path, not position*
A line is earned only at a boundary crossing, a silent drift, or a state change — never at an internal branch, whose outcome is reproducible from inputs already logged. The test: *if something downstream breaks, would this line help answer "what did the program do and why" — and could I not just recover it by re-running?* If it only says "execution reached here," or merely records a deterministic result, it is narration — cut it.

### Drift check — *log the silent ones; let the loud ones ride*
A **reject** raises an exception; log it **once at the boundary where it's handled**, not at the throw and again at every catch. A **recover/degrade** raises nothing and continues — it is the silent failure, and its WARN line is the *only* signal it exists. Every recover/degrade must be logged; an unlogged one is a silent failure wearing new clothes.

### Driving-state check — *why, not that*
Each node carries the state that *mattered*, not a bare label a reader could infer. For a boundary, the key inputs or the response's meaningful fields; for a state change, what changed and to what. Never log the output of a deterministic internal computation — it's a reproducible *point*, not a cause. No "entering/took-branch/exiting" lines. Attach the few determining fields; never dump a whole object.

### Thread check — *one story out of many*
Every node carries a correlation id and minimal shared context, so a run is reconstructable and filterable mechanically. No orphan lines that can't be tied to their run.

### Cost check — *every line is always paid for*
There is no gate; the reader sees all of it. Narration, re-logged facts across layers, derivable data, and per-iteration loop spam are pure cost that buries the signal (and for the agent reader, costs attention to read). When in doubt, don't log — and if a line wouldn't change where a debugger looks, it isn't a node.

---

## Example

A checkout that degrades when a pricing dependency times out. The bug: the fallback returns `None` instead of a safe `0.0`.

```python
def checkout(request):
    log.info("request_received", req=rid, op="checkout", user=request.user_id)   # boundary in + thread anchor
    cart = load_cart(request.user_id)                 # success, nothing branched → no line
    rate = fetch_discount_rate(request.user_id, rid)
    total = apply(cart.subtotal, rate)                # TypeError surfaces here when rate is None
    save_order(request.user_id, total)
    return OrderResult(total)

def fetch_discount_rate(user_id, rid):
    try:
        return pricing_client.get_rate(user_id, timeout=2).rate
    except Timeout:
        log.warning("pricing_degraded", req=rid, op="checkout",            # the silent drift — MUST be logged
                    user=user_id, reason="timeout", fallback_rate=None)
        return None                                    # the bug: should be 0.0
```

**What the exception alone gives** — the point, not the path:
```
TypeError: unsupported operand type(s) for -: 'int' and 'NoneType'  at apply  (rate is None — but why?)
```

**What the log gives** — three lines, threaded by `req`:
```
INFO  req=7a3f op=checkout user=42 event=request_received
WARN  req=7a3f op=checkout user=42 event=pricing_degraded reason=timeout fallback_rate=None
ERROR req=7a3f op=checkout user=42 event=checkout_failed error=TypeError at=apply rate=None
```

The WARN is the line that cracks it — a recover/degrade that raises nothing and would otherwise be invisible. It reconstructs the path: *pricing timed out → degrade fired → fallback produced `None` → `None` reached `apply` → crash.*

**It localizes but does not state the cause.** The WARN says "degraded to `fallback_rate=None`," not "the fallback is wrong." The reader connects: from the log the fallback produced `None`; from the exception `None` is unusable; from judgment, a degrade must continue *safely* — so the fallback should have been `0.0`. The log pointed at the room; the reader gave the verdict.

**Cost:** the full trail is three lines. No `entering checkout`, no `cart loaded`, no `computing total` — `load_cart` and `save_order` succeeding got nothing, because execution reaching the next node already implies they ran. The one line that solves it is a single WARN; a noisier log would have buried it while adding nothing the solution used.