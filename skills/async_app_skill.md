# Agent Guidelines for Ensuring Asynchronous Implementation

**Name:** `ensure async implementation`

**Description:**

generates guidelines for making an application, or a feature/service inside it, run asynchronously. Determines which operations are declared **async** and **awaited**, which independent I/O-bound operations overlap their waiting time through concurrent execution, which data-dependent operations stay sequential, and which blocking or synchronous operations are moved to a worker so they do not block the event loop. When an operation is offloaded, selects the worker type (thread or process) from its blocking behavior: a thread when the operation waits on I/O, a process when it holds the interpreter lock doing CPU work. Applies the same data-dependency analysis to offloaded operations as to on-loop operations, so independent offloaded work is dispatched together and its results gathered, and data-dependent offloaded work still runs in order. Analysis runs across the full call chain, from the high-level entry layer down to the I/O operations. Covers async/await structuring, concurrency (also called non-blocking or event-loop execution), and offloading of blocking work.

**Trigger:**

when user asks how to make an application, feature, or service run asynchronously, or asks which operations to mark async/await, which to run concurrently, which to move off the event loop, or whether a blocking operation belongs on a thread or a process.

**Plan agent:**

Input the application or feature flow: the call chain, the operations at each layer, and their I/O touchpoints. Trace the flow from the high-level layer down to the I/O operations. At each layer, classify operations by data dependency. Mark the async boundaries (what is awaited, what runs concurrently). Flag synchronous operations that block the event loop for offloading, and for each one select the worker type (thread or process) from whether it waits on I/O or runs CPU work. Then apply the data-dependency test to the offloaded operations too, to decide which are dispatched together and which stay in order. Placement and ordering are two separate decisions for every operation.

**Goal:**

a layered map of the async structure. Each operation group is marked on two separate axes. Placement (on the event loop, offloaded to a thread, or offloaded to a process) is set by blocking behavior. Ordering (sequential await or concurrent) is set by data dependency. The two are decided independently and combined, so an operation is, for example, offloaded to a process and concurrent, or offloaded to a thread and sequential. Together the map preserves required ordering while overlapping the waiting time of independent I/O operations and running independent CPU-bound operations in parallel, from the entry point down to the lowest I/O call.

**Output per layer / operation group:**

* **Layer or Operation Group Name**
* **Operations and I/O Touchpoints** (the calls in the group and where each waits on I/O)
* **Data Dependency** (data-dependent, independent, or mixed. State which operation needs which result.)
* **Placement** (on the event loop as a coroutine / offloaded to a thread / offloaded to a process. Set by blocking behavior.)
* **Ordering** (sequential await / concurrent via `create_task` or `gather`. Set by data dependency, and set independently of placement: an offloaded operation is still either awaited in order or dispatched with its siblings and gathered.)
* **Shared-State Handling** (only when concurrent. State the model used, one-object or partial-results-and-merge, and the writes each concurrent operation performs.)
* **Blocking Check** (whether any operation in the group is synchronous and can block the event loop, and if so, whether its time is spent waiting on I/O or running CPU work.)
* **Worker Handling** (only when offloaded. State the worker type and the blocking behavior that selected it. For a thread: the library-level timeout that bounds the call, and the note that cancelling the awaiting task does not stop the thread. For a process: what crosses the process boundary, whether those values are serializable, their size, and the start method.)

**Workflow:** Map flow → Classify dependencies → Set placement (event loop, thread, or process) from blocking behavior → Set ordering (sequential or concurrent) from data dependency, on-loop and offloaded work alike → Review.

**Rules:**

*Structuring and concurrency*

