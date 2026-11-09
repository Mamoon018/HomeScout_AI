"""R3's run lifecycle over HTTP (R3-C3, R3-C6, R3-C7), around the two R3 run tables.

- Start: read R2's finished output -> create the run -> start a background task -> 202.
- Retry: load -> pre-check -> claim the run (one conditional update) -> claim its failed or
  degraded step rows -> start the resumed task -> 202.
- Status: a live task of this user's answers `running` (with its checkpointed step) with no read;
  otherwise the row.
- The task: build a fresh R3 instance (its own gateway, R3-C2) and run its one unchanged entry
  method. At STEP 3's barrier a callback saves the checkpoint, unless the breaker was open (then
  STEP 3 is degraded: no checkpoint, kept only as a `degraded` step row). A retry passes
  `resume_after = completed_step`, so a saved STEP 3 is skipped. Any failure is saved on the row
  with its stage and `retryable`. Every write is fenced on this execution's `attempts`.
"""

import asyncio
import functools
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.core.logging import DEEP_SEARCH_LOGGER_NAME, run_id_var
from src.exceptions.deep_search import (
    R3_STAGE_ERRORS,
    MetricResolutionProviderError,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    RunSupersededError,
    StateVersionMismatchError,
)
from src.exceptions.mcp import McpConnectionError
from src.services.deep_search.feature_schemas.schemas import (
    R3RunRecord,
    R3RunView,
    R3StepId,
    SpecificMetricResolutionState,
)
from src.services.deep_search.r2_run_store import R2RunStore
from src.services.deep_search.r3_run_store import (
    R3_STATE_SCHEMA_VERSION,
    R3RunStore,
    dump_resolution_entries,
    state_chars,
)
from src.services.deep_search.specific_metric_resolution import SpecificMetricResolution

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# A run can be retried once. Reclaiming a crashed (stale) run counts as that retry.
MAX_RETRY_ATTEMPTS = 1

# A `running` run with no write for this long crashed and can be reclaimed (R3-C6). STEP 4 writes
# nothing for minutes, so this stays well above the longest STEP 4.
DEFAULT_STALE_AFTER_SECONDS = 1800.0

# How long shutdown waits for cancelled tasks to close their gateway and save themselves as failed.
# Longer than R2's 5 s: the method's `finally` closes two MCP sessions before the failed write.
R3_SHUTDOWN_TIMEOUT_SECONDS = 10.0

# The one checkpoint (R3-C3), and R3's step rows in run order.
CHECKPOINT_STEP = "discovery_batch"
_STEP_ORDER: tuple[R3StepId, ...] = ("discovery_batch", "pipelines")

# Errors raised before STEP 3 starts (gateway open, capability check, catalog): no step row.
_SETUP_ERRORS: tuple[type[Exception], ...] = (McpConnectionError, *R3_STAGE_ERRORS)

# The HTTP statuses that mean the provider refused our key (R3-C7 Iteration 1).
_REFUSED_KEY_STATUSES = frozenset({401, 403})
# McpConnectionError -> session start error (possibly inside an exception group) -> HTTP error.
# The limit only stops a cycle or an unexpectedly deep nesting.
_CAUSE_DEPTH_LIMIT = 8

_UNEXPECTED = "unexpected"
_CANCELLED = "cancelled"


def is_config_error(exc: BaseException) -> int | None:
    """The refused-key HTTP status (401 / 403) behind a gateway connection error, or None.

    Follows `__cause__` and the members of exception groups (the MCP session start runs in a task
    group, so its error can arrive grouped), at most `_CAUSE_DEPTH_LIMIT` levels deep.
    """
    pending: list[tuple[BaseException, int]] = [(exc, 0)]
    while pending:
        link, depth = pending.pop()
        status = getattr(link, "status_code", None)
        if status is None:
            status = getattr(getattr(link, "response", None), "status_code", None)
        if isinstance(status, int) and status in _REFUSED_KEY_STATUSES:
            return status
        if depth >= _CAUSE_DEPTH_LIMIT:
            continue
        if link.__cause__ is not None:
            pending.append((link.__cause__, depth + 1))
        if isinstance(link, BaseExceptionGroup):
            pending.extend((member, depth + 1) for member in link.exceptions)
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Execution:
    """One execution of a run: its identity, the `attempts` every write is fenced on, and the step
    rows this execution claimed at retry (they move from `started` at their write point)."""

    run_id: str
    user_id: str
    attempts: int
    claimed_steps: frozenset[R3StepId]
    path: str  # "start" or "retry"


