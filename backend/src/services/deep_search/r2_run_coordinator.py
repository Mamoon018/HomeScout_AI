"""R2's run lifecycle over HTTP (R2-C2, R2-C5, R2-C6), around the two R2 run tables.

- Start: read R1's finished plans -> create the run -> start a background task -> 202.
- Retry: load -> pre-check -> claim the run (one conditional update) -> claim its failed step
  -> start the resumed task -> 202.
- Status: a live task of this user's answers `running` with no read; otherwise the row.
- The task: run R2's three unchanged step methods from the first unfinished step, save a
  checkpoint after discovery, then the finish write. Any failure is saved on the row with its
  stage and `retryable`. Every write is fenced on this execution's `attempts`.
"""

import asyncio
import functools
import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from google.api_core import exceptions as google_exceptions

from src.clients.google_places import GooglePlacesAsyncClient
from src.clients.google_routes import GoogleRoutesAsyncClient
from src.clients.llm_provider import StructuredLLMCaller
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, run_id_var
from src.exceptions.deep_search import (
    R2_PROVIDER_ERRORS,
    R2_STAGE_ERRORS,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    StateVersionMismatchError,
)
from src.services.deep_search.amenity_search import AmenitySearch
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchOutput,
    AmenitySearchState,
    GeoPoint,
    R2RunRecord,
    R2RunView,
    R2StepId,
    R2StepName,
)
from src.services.deep_search.r1_run_store import R1RunStore
from src.services.deep_search.r2_run_store import R2_STATE_SCHEMA_VERSION, R2RunStore

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# A run can be retried once. Reclaiming a crashed (stale) run counts as that retry.
MAX_RETRY_ATTEMPTS = 1

# A `running` run with no write for this long crashed and can be reclaimed (R2-C5).
DEFAULT_STALE_AFTER_SECONDS = 600.0

# How long shutdown waits for cancelled tasks to save themselves as failed.
SHUTDOWN_TIMEOUT_SECONDS = 5.0

# Google's errors that mean our setup or request is wrong; a retry fails the same way.
_CONFIG_ERRORS: tuple[type[Exception], ...] = (
    google_exceptions.InvalidArgument,
    google_exceptions.FailedPrecondition,
    google_exceptions.PermissionDenied,
)
# R2 error -> client error -> Google error is three links; the limit only stops a cycle.
_CAUSE_DEPTH_LIMIT = 8

_UNEXPECTED = "unexpected"
_CANCELLED = "cancelled"


@dataclass(frozen=True)
class R2StepSpec:
    """One step of R2's plan: the existing method it calls and how it is persisted."""

    name: R2StepName
    call: Callable[[AmenitySearch, AmenitySearchState], Any]
    # Saved as a checkpoint (`completed_step`) right after it completes.
    checkpoint_after: bool
    # Has an `r2_run_steps` row (non-reproducible steps only).
    recorded: bool


# R2-C2: the order a one-call R2 run uses today. Discovery is costly, non-reproducible and
# followed by more paid calls, so it is checkpointed. Enrichment is followed only by in-memory
# work, so the finish write covers it. Attachment is pure.
R2_STEP_PLAN: tuple[R2StepSpec, ...] = (
    R2StepSpec("discovery", lambda search, state: search.run_place_discovery(state), True, True),
    R2StepSpec(
        "enrichment", lambda search, state: search.run_accessibility_enrichment(state), False, True
    ),
    R2StepSpec("attachment", lambda search, state: search.run_result_attachment(state), False, False),
)


def remaining_steps(completed_step: str | None) -> tuple[R2StepSpec, ...]:
    """The resume rule: no checkpoint -> every step; `discovery` -> enrichment onward."""
    if completed_step is None:
        return R2_STEP_PLAN
    names = [step.name for step in R2_STEP_PLAN]
    return R2_STEP_PLAN[names.index(completed_step) + 1 :]


def is_config_error(exc: BaseException) -> type[Exception] | None:
    """The Google config error behind an R2 provider error, following `__cause__`, or None."""
    link: BaseException | None = exc
    for _ in range(_CAUSE_DEPTH_LIMIT):
        if link is None:
            return None
        if isinstance(link, _CONFIG_ERRORS):
            return type(link)
        link = link.__cause__
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Execution:
    """One execution of a run: its identity and the `attempts` value every write is fenced on."""

    run_id: str
    user_id: str
    attempts: int
    claimed_step: R2StepId | None
    path: str  # "start" or "retry"