* Support async execution across the whole call chain, from the high-level layer down to the I/O operations.
* Start at the high-level layer. Identify what must be awaited and which independent operations can run concurrently before moving down.
* At each layer, identify data dependencies before deciding execution mode.
* Data-dependent operations that need each other's results stay sequential. Use `async`/`await` so the coroutine yields control (the function pauses and lets other work run) during the I/O wait. Do not use `asyncio.create_task()` or `asyncio.gather()` for them, because they cannot make progress independently. Pattern: `A → await A → B → await B → C`.
* Independent operations with no data dependency are candidates for concurrency. Schedule and await them with `asyncio.create_task()` or `asyncio.gather()`. Pattern: `gather(A, B, C)`.
* Operations that work on different parts of shared state and progress independently can run concurrently, but their writes to shared state must be managed. Use a one-object model or a partial-results-and-merge model. Do not allow unsafe concurrent mutations or race conditions.
* Do not make every operation concurrent. Preserve required sequential dependencies. Overlap only independent work: the waiting time of independent I/O-bound operations, and the run time of independent CPU-bound operations placed on a process pool.
* Data dependency governs ordering for every operation, on-loop and offloaded alike. Deciding to offload an operation to a thread or a process does not answer whether it runs in order or overlaps with its siblings. That is a separate decision made from the same dependency test.
* An awaited operation must be async down its chain. An async operation left unawaited does not run to completion.

*Identifying blocking work*

* A synchronous operation is acceptable when it is intentional or unavoidable (synchronous third-party library, CPU-intensive processing, blocking SDK or API, legacy synchronous code, or a deliberately synchronous step).
* The test for a synchronous operation is whether it blocks the event loop. If it can take significant time or perform blocking I/O, do not run it directly in the event-loop thread.
* Trivial CPU work that finishes quickly runs inline in the coroutine. The cost of moving it to a worker (pool startup, data transfer) is not paid for short work.
* When an async-native version of the operation exists (an async HTTP client in place of a synchronous one, an async database driver in place of a synchronous one), use it instead of offloading. It carries less per-call overhead than a worker.

*Selecting the worker type*

* Offload to a thread when the operation spends its wait inside a system call (socket, disk, database wire protocol). During that wait CPython releases the global interpreter lock (the lock that allows only one thread to run Python code at a time), so the waiting thread and the event loop make progress at the same time.
* Offload to a process when the operation spends its time running Python-level CPU work. That work holds the interpreter lock, so a thread cannot run it at the same time as the event loop. A separate process has its own interpreter and runs in true parallel.
* Before selecting a process, check whether the heavy section runs inside a C extension that releases the interpreter lock while it runs (for example array or dataframe libraries). If it does, a thread already runs it in parallel and a process is not required.

*Ordering offloaded work*

* After placement is set, apply the data-dependency test again to decide ordering. Selecting a thread or a process answers where the operation runs, not whether it runs in order.
* Offloaded operations that depend on each other's results are awaited in order: await the first future before submitting the next. Placement on a worker does not remove the ordering requirement, and submitting a dependent operation before its input is ready produces a wrong result or an error.
* Offloaded operations that are independent are submitted to the pool together and their futures are gathered, so they run at the same time. Awaiting them one after another instead runs them in sequence and gives up the pool's parallelism.
* Independent operations can be gathered together regardless of placement. A single `gather()` can hold a coroutine, a threaded call, and a process call at once, because independence, not placement, is what allows them to overlap. Pattern: `gather(async_io(), asyncio.to_thread(blocking_io), loop.run_in_executor(process_pool, cpu_work))`.
* Concurrent dispatch turns into real overlap only when placement matches the work. Gathering independent thread calls overlaps their I/O waits. Gathering independent process calls runs their CPU work in parallel up to the pool size. Gathering CPU work onto threads does not run it in parallel, because the operations hold the interpreter lock and take it in turn, so CPU work that needs to overlap goes on a process pool.

*Applying a thread*

* Offload to a thread with `asyncio.to_thread(fn, *args, **kwargs)`, which copies the current context variables (request-scoped values) into the thread, or with `loop.run_in_executor(executor, fn, *args)`, which takes no keyword arguments (wrap the call with `functools.partial`).
* Do not send load-bearing work through the default executor (the built-in worker pool). It is shared across the whole process, including the runtime's own name resolution, and its size is capped at `min(32, cpu_count + 4)`. Create a dedicated `ThreadPoolExecutor` and size it to the downstream limit it feeds (for example the database connection pool size).
* Cancelling the awaiting task does not stop the running thread. Python cannot force a thread to stop. Bound every offloaded call with a timeout at the library level (socket timeout, request timeout). A blocking call with no timeout holds its thread until it returns on its own, and a hung call holds it indefinitely.
* The offloaded function runs off the event-loop thread. Objects owned by the event loop are not safe to touch from it. Return results as the awaited value, or signal the loop with `loop.call_soon_threadsafe(...)` or `asyncio.run_coroutine_threadsafe(...)`. Shared mutable state the function reads or writes needs a lock.