@dataclass
class _Progress:
    """Where one execution is: the step a failure is recorded on, and whether STEP 3 degraded."""

    in_flight: R3StepId | None
    step3_degraded: bool = False


@dataclass
class _LiveRun:
    """One live task in this process: kept referenced until it ends, and read by status.

    `completed_step` is set only after the checkpoint write matched, so the memory reply never
    shows a step the row doesn't have.
    """

    task: asyncio.Task
    user_id: str
    completed_step: str | None = field(default=None)


class R3RunCoordinator:
    """Ties R3's entry method to the run tables: one background task per live execution."""

    def __init__(
        self,
        store: R3RunStore,
        r2_store: R2RunStore,
        *,
        service_factory: Callable[[], SpecificMetricResolution],
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self._store = store
        self._r2_store = r2_store
        # Builds a fresh R3 instance (and so a fresh gateway) per run (R3-C2): a shared gateway
        # would be closed by another run's `finally` in the middle of this run.
        self._service_factory = service_factory
        self._stale_after = timedelta(seconds=stale_after_seconds)
        # run_id -> live run. Exposed as `app.state.r3_tasks`.
        self._tasks: dict[str, _LiveRun] = {}

    @property
    def tasks(self) -> dict[str, _LiveRun]:
        """The live task dict (the same object the app keeps as `app.state.r3_tasks`)."""
        return self._tasks

    # ---- entry points ------------------------------------------------------------------------

    async def start_run(self, user_id: str, r2_run_id: str) -> R3RunView:
        """Read R2's finished output, create the run, start it in the background."""
        try:
            handoff = await self._r2_store.get_finished_output(r2_run_id, user_id)
        except StateVersionMismatchError as exc:
            self._log(
                logging.INFO,
                "r3_run.rejected",
                "-",
                user_id,
                reason="r2_version_mismatch",
                r2_run_id=r2_run_id,
                found_version=exc.found,
            )
            raise RunNotFoundError(r2_run_id) from exc
        if handoff is None:
            self._log(
                logging.INFO, "r3_run.rejected", "-", user_id, reason="r2_not_found", r2_run_id=r2_run_id
            )
            raise RunNotFoundError(r2_run_id)

        run_id = str(uuid4())
        token = run_id_var.set(run_id)
        try:
            state = SpecificMetricResolutionState(
                category_metric_plans=list(handoff.category_metric_plans),
                discovered_places=handoff.discovered_places,
                predefined_records=handoff.predefined_records,
            )
            await self._store.create_run(run_id, user_id, r2_run_id, state)
            self._log(
                logging.INFO,
                "r3_run.created",
                run_id,
                user_id,
                r2_run_id=r2_run_id,
                eligible_categories=sum(
                    1 for plan in state.category_metric_plans if plan.specific_metrics
                ),
                place_count=sum(len(places) for places in state.discovered_places.values()),
                schema_version=R3_STATE_SCHEMA_VERSION,
            )
            execution = _Execution(run_id, user_id, 0, frozenset(), path="start")
            self._schedule(execution, state, resume_after=None)
            return R3RunView(run_id=run_id, status="running")
        finally:
            run_id_var.reset(token)

    async def retry_run(self, user_id: str, run_id: str) -> R3RunView:
        """Claim a failed or crashed run once, then resume it after its last checkpoint."""
        token = run_id_var.set(run_id)
        try:
            record = await self._load_for_action(user_id, run_id)
            self._precheck_retry(record)
            reclaimed = record.status == "running"
            if not await self._store.claim_retry(
                run_id,
                user_id,
                expected_attempts=record.attempts,
                stale_before=_now() - self._stale_after,
            ):
                raise self._conflict(
                    record,
                    reason="cas_lost",
                    message="Another retry of this run already started",
                    status="running",
                )
            attempts = record.attempts + 1
            claimed_steps = await self._claim_resume_steps(record, attempts)
            self._log(
                logging.INFO,
                "r3_run.retry_started",
                run_id,
                user_id,
                attempts=attempts,
                resume_after=record.completed_step,
                claimed_steps=sorted(claimed_steps),
                reclaimed_stale=reclaimed,
            )
            execution = _Execution(run_id, user_id, attempts, claimed_steps, path="retry")
            self._schedule(execution, record.state, resume_after=record.completed_step)
            return R3RunView(run_id=run_id, status="running", completed_step=record.completed_step)
        finally:
            run_id_var.reset(token)

    async def get_run(self, user_id: str, run_id: str) -> R3RunView:
        """Read-only status: the live task dict first (no I/O), then the row."""
        token = run_id_var.set(run_id)
        try:
            live = self._tasks.get(run_id)
            if live is not None:
                if live.user_id == user_id:
                    return R3RunView(
                        run_id=run_id, status="running", completed_step=live.completed_step
                    )
                # Same answer the row read would give: another user's run does not exist here.
                self._log(logging.INFO, "r3_run.rejected", run_id, user_id, reason="not_found")
                raise RunNotFoundError(run_id)
            try:
                record = await self._store.load_run(run_id, user_id)
            except StateVersionMismatchError as exc:
                self._log(
                    logging.WARNING,
                    "r3_run.status_degraded",
                    run_id,
                    user_id,
                    reason="version_mismatch",
                    found_version=exc.found,
                    expected_version=exc.expected,
                )
                return R3RunView(run_id=run_id, status="failed", retryable=False)
            if record is None:
                self._log(logging.INFO, "r3_run.rejected", run_id, user_id, reason="not_found")
                raise RunNotFoundError(run_id)
            self._log_loaded(record)
            return self._view(record)
        finally:
            run_id_var.reset(token)

    async def shutdown(self, timeout_seconds: float = R3_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Cancel every live task and wait for each to close its gateway and save itself."""
        tasks = [live.task for live in self._tasks.values()]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        _, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
        if pending:
            logger.warning(
                json.dumps(
                    {
                        "event": "r3_run.shutdown_timeout",
                        "timestamp": _now().isoformat(),
                        "pending_run_ids": [
                            run_id for run_id, live in self._tasks.items() if live.task in pending
                        ],
                        "timeout_seconds": timeout_seconds,
                    }
                )
            )

    # ---- background execution ----------------------------------------------------------------

    def _schedule(
        self,
        execution: _Execution,
        state: SpecificMetricResolutionState,
        *,
        resume_after: str | None,
    ) -> None:
        """Start the execution as a task. It copies `run_id_var`, so its log lines carry the run."""
        task = asyncio.create_task(
            self._execute(execution, state, resume_after), name=f"r3_run:{execution.run_id}"
        )
        self._tasks[execution.run_id] = _LiveRun(task, execution.user_id, resume_after)
        task.add_done_callback(functools.partial(self._on_task_done, execution))

    def _on_task_done(self, execution: _Execution, task: asyncio.Task) -> None:
        """Remove the finished task (only if it is still the current one for the run)."""
        current = self._tasks.get(execution.run_id)
        if current is not None and current.task is task:
            del self._tasks[execution.run_id]
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            # `_execute` saves every failure itself; reaching here means the save path broke.
            self._log(
                logging.ERROR,
                "r3_run.task_crashed",
                execution.run_id,
                execution.user_id,
                error_class=type(exc).__name__,
                detail=repr(exc),
            )

    async def _execute(
        self,
        execution: _Execution,
        state: SpecificMetricResolutionState,
        resume_after: str | None,
    ) -> None:
        """Run R3 once from the first unfinished step, then one terminal write (none if superseded)."""
        service = self._service_factory()
        # Before the STEP 3 callback a failure belongs to STEP 3; on a resume STEP 3 is skipped.
        progress = _Progress(in_flight="discovery_batch" if resume_after is None else "pipelines")
        try:
            await service.run_specific_metric_resolution(
                state,
                resume_after=resume_after,  # type: ignore[arg-type]
                on_step_completed=self._step_callback(execution, progress),
            )
            # `pipelines` stays in flight until the finish write lands: a database error there
            # records it as failed, so the retry claims it and completes it at its finish write.
            await self._save_finished(execution, state, progress)
        except RunSupersededError:
            # A newer execution owns the row; this one already logged it and writes nothing more.
            return
        except asyncio.CancelledError as exc:
            await self._save_failed(execution, exc, progress, state)
            raise
        except Exception as exc:
            await self._save_failed(execution, exc, progress, state)
        finally:
            # The gateway is already closed by the method's own `finally` (idempotent close); the
            # shared caller is not owned by a per-run instance, so it stays open.
            await service.aclose()

    def _step_callback(self, execution: _Execution, progress: _Progress):
        """The R3-C3 hook: save a clean STEP 3 as the checkpoint; mark a breaker-open one degraded."""

        async def on_step_completed(
            step: str, state: SpecificMetricResolutionState, breaker_open: bool
        ) -> None:
            if breaker_open:
                # The remaining verdicts came from an outage, not from the web: never a checkpoint,
                # so a retry reruns STEP 3. The row is written with the run's final write.
                progress.step3_degraded = True
                progress.in_flight = "pipelines"
                self._log(
                    logging.WARNING,
                    "r3_run.step3_degraded",
                    execution.run_id,
                    execution.user_id,
                    attempts=execution.attempts,
                    work_items=len(state.website_search_results),
                )
                return
            await self._save_checkpoint(execution, state)
            progress.in_flight = "pipelines"

        return on_step_completed

    async def _save_checkpoint(
        self, execution: _Execution, state: SpecificMetricResolutionState
    ) -> None:
        """Save the state after a clean STEP 3, then its step row. Raises to stop the run."""
        saved = await self._store.save_checkpoint(
            execution.run_id, execution.user_id, attempts=execution.attempts, state=state
        )
        if not saved:
            self._superseded(execution, "save_checkpoint")
            raise RunSupersededError(execution.run_id, "save_checkpoint")
        live = self._tasks.get(execution.run_id)
        if live is not None and live.task is asyncio.current_task():
            live.completed_step = CHECKPOINT_STEP
        origins: dict[str, int] = {"google": 0, "discovered": 0, "none": 0}
        for verdict in state.website_search_results.values():
            origins[verdict.website_origin] += 1
        self._log(
            logging.INFO,
            "r3_run.checkpoint_saved",
            execution.run_id,
            execution.user_id,
            completed_step=CHECKPOINT_STEP,
            attempts=execution.attempts,
            verdict_counts=origins,
            state_chars=state_chars(state),
        )
        await self._record_step(execution, "discovery_batch", state, stop_on_conflict=True)

    async def _save_finished(
        self, execution: _Execution, state: SpecificMetricResolutionState, progress: _Progress
    ) -> None:
        """The finish write (state + output + `finished`), then the step rows."""
        saved = await self._store.save_finished(
            execution.run_id,
            execution.user_id,
            attempts=execution.attempts,
            state=state,
            output=state.resolution_results,
        )
        if not saved:
            self._superseded(execution, "save_finished")
            return
        outcomes: dict[str, int] = {}
        for record in state.resolution_results.values():
            outcomes[record.outcome] = outcomes.get(record.outcome, 0) + 1
        self._log(
            logging.INFO,
            "r3_run.finished",
            execution.run_id,
            execution.user_id,
            attempts=execution.attempts,
            path=execution.path,
            outcome_counts=outcomes,
            state_chars=state_chars(state),
        )
        # Recorded only now: a completed row never changes, and a STEP 5 raise after STEP 4 would
        # otherwise make the retry rerun STEP 4 against its own completed row.
        await self._record_step(execution, "pipelines", state, stop_on_conflict=False)
        if progress.step3_degraded:
            await self._record_degraded(execution, state)

    async def _record_step(
        self,
        execution: _Execution,
        step_id: R3StepId,
        state: SpecificMetricResolutionState,
        *,
        stop_on_conflict: bool,
    ) -> None:
        """Write a completed step row after a matched run write. A conflict mid-run stops it."""
        claimed = step_id in execution.claimed_steps
        try:
            if claimed:
                ok = await self._store.complete_claimed_step(execution.run_id, step_id, state)
            else:
                ok = await self._store.insert_step(execution.run_id, step_id, state)
        except RunStoreError as exc:
            # The run row is already right and decides resume; the step table is a record only.
            self._log(
                logging.WARNING,
                "r3_run.step_record_failed",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                operation="complete_claimed_step" if claimed else "insert_step",
                store_error=str(exc),
            )
            return
        path = "claimed" if claimed else "insert"
        if not ok:
            self._log(
                logging.INFO,
                "r3_run.step_conflict",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                path=path,
            )
            if stop_on_conflict:
                raise RunSupersededError(execution.run_id, "step_conflict")
            return
        self._log(
            logging.INFO,
            "r3_step.saved",
            execution.run_id,
            execution.user_id,
            step_id=step_id,
            status="completed",
            path=path,
        )

    async def _record_degraded(
        self, execution: _Execution, state: SpecificMetricResolutionState
    ) -> None:
        """Keep what a breaker-open STEP 3 found as a `degraded` row (after a matched run write)."""
        claimed = "discovery_batch" in execution.claimed_steps
        try:
            ok = await self._store.save_step_degraded(
                execution.run_id, "discovery_batch", state, claimed=claimed
            )
        except RunStoreError as exc:
            self._log(
                logging.WARNING,
                "r3_run.step_record_failed",
                execution.run_id,
                execution.user_id,
                step_id="discovery_batch",
                operation="save_step_degraded",
                store_error=str(exc),
            )
            return
        path = "claimed" if claimed else "insert"
        if not ok:
            self._log(
                logging.INFO,
                "r3_run.step_conflict",
                execution.run_id,
                execution.user_id,
                step_id="discovery_batch",
                path=path,
            )
            return
        self._log(
            logging.INFO,
            "r3_step.saved",
            execution.run_id,
            execution.user_id,
            step_id="discovery_batch",
            status="degraded",
            path=path,
        )

    async def _save_failed(
        self,
        execution: _Execution,
        exc: BaseException,
        progress: _Progress,
        state: SpecificMetricResolutionState,
    ) -> None:
        """Save the run as failed (state untouched), then its step rows; never raises.

        `state` is read only for a degraded STEP 3's step row; the run row's state is not written.
        """
        stage, retryable, refused_status = self._retryable_for(exc, execution.attempts)
        step_id = None if isinstance(exc, _SETUP_ERRORS) else progress.in_flight
        unexpected = stage == _UNEXPECTED
        error_type = type(exc).__name__
        message = repr(exc) if unexpected or not str(exc) else str(exc)
        if refused_status is not None:
            self._log(
                logging.ERROR,
                "r3_run.config_error",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                http_status=refused_status,
                error_class=error_type,
            )
        saved: bool | None
        try:
            saved = await self._store.save_failed(
                execution.run_id,
                execution.user_id,
                attempts=execution.attempts,
                stage=stage,
                message=message,
                retryable=retryable,
            )
        except RunStoreError as store_exc:
            # The database is down too. The row stays `running` and is reclaimable once stale.
            saved = None
            self._log(
                logging.ERROR,
                "r3_run.failed_not_saved",
                execution.run_id,
                execution.user_id,
                stage=stage,
                store_error=str(store_exc),
            )
        if saved is False:
            self._superseded(execution, "save_failed")
        if saved:
            if step_id is not None:
                await self._record_failed_step(
                    execution, step_id, error_type=error_type, message=message, retryable=retryable
                )
            if progress.step3_degraded:
                await self._record_degraded(execution, state)
        fields = self._fields(
            "r3_run.failed",
            execution.run_id,
            execution.user_id,
            stage=stage,
            step_id=step_id,
            error_class=error_type,
            retryable=retryable,
            attempts=execution.attempts,
            saved=bool(saved),
            message=message,
        )
        if unexpected:
            logger.error(json.dumps(fields, default=str), exc_info=exc)
        else:
            logger.error(json.dumps(fields, default=str))

    async def _record_failed_step(
        self,
        execution: _Execution,
        step_id: R3StepId,
        *,
        error_type: str,
        message: str,
        retryable: bool,
    ) -> None:
        """Record the running step's failure (a new row, or `started → failed` when claimed)."""
        try:
            recorded = await self._store.save_step_failed(
                execution.run_id,
                step_id,
                error_type=error_type,
                message=message,
                retryable=retryable,
                claimed=step_id in execution.claimed_steps,
            )
        except RunStoreError as store_exc:
            self._log(
                logging.WARNING,
                "r3_run.step_record_failed",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                operation="save_step_failed",
                store_error=str(store_exc),
            )
            return
        if not recorded:
            self._log(
                logging.INFO,
                "r3_run.step_conflict",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                path="save_step_failed",
            )

    @staticmethod
    def _retryable_for(exc: BaseException, attempts: int) -> tuple[str, bool, int | None]:
        """The R3-C7 table: (stage, retryable, refused-key HTTP status or None)."""
        under_limit = attempts < MAX_RETRY_ATTEMPTS
        if isinstance(exc, asyncio.CancelledError):
            return _CANCELLED, under_limit, None
        if isinstance(exc, McpConnectionError):
            refused = is_config_error(exc)
            return exc.stage, refused is None and under_limit, refused
        if isinstance(exc, MetricResolutionProviderError):
            return exc.stage, under_limit, None
        if isinstance(exc, R3_STAGE_ERRORS):
            return exc.stage, False, None
        if isinstance(exc, RunStoreError):
            # A database error on the checkpoint or finish write: the work since the last save is
            # lost, the run is not, and a blip clears on retry (as R2's D-R2-3).
            return exc.stage, under_limit, None
        return _UNEXPECTED, False, None

    # ---- retry helpers -----------------------------------------------------------------------

    async def _load_for_action(self, user_id: str, run_id: str) -> R3RunRecord:
        """Load a run for retry. A version mismatch closes the run (not retryable) and conflicts."""
        try:
            record = await self._store.load_run(run_id, user_id)
        except StateVersionMismatchError as exc:
            await self._store.mark_version_mismatch(run_id, user_id)
            self._log(
                logging.INFO,
                "r3_run.rejected",
                run_id,
                user_id,
                reason="version_mismatch",
                found_version=exc.found,
                expected_version=exc.expected,
            )
            raise RunConflictError(
                "The run was saved by another version; start again",
                run_id=run_id,
                status="failed",
                retryable=False,
            ) from exc
        if record is None:
            self._log(logging.INFO, "r3_run.rejected", run_id, user_id, reason="not_found")
            raise RunNotFoundError(run_id)
        self._log_loaded(record)
        return record

    def _precheck_retry(self, record: R3RunRecord) -> None:
        """Fast reject before the claim (the claim itself is the guard)."""
        if record.status == "finished":
            raise self._conflict(
                record, reason="finished", message="The run has finished", status="finished"
            )
        if record.status == "failed":
            if not record.retryable or record.attempts >= MAX_RETRY_ATTEMPTS:
                raise self._conflict(
                    record,
                    reason="not_retryable",
                    message="The run cannot be retried",
                    status="failed",
                    retryable=False,
                )
            return
        # `running`: alive until stale; a stale run can be reclaimed once (that is the retry).
        if not self._is_stale(record):
            raise self._conflict(
                record, reason="still_running", message="The run is still running", status="running"
            )
        if record.attempts >= MAX_RETRY_ATTEMPTS:
            raise self._conflict(
                record,
                reason="not_retryable",
                message="The run was cut off and its retry is used; start again",
                status="running",
                retryable=False,
            )

    async def _claim_resume_steps(self, record: R3RunRecord, attempts: int) -> frozenset[R3StepId]:
        """Claim every `failed` or `degraded` step row from the resume step on."""
        start = 0 if record.completed_step is None else _STEP_ORDER.index("pipelines")
        claimed: set[R3StepId] = set()
        for step_id in _STEP_ORDER[start:]:
            step = record.steps.get(step_id)
            if step is None or step.status not in ("failed", "degraded"):
                # A crashed (reclaimed) run, or a step never reached: nothing to claim. The step
                # is inserted as a new row at its write point.
                continue
            if await self._store.claim_step(record.run_id, step_id):
                claimed.add(step_id)
                continue
            # The run claim won but its step row moved: the rows disagree. Close the run.
            await self._store.save_failed(
                record.run_id,
                record.user_id,
                attempts=attempts,
                stage="claim_step",
                message=f"The run's {step_id} step changed during the retry",
                retryable=False,
            )
            raise self._conflict(
                record,
                reason="step_conflict",
                message="The run's step record changed; start again",
                status="failed",
                retryable=False,
            )
        return frozenset(claimed)

    def _is_stale(self, record: R3RunRecord) -> bool:
        """True when the run is `running` and has not been written for longer than the limit."""
        if record.status != "running":
            return False
        try:
            updated_at = datetime.fromisoformat(record.updated_at)
        except ValueError as exc:
            raise RunStoreError(
                f"r3_runs updated_at is not an ISO timestamp: {record.updated_at!r}",
                operation="load_run",
            ) from exc
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return _now() - updated_at > self._stale_after

    # ---- views and logging -------------------------------------------------------------------

    @staticmethod
    def _view(record: R3RunRecord) -> R3RunView:
        """What the page shows for a stored run, by status."""
        if record.status == "running":
            return R3RunView(
                run_id=record.run_id, status="running", completed_step=record.completed_step
            )
        if record.status == "finished":
            results = (
                record.output if record.output is not None else record.state.resolution_results
            )
            return R3RunView(
                run_id=record.run_id,
                status="finished",
                completed_step=record.completed_step,
                result=dump_resolution_entries(results),
            )
        return R3RunView(
            run_id=record.run_id,
            status="failed",
            completed_step=record.completed_step,
            retryable=record.retryable,
        )

    def _conflict(
        self,
        record: R3RunRecord,
        *,
        reason: str,
        message: str,
        status: str,
        retryable: bool | None = None,
    ) -> RunConflictError:
        self._log(
            logging.INFO, "r3_run.rejected", record.run_id, record.user_id, reason=reason, status=status
        )
        return RunConflictError(message, run_id=record.run_id, status=status, retryable=retryable)

    def _superseded(self, execution: _Execution, operation: str) -> None:
        """A newer execution owns the row (lost fence): this one stops writing."""
        self._log(
            logging.INFO,
            "r3_run.superseded",
            execution.run_id,
            execution.user_id,
            operation=operation,
            attempts=execution.attempts,
        )

    def _log_loaded(self, record: R3RunRecord) -> None:
        self._log(
            logging.INFO,
            "r3_run.loaded",
            record.run_id,
            record.user_id,
            status=record.status,
            attempts=record.attempts,
            completed_step=record.completed_step,
            retryable=record.retryable,
            step_statuses={step_id: step.status for step_id, step in record.steps.items()},
        )

    @staticmethod
    def _fields(event: str, run_id: str, user_id: str, **fields: object) -> dict:
        return {
            "event": event,
            "timestamp": _now().isoformat(),
            "run_id": run_id,
            "user_id": user_id,
            **fields,
        }

    def _log(self, level: int, event: str, run_id: str, user_id: str, **fields: object) -> None:
        logger.log(level, json.dumps(self._fields(event, run_id, user_id, **fields), default=str))