class R2RunCoordinator:
    """Ties R2's step methods to the run tables: one background task per live execution."""

    def __init__(
        self,
        store: R2RunStore,
        r1_store: R1RunStore,
        *,
        places_client: GooglePlacesAsyncClient,
        routes_client: GoogleRoutesAsyncClient,
        global_places_semaphore: asyncio.Semaphore | None,
        llm_caller: StructuredLLMCaller | None = None,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        max_places_per_category: int | None = None,
    ) -> None:
        self._store = store
        # Test-cost cap passed to every per-run AmenitySearch (None = no limit).
        self._max_places_per_category = max_places_per_category
        self._r1_store = r1_store
        self._places_client = places_client
        self._routes_client = routes_client
        self._global_places_semaphore = global_places_semaphore
        self._llm_caller = llm_caller
        self._stale_after = timedelta(seconds=stale_after_seconds)
        # run_id -> (task, user_id). Keeps each task referenced until it ends, and lets the status
        # read check ownership before any database read. Exposed as `app.state.r2_tasks`.
        self._tasks: dict[str, tuple[asyncio.Task, str]] = {}

    @property
    def tasks(self) -> dict[str, tuple[asyncio.Task, str]]:
        """The live task set (the same object the app keeps as `app.state.r2_tasks`)."""
        return self._tasks

    # ---- entry points ------------------------------------------------------------------------

    async def start_run(
        self, user_id: str, r1_run_id: str, origin: GeoPoint, radius_km: float
    ) -> R2RunView:
        """Read R1's finished plans, create the run, start it in the background."""
        try:
            plans = await self._r1_store.get_finished_output(r1_run_id, user_id)
        except StateVersionMismatchError as exc:
            self._log(
                logging.INFO,
                "r2_run.rejected",
                "-",
                user_id,
                reason="r1_version_mismatch",
                r1_run_id=r1_run_id,
                found_version=exc.found,
            )
            raise RunNotFoundError(r1_run_id) from exc
        if plans is None:
            self._log(
                logging.INFO, "r2_run.rejected", "-", user_id, reason="r1_not_found", r1_run_id=r1_run_id
            )
            raise RunNotFoundError(r1_run_id)

        run_id = str(uuid4())
        token = run_id_var.set(run_id)
        try:
            state = AmenitySearchState(
                origin=origin, radius_km=radius_km, category_metric_plans=list(plans)
            )
            await self._store.create_run(run_id, user_id, r1_run_id, state)
            self._log(
                logging.INFO,
                "r2_run.created",
                run_id,
                user_id,
                r1_run_id=r1_run_id,
                category_count=len(plans),
                radius_km=radius_km,
                schema_version=R2_STATE_SCHEMA_VERSION,
            )
            execution = _Execution(run_id, user_id, attempts=0, claimed_step=None, path="start")
            self._schedule(execution, state, resume_after=None)
            return R2RunView(run_id=run_id, status="running")
        finally:
            run_id_var.reset(token)

    async def retry_run(self, user_id: str, run_id: str) -> R2RunView:
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
            claimed_step = await self._claim_resume_step(record, attempts)
            self._log(
                logging.INFO,
                "r2_run.retry_started",
                run_id,
                user_id,
                attempts=attempts,
                resume_after=record.completed_step,
                claimed_step=claimed_step,
                reclaimed_stale=reclaimed,
            )
            execution = _Execution(run_id, user_id, attempts, claimed_step, path="retry")
            self._schedule(execution, record.state, resume_after=record.completed_step)
            return R2RunView(
                run_id=run_id, status="running", completed_step=record.completed_step
            )
        finally:
            run_id_var.reset(token)

    async def get_run(self, user_id: str, run_id: str) -> R2RunView:
        """Read-only status: the live task set first (no I/O), then the row."""
        token = run_id_var.set(run_id)
        try:
            entry = self._tasks.get(run_id)
            if entry is not None:
                if entry[1] == user_id:
                    return R2RunView(run_id=run_id, status="running")
                # Same answer the row read would give: another user's run does not exist here.
                self._log(logging.INFO, "r2_run.rejected", run_id, user_id, reason="not_found")
                raise RunNotFoundError(run_id)
            try:
                record = await self._store.load_run(run_id, user_id)
            except StateVersionMismatchError as exc:
                self._log(
                    logging.WARNING,
                    "r2_run.status_degraded",
                    run_id,
                    user_id,
                    reason="version_mismatch",
                    found_version=exc.found,
                    expected_version=exc.expected,
                )
                return R2RunView(run_id=run_id, status="failed", retryable=False)
            if record is None:
                self._log(logging.INFO, "r2_run.rejected", run_id, user_id, reason="not_found")
                raise RunNotFoundError(run_id)
            self._log_loaded(record)
            return self._view(record)
        finally:
            run_id_var.reset(token)

    async def shutdown(self, timeout_seconds: float = SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Cancel every live task and wait for each to save itself as failed."""
        tasks = [task for task, _ in self._tasks.values()]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        _, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
        if pending:
            logger.warning(
                json.dumps(
                    {
                        "event": "r2_run.shutdown_timeout",
                        "timestamp": _now().isoformat(),
                        "pending_run_ids": [
                            run_id for run_id, (task, _) in self._tasks.items() if task in pending
                        ],
                        "timeout_seconds": timeout_seconds,
                    }
                )
            )

    # ---- background execution ----------------------------------------------------------------

    def _schedule(
        self, execution: _Execution, state: AmenitySearchState, *, resume_after: str | None
    ) -> None:
        """Start the execution as a task. It copies `run_id_var`, so its log lines carry the run."""
        task = asyncio.create_task(
            self._execute(execution, state, resume_after), name=f"r2_run:{execution.run_id}"
        )
        self._tasks[execution.run_id] = (task, execution.user_id)
        task.add_done_callback(functools.partial(self._on_task_done, execution))

    def _on_task_done(self, execution: _Execution, task: asyncio.Task) -> None:
        """Remove the finished task (only if it is still the current one for the run)."""
        current = self._tasks.get(execution.run_id)
        if current is not None and current[0] is task:
            del self._tasks[execution.run_id]
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            # `_execute` saves every failure itself; reaching here means the save path broke.
            self._log(
                logging.ERROR,
                "r2_run.task_crashed",
                execution.run_id,
                execution.user_id,
                error_class=type(exc).__name__,
                detail=repr(exc),
            )

    async def _execute(
        self,
        execution: _Execution,
        state: AmenitySearchState,
        resume_after: str | None,
    ) -> None:
        """Run the remaining steps, checkpoint after discovery, then finish; or save the failure."""
        search = self._new_amenity_search()
        in_flight: R2StepId | None = None
        try:
            for step in remaining_steps(resume_after):
                # A failure is recorded against a non-reproducible step; attachment has no row.
                in_flight = step.name if step.recorded else None
                result = step.call(search, state)
                if inspect.isawaitable(result):
                    await result
                if step.checkpoint_after and not await self._save_checkpoint(
                    execution, state, step.name
                ):
                    return
            in_flight = None
            await self._save_finished(execution, state)
        except asyncio.CancelledError as exc:
            await self._save_failed(execution, exc, in_flight)
            raise
        except Exception as exc:
            await self._save_failed(execution, exc, in_flight)

    def _new_amenity_search(self) -> AmenitySearch:
        """A per-run R2 instance: its own run semaphore, the shared clients and global cap."""
        return AmenitySearch(
            self._places_client,
            self._routes_client,
            llm_caller=self._llm_caller,
            owns_caller=False,
            global_places_semaphore=self._global_places_semaphore,
            owns_clients=False,
            max_places_per_category=self._max_places_per_category,
        )

    async def _save_checkpoint(
        self, execution: _Execution, state: AmenitySearchState, step_name: str
    ) -> bool:
        """Save the state after discovery, then its step row. False: stop this execution."""
        saved = await self._store.save_checkpoint(
            execution.run_id,
            execution.user_id,
            attempts=execution.attempts,
            state=state,
            completed_step=step_name,
        )
        if not saved:
            self._superseded(execution, "save_checkpoint")
            return False
        self._log(
            logging.INFO,
            "r2_run.checkpoint_saved",
            execution.run_id,
            execution.user_id,
            completed_step=step_name,
            attempts=execution.attempts,
            place_counts={
                str(category_id): len(places)
                for category_id, places in state.discovered_places.items()
            },
        )
        return await self._record_step(execution, "discovery", state.discovered_places)

    async def _save_finished(self, execution: _Execution, state: AmenitySearchState) -> None:
        """The finish write (state + output + `finished`), then the enrichment step row."""
        output = AmenitySearchOutput(
            category_metric_plans=list(state.category_metric_plans),
            discovered_places=state.discovered_places,
            predefined_records=state.predefined_records,
        )
        saved = await self._store.save_finished(
            execution.run_id,
            execution.user_id,
            attempts=execution.attempts,
            state=state,
            output=output,
        )
        if not saved:
            self._superseded(execution, "save_finished")
            return
        self._log(
            logging.INFO,
            "r2_run.finished",
            execution.run_id,
            execution.user_id,
            attempts=execution.attempts,
            path=execution.path,
            record_counts={
                str(category_id): len(records)
                for category_id, records in state.predefined_records.items()
            },
        )
        # Recorded only now: a completed row never changes, and a failure in attachment would
        # otherwise make the retry rerun enrichment against its own completed row.
        await self._record_step(execution, "enrichment", state.enrichment)

    async def _record_step(self, execution: _Execution, step_id: R2StepId, result: Any) -> bool:
        """Write the step row after a matched run write. False on a conflict (stop)."""
        claimed = step_id == execution.claimed_step
        try:
            if claimed:
                ok = await self._store.complete_claimed_step(execution.run_id, step_id, result)
            else:
                ok = await self._store.insert_step(execution.run_id, step_id, result)
        except RunStoreError as exc:
            # The run row is already right and decides resume; the step table is a record only.
            self._log(
                logging.WARNING,
                "r2_run.step_record_failed",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                operation="complete_claimed_step" if claimed else "insert_step",
                store_error=str(exc),
            )
            return True
        path = "claimed" if claimed else "insert"
        if not ok:
            self._log(
                logging.INFO,
                "r2_run.step_conflict",
                execution.run_id,
                execution.user_id,
                step_id=step_id,
                path=path,
            )
            return False
        self._log(
            logging.INFO, "r2_step.saved", execution.run_id, execution.user_id, step_id=step_id, path=path
        )
        return True

    async def _save_failed(
        self, execution: _Execution, exc: BaseException, in_flight: R2StepId | None
    ) -> None:
        """Save the run as failed (state untouched), then the failed step row; never raises."""
        stage, retryable, config_cls = self._retryable_for(exc, execution.attempts)
        unexpected = stage == _UNEXPECTED
        error_type = type(exc).__name__
        message = repr(exc) if unexpected or not str(exc) else str(exc)
        if config_cls is not None:
            self._log(
                logging.ERROR,
                "r2_run.config_error",
                execution.run_id,
                execution.user_id,
                step_id=in_flight,
                google_error_class=config_cls.__name__,
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
                "r2_run.failed_not_saved",
                execution.run_id,
                execution.user_id,
                stage=stage,
                store_error=str(store_exc),
            )
        if saved is False:
            self._superseded(execution, "save_failed")
        if saved and in_flight is not None:
            try:
                recorded = await self._store.save_step_failed(
                    execution.run_id,
                    in_flight,
                    error_type=error_type,
                    message=message,
                    retryable=retryable,
                    claimed=in_flight == execution.claimed_step,
                )
                if not recorded:
                    self._log(
                        logging.INFO,
                        "r2_run.step_conflict",
                        execution.run_id,
                        execution.user_id,
                        step_id=in_flight,
                        path="save_step_failed",
                    )
            except RunStoreError as store_exc:
                self._log(
                    logging.WARNING,
                    "r2_run.step_record_failed",
                    execution.run_id,
                    execution.user_id,
                    step_id=in_flight,
                    operation="save_step_failed",
                    store_error=str(store_exc),
                )
        fields = self._fields(
            "r2_run.failed",
            execution.run_id,
            execution.user_id,
            stage=stage,
            step_id=in_flight,
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

    @staticmethod
    def _retryable_for(
        exc: BaseException, attempts: int
    ) -> tuple[str, bool, type[Exception] | None]:
        """The R2-C6 table: (stage, retryable, Google config error class or None)."""
        under_limit = attempts < MAX_RETRY_ATTEMPTS
        if isinstance(exc, asyncio.CancelledError):
            return _CANCELLED, under_limit, None
        if isinstance(exc, R2_PROVIDER_ERRORS):
            config_cls = is_config_error(exc)
            return exc.stage, config_cls is None and under_limit, config_cls
        if isinstance(exc, R2_STAGE_ERRORS):
            return exc.stage, False, None
        if isinstance(exc, RunStoreError):
            # A database error on the checkpoint or finish write: the paid work was fine and a
            # blip clears on retry (decision D-R2-3, traceflow A10).
            return exc.stage, under_limit, None
        return _UNEXPECTED, False, None

    # ---- retry helpers -----------------------------------------------------------------------

    async def _load_for_action(self, user_id: str, run_id: str) -> R2RunRecord:
        """Load a run for retry. A version mismatch closes the run (not retryable) and conflicts."""
        try:
            record = await self._store.load_run(run_id, user_id)
        except StateVersionMismatchError as exc:
            await self._store.mark_version_mismatch(run_id, user_id)
            self._log(
                logging.INFO,
                "r2_run.rejected",
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
            self._log(logging.INFO, "r2_run.rejected", run_id, user_id, reason="not_found")
            raise RunNotFoundError(run_id)
        self._log_loaded(record)
        return record

    def _precheck_retry(self, record: R2RunRecord) -> None:
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

    async def _claim_resume_step(self, record: R2RunRecord, attempts: int) -> R2StepId | None:
        """Claim the failed row of the step the retry resumes at; None when there is none."""
        resume_step = remaining_steps(record.completed_step)[0].name
        step = record.steps.get(resume_step)
        if step is None or step.status != "failed":
            # A crashed (reclaimed) run, or a failure in attachment: nothing to claim. The step
            # is inserted as a new row at its write point.
            return None
        if await self._store.claim_failed_step(record.run_id, resume_step):
            return resume_step
        # The run claim won but its failed step moved: the rows disagree. Close the run.
        await self._store.save_failed(
            record.run_id,
            record.user_id,
            attempts=attempts,
            stage="claim_failed_step",
            message="The run's failed step changed during the retry",
            retryable=False,
        )
        raise self._conflict(
            record,
            reason="step_conflict",
            message="The run's failed step changed; start again",
            status="failed",
            retryable=False,
        )

    def _is_stale(self, record: R2RunRecord) -> bool:
        """True when the run is `running` and has not been written for longer than the limit."""
        if record.status != "running":
            return False
        try:
            updated_at = datetime.fromisoformat(record.updated_at)
        except ValueError as exc:
            raise RunStoreError(
                f"r2_runs updated_at is not an ISO timestamp: {record.updated_at!r}",
                operation="load_run",
            ) from exc
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return _now() - updated_at > self._stale_after

    # ---- views and logging -------------------------------------------------------------------

    @staticmethod
    def _view(record: R2RunRecord) -> R2RunView:
        """What the page shows for a stored run, by status."""
        if record.status == "running":
            return R2RunView(
                run_id=record.run_id, status="running", completed_step=record.completed_step
            )
        if record.status == "finished":
            records = (
                record.output.predefined_records
                if record.output is not None
                else record.state.predefined_records
            )
            return R2RunView(
                run_id=record.run_id,
                status="finished",
                completed_step=record.completed_step,
                result=records,
            )
        return R2RunView(
            run_id=record.run_id,
            status="failed",
            completed_step=record.completed_step,
            retryable=record.retryable,
        )

    def _conflict(
        self,
        record: R2RunRecord,
        *,
        reason: str,
        message: str,
        status: str,
        retryable: bool | None = None,
    ) -> RunConflictError:
        self._log(
            logging.INFO, "r2_run.rejected", record.run_id, record.user_id, reason=reason, status=status
        )
        return RunConflictError(message, run_id=record.run_id, status=status, retryable=retryable)

    def _superseded(self, execution: _Execution, operation: str) -> None:
        """A newer execution owns the row (lost fence): this one stops writing."""
        self._log(
            logging.INFO,
            "r2_run.superseded",
            execution.run_id,
            execution.user_id,
            operation=operation,
            attempts=execution.attempts,
        )

    def _log_loaded(self, record: R2RunRecord) -> None:
        self._log(
            logging.INFO,
            "r2_run.loaded",
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