*Applying a process*

* Offload to a process with `loop.run_in_executor(process_pool, fn, *args)` using a `concurrent.futures.ProcessPoolExecutor` created once and reused. Starting a process is expensive and is not repeated per call.
* Everything that crosses the process boundary is serialized (converted to bytes for transfer, called pickling), sent, and rebuilt on the other side. The target function must be importable at module level (no lambdas, no functions defined inside other functions). Its arguments and return values must be serializable.
* Large arguments or return values pay the serialization cost in both directions and can cost more than the computation saves. For large payloads, pass a file path or a handle to shared memory rather than the data itself.
* Set the process start method explicitly to `spawn` or `forkserver` rather than relying on the platform default. An async process already runs multiple threads (the event loop and the thread pool). `fork` copies the parent as-is, so a lock held by another thread at the moment of fork is copied in a held state and the child can deadlock. `spawn` re-imports the module in each worker, which requires an `if __name__ == "__main__":` guard and re-runs any top-level code in every worker.
* Load per-worker resources once with `ProcessPoolExecutor(initializer=..., initargs=...)` rather than sending them with every call.
* Size the pool to the CPU count and leave headroom for the event-loop process and the operating system. Each worker is a separate interpreter with its own copy of imported modules, so N workers use about N times the base memory.
* A worker that crashes (segmentation fault, out-of-memory kill) raises `BrokenProcessPool` and fails every pending call in the pool. A task already running in a worker is not stopped by cancelling the awaiting coroutine.

*Both worker types*

* Bound the number of concurrent offloads with an `asyncio.Semaphore`. Scheduling more calls than the pool can serve queues them with no visible signal, and latency rises with no error raised.
* Own the executor lifecycle. Create it explicitly and shut it down with `shutdown(wait=True)` or a context manager.
* An exception raised inside a thread or a process propagates and re-raises when its future is awaited. From a process, an exception that is not serializable comes back as a degraded, less specific error.

**Explainability Rules**

6. **No em dashes.** Use periods, commas, or parentheses instead.
7. **Mechanical, observable language.** Describe what happens, not how it feels.
8. **No selling, justifying, or comparing.** Describe the execution behavior, not why one style is better. Worker selection is stated as a condition on behavior (waits on I/O, or holds the interpreter lock), not as a preference.
9. **Bridge async-specific terms with generic vocabulary.** When a term is runtime or framework specific (coroutine, event loop, yield control, offload to worker, interpreter lock, pickling, executor), pair it once with a plain-language equivalent. Fold into prose. No separate glossary section.

| Don't                                       | Do                                                                                  |
| ------------------------------------------- | ----------------------------------------------------------------------------------- |
| "makes the app feel snappier"               | "the event loop services other coroutines during the I/O wait"                      |
| "the best way to run these together"        | "these operations have no data dependency, so they run concurrently"                |
| "blocks and causes lag"                     | "runs on the event-loop thread and stops other coroutines from progressing"         |
| "we fire everything off at once and it just works" | "independent operations are scheduled with `gather()`. They run concurrently." |
| "threads are better for this"               | "the wait is spent in a system call, so the thread and the event loop overlap"       |
| "processes are faster here"                 | "the work holds the interpreter lock, so a separate process runs it in parallel"     |
| "these are offloaded, so ordering does not apply" | "placement and ordering are separate. These are offloaded to a process and, being independent, dispatched together and gathered" |

| Don't                    | Do                                                                             |
| ------------------------ | ----------------------------------------------------------------------------- |
| "the coroutine yields"   | "the coroutine yields (the function pauses and lets other work run)"           |
| "offload it to a worker" | "offload it to a worker (run the blocking call on a separate thread or process)" |
| "the GIL blocks it"      | "the interpreter lock (which lets only one thread run Python code at a time) blocks it" |
| "pickle the arguments"   | "serialize the arguments (convert them to bytes for transfer, called pickling)" |