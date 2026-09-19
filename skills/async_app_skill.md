Here is the skill defined in the same format as your example, generalized as async implementation practices rather than tied to any specific codebase.

---

# Agent Guidelines for Ensuring Asynchronous Implementation

**Name:** `ensure async implementation`

**Description:**

generates guidelines for making an application, or a feature/service inside it, run asynchronously. Determines which operations are declared **async** and **awaited**, which independent I/O-bound operations overlap their waiting time through concurrent execution, which data-dependent operations stay sequential, and which blocking or synchronous operations are moved to a worker so they do not block the event loop. Analysis runs across the full call chain, from the high-level entry layer down to the I/O operations. Covers async/await structuring, concurrency (also called non-blocking or event-loop execution), and offloading of blocking work.

**Trigger:**

when user asks how to make an application, feature, or service run asynchronously, or asks which operations to mark async/await, which to run concurrently, or how to keep blocking work off the event loop.

**Plan agent:**

Input the application or feature flow: the call chain, the operations at each layer, and their I/O touchpoints. Trace the flow from the high-level layer down to the I/O operations. At each layer, classify operations by data dependency. Mark the async boundaries (what is awaited, what runs concurrently). Flag synchronous operations that block the event loop for offloading to a worker.

**Goal:**

a layered map of the async structure. Each operation group is marked as sequential await, concurrent execution, or offloaded-to-worker, based on its data dependencies and blocking behavior. Together the map preserves required ordering while overlapping the waiting time of independent I/O operations, from the entry point down to the lowest I/O call.

**Output per layer / operation group:**

* **Layer or Operation Group Name**
* **Operations and I/O Touchpoints** (the calls in the group and where each waits on I/O)
* **Data Dependency** (data-dependent, independent, or mixed. State which operation needs which result.)
* **Execution Mode** (sequential await / concurrent via `create_task` or `gather` / offloaded to worker)
* **Shared-State Handling** (only when concurrent. State the model used, one-object or partial-results-and-merge, and the writes each concurrent operation performs.)
* **Blocking Check** (whether any operation in the group is synchronous and can block the event loop, and if so, the worker it is moved to)

**Workflow:** Map flow → Classify dependencies → Define async boundaries → Review.

**Rules:**

* Support async execution across the whole call chain, from the high-level layer down to the I/O operations.
* Start at the high-level layer. Identify what must be awaited and which independent operations can run concurrently before moving down.
* At each layer, identify data dependencies before deciding execution mode.
* Data-dependent operations that need each other's results stay sequential. Use `async`/`await` so the coroutine yields control during the I/O wait. Do not use `asyncio.create_task()` or `asyncio.gather()` for them, because they cannot make progress independently. Pattern: `A → await A → B → await B → C`.
* Independent operations with no data dependency are candidates for concurrency. Schedule and await them with `asyncio.create_task()` or `asyncio.gather()`. Pattern: `gather(A, B, C)`.
* Operations that work on different parts of shared state and progress independently can run concurrently, but their writes to shared state must be managed. Use a one-object model or a partial-results-and-merge model. Do not allow unsafe concurrent mutations or race conditions.
* Do not make every operation concurrent. Preserve required sequential dependencies. Only overlap the waiting time of independent I/O-bound operations.
* A synchronous operation is acceptable when it is intentional or unavoidable (synchronous third-party library, CPU-intensive processing, blocking SDK or API, legacy synchronous code, or a deliberately synchronous step).
* The test for a synchronous operation is whether it blocks the event loop. If it can take significant time or perform blocking I/O, do not run it directly in the event-loop thread.
* Move blocking synchronous work to an appropriate worker so the event loop keeps servicing other coroutines.
* An awaited operation must be async down its chain. An async operation left unawaited does not run to completion.

**Explainability Rules**

6. **No em dashes.** Use periods, commas, or parentheses instead.
7. **Mechanical, observable language.** Describe what happens, not how it feels.
8. **No selling, justifying, or comparing.** Describe the execution behavior, not why one style is better.
9. **Bridge async-specific terms with generic vocabulary.** When a term is runtime or framework specific (coroutine, event loop, yield control, offload to worker), pair it once with a plain-language equivalent. Fold into prose. No separate glossary section.

| Don't                                       | Do                                                                                  |
| ------------------------------------------- | ----------------------------------------------------------------------------------- |
| "makes the app feel snappier"               | "the event loop services other coroutines during the I/O wait"                      |
| "the best way to run these together"        | "these operations have no data dependency, so they run concurrently"                |
| "blocks and causes lag"                     | "runs on the event-loop thread and stops other coroutines from progressing"         |
| "we fire everything off at once and it just works" | "independent operations are scheduled with `gather()`. They run concurrently." |

| Don't                    | Do                                                                             |
| ------------------------ | ----------------------------------------------------------------------------- |
| "the coroutine yields"   | "the coroutine yields (the function pauses and lets other work run)"           |
| "offload it to a worker" | "offload it to a worker (run the blocking call on a separate thread or process)" |

---

Want me to save this as a `.md` file you can drop alongside your other skill definitions?