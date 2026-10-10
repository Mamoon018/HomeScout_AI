---
name: backend-test-writer
description: Use when the user wants tests written or planned for backend implementation code. Reads the implementation, decides which behaviors are worth protecting, and produces a reviewable test-plan document — one entry per test covering the behavior, the test type, what is real vs. mocked, and the evidence that the test actually proves the behavior. Stops at the plan for user review; writing and running the tests are to-do items executed only after approval.
---

# Backend Test Writer

This skill plans backend tests. Its deliverable is a **plan document**, not test code. The plan is a review gate: the agent produces it and stops. Writing and verifying the tests are to-do items carried inside the plan, done only after the user approves.

The guiding principle behind everything below:

> Test the decisions the code makes, at a boundary where the outcome is observable, using real dependencies for the things that can actually be wrong (your logic, your database) and fakes only for what is non-deterministic, costly, or outside the system — and only if a bug there would genuinely matter.

---

## Structure

The plan document is a list of entries, **one per planned test**. Each entry has six fields:

1. **Test name & target** — the test's name and the resource (function, method, endpoint) it tests. The name should read as a statement of the guaranteed behavior.
2. **Core behavior of the resource** — one or two lines on what the resource is actually supposed to do. This is the yardstick the test is judged against.
3. **Behavior under test** — the single behavior this test checks. One behavior per test.
4. **Type of test** — `unit` / `integration` / `e2e`. This sets the expectation for field 5: unit leans faked edges, integration uses a real database/broker, e2e goes through the real entry point.
5. **Real vs. mocked** — exactly what is used for real and what is faked, for this test. Must be consistent with the type in field 4.
6. **Evidence** — why the asserted outcome actually proves the behavior in field 3, rather than just re-asserting the implementation. If this field can't be stated convincingly, the test is probably tautological — drop or rethink it.

The document ends with a **to-do list**:
- [ ] Write the tests from each entry above
- [ ] Run them and verify each fails for the right reason (break the behavior; confirm the test catches it)

---

## Deciding what to test

A behavior is worth a test only if it passes **all three** filters:

- **It's a decision** — the code chose something: a branch, a calculation, a validation, a transformation, a raised error, a state change. Not a language/framework guarantee.
- **It has stakes** — if it were wrong, something real would be harmed. Rank by blast radius: data integrity, money, auth, anything a downstream consumer relies on.
- **It can plausibly break** — it's complex (branches, boundaries, edge cases) or it changes often. Stable straight-line code with no decision rarely surprises anyone.

For each behavior that passes, walk these five **break-categories** and pick the *representative* cases (one per equivalence class, not every permutation):

- **Happy path** — valid input, intended outcome.
- **Boundaries** — empty, zero, one, max, off-by-one, range edges.
- **Invalid / absent input** — nulls, missing fields, wrong types, malformed data.
- **Failure modes** — downstream call fails, record missing, constraint violated, concurrent conflict.
- **State & side-effects** — the DB row actually changed, the right event fired, state is now correct.

**Do not test:** framework/library behavior, language features, trivial accessors, private helpers directly (reach them through public behavior), or config with no logic.

---

## Workflow

1. **Read the implementation** — understand the resource and its real behavior before planning anything.
2. **Decide what to test** — apply the three filters and five break-categories to produce the list of behaviors worth protecting.
3. **Write the plan document** — one Structure entry per test, then the to-do list.
4. **Stop and hand the plan to the user for review.** Do not write test code yet.
5. *(After approval, per the to-do list)* write the tests, run them, and verify each fails for the right reason. You need to write tests files in folder C:\Users\Hp\Documents\HomeScout_AI\backend\src\services\deep_search\feature_tests

---

## Rules

Each rule is a check with a purpose. Apply it with context, not as a recited line.

### Real-vs-mock check — *keep the test connected to reality*
- Never mock your own domain logic — it's the thing under test.
- Don't mock the database's query logic. Persistence, SQL, constraints, and transactions only work against a real engine; use a real/ephemeral DB for anything that touches them.
- Fake only what is non-deterministic, slow, costly, or outside the system (third-party APIs, email/SMS, anything that spends money or can't be rolled back).
- Control time, randomness, and ID generation by injection so output is deterministic.
- **Guard:** if removing a mock would let a real bug slip through, that mock is hiding the bug, not isolating the test.

### Behavior-not-implementation check — *survive legitimate refactors*
- Assert on observable outcomes: return values, state changes, persisted rows, emitted events, API responses.
- Use interaction assertions ("called `save()` once with X") only when the interaction *is* the behavior (e.g., must-not-double-charge, email must be sent). Otherwise they break on harmless restructuring.

### Determinism check — *keep the signal trustworthy*
- Same input, same result, every run. No reliance on wall-clock, randomness, network, or test ordering.
- A flaky test is worse than no test — it trains people to ignore red.

### Effectiveness & ineffectiveness check — *self-audit each test*
A test is **effective** if it is: behavior-focused, deterministic, fast enough to run constantly, isolated, and failure-informative (the message points at the cause). The decisive question: *would this catch a real bug, and would it stay silent on a non-bug?* Both halves must hold.

A test is **ineffective / harmful** — fix or discard it — if it is any of:
- **Tautological** — mocks everything, then asserts the mocks were called.
- **Brittle** — bound to internals; breaks when nothing observable changed.
- **Flaky** — passes/fails nondeterministically.
- **Over-mocked** — so much is faked it no longer resembles production.
- **Testing the framework** — verifying the ORM saves or the router routes.

### Scope / what-NOT-to-test check — *stay lean*
- One behavior per test; representative cases per equivalence class, not every permutation.
- Coverage is a diagnostic, never a target — don't write tests to move a number.
- Honor the "Do not test" list. Deciding what to leave out is as important as what to include.

---

## Examples

**Ineffective — tautological, over-mocked:**

```python
def test_create_user():
    repo = Mock()
    service = UserService(repo)
    service.create_user("a@b.com")
    repo.save.assert_called_once()   # only proves the code calls the code
```
Everything real is faked; the assertion re-states the implementation. If `save` persisted the wrong data, or the email validation were broken, this stays green.

**Effective — behavior-focused, real DB:**

```python
def test_create_user_persists_and_rejects_duplicate(db):
    service = UserService(UserRepository(db))   # real repository, real DB

    user = service.create_user("a@b.com")
    assert db.get_user(user.id).email == "a@b.com"   # state actually changed

    with pytest.raises(DuplicateEmailError):          # real failure mode
        service.create_user("a@b.com")
```
Asserts observable outcomes (row persisted, duplicate rejected) against a real database, so it catches the bugs most likely to occur — and survives refactors that don't change behavior.