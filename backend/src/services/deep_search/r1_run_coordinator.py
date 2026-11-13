"""R1's run lifecycle over HTTP, around the two run tables (R1 Step Persistence).

- Start: input check -> create the run -> drive R1 live, saving each LLM step -> pause or finish.
- Answers: load -> replay to the pause (no LLM call) -> check and save the answers -> drive on.
- Retry: load -> claim the run and its failed step -> replay saved steps -> resume at that step.
- Status: load -> report the run; a run stuck in `running` reads as failed, not retryable.

Every path drives R1 through the same entry points with an `R1StepCheckpoints` object: a step
with a saved result is not called again, and a new result is saved before the next step starts.
A failure is recorded against the step that was running (`in_flight`).
"""

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from src.core.logging import DEEP_SEARCH_LOGGER_NAME, run_id_var
from src.exceptions.deep_search import (
    R1_PROVIDER_ERRORS,
    R1_STAGE_ERRORS,
    CheckpointMissingError,
    ClarificationAnswerError,
    R1RunFailedError,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    StateVersionMismatchError,
)
from src.services.deep_search.feature_schemas.schemas import (
    ClarificationAnswer,
    PayloadRecord,
    R1RunRecord,
    R1RunView,
    R1StartOutcome,
    R1StepCheckpoints,
    R1StepId,
)
from src.services.deep_search.r1_run_store import (
    R1_WORKFLOW_VERSION,
    STEP_SCHEMA_VERSION,
    R1RunStore,
    dump_step_output,
)
from src.services.deep_search.requirement_interpretation import UserRequirementsInterpretation

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# A run can be retried once. A failed retry is saved with retryable false.
MAX_RETRY_ATTEMPTS = 1

# A run still `running` after this long was cut off and reads as failed (decision D1).
DEFAULT_STALE_AFTER_SECONDS = 180.0

_UNEXPECTED = "unexpected"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class R1RunCoordinator:
    """Ties R1's entry points to the run tables under one status per run."""

    def __init__(
        self,
        interpretation: UserRequirementsInterpretation,
        store: R1RunStore,
        *,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self._interpretation = interpretation
        self._store = store
        self._stale_after = timedelta(seconds=stale_after_seconds)

    # ---- entry points ------------------------------------------------------------------------

    async def start_run(self, user_id: str, raw_input: str) -> R1RunView:
        """Check the input, create the run, then run R1 until it pauses or finishes."""
        # Input that fails the check raises here, before any row exists (no run ID is issued).
        payload = self._interpretation.intake_and_assemble_payload(raw_input)

        run_id = str(uuid4())
        token = run_id_var.set(run_id)
        try:
            await self._store.create_run(run_id, user_id, raw_input)
            self._log(
                logging.INFO,
                "r1_run.created",
                run_id,
                user_id,
                workflow_version=R1_WORKFLOW_VERSION,
                word_count=len(payload.normalized_text.split()),
            )
            checkpoints = self._checkpoints(run_id, user_id, completed={})
            return await self._run_live(
                run_id,
                user_id,
                checkpoints,
                attempts=0,
                path="start",
                work=lambda: self._drive_run(payload, checkpoints),
            )
        finally:
            run_id_var.reset(token)

    async def submit_answers(
        self,
        user_id: str,
        run_id: str,
        answers: list[ClarificationAnswer],
    ) -> R1RunView:
        """Rebuild the paused run, check and save the answers, then continue R1."""
        token = run_id_var.set(run_id)
        try:
            record = await self._load_for_action(user_id, run_id)
            if record.status != "needs_answers":
                raise self._conflict(
                    record, reason="wrong_status", message="The run is not waiting for answers"
                )
            checkpoints = self._checkpoints(
                run_id, user_id, completed=dict(record.completed), allow_calls=False
            )
            paused = await self._replay_to_pause(record, checkpoints)
            state = paused.state

            try:
                self._interpretation.record_clarification_answers(state, answers)
            except ClarificationAnswerError as exc:
                self._log(
                    logging.INFO,
                    "r1_run.rejected",
                    run_id,
                    user_id,
                    reason="answers_invalid",
                    status=record.status,
                    detail=str(exc),
                )
                raise

            if not await self._store.set_status(
                run_id, user_id, to="running", expected="needs_answers"
            ):
                raise self._conflict(
                    record,
                    reason="cas_lost",
                    message="The run changed while the answers were being saved",
                )
            if not await self._store.insert_step(run_id, "clarification_answers", answers):
                raise self._conflict(
                    record,
                    reason="step_conflict",
                    message="The answers for this run were already saved",
                    status="running",
                )
            checkpoints.completed["clarification_answers"] = list(answers)
            checkpoints.allow_calls = True
            self._log(
                logging.INFO,
                "r1_run.answers_saved",
                run_id,
                user_id,
                answer_count=len(answers),
                other_count=sum(1 for answer in answers if answer.description is not None),
            )

            async def continue_after_answers() -> R1StartOutcome:
                finished = await self._interpretation.continue_after_answers(
                    state, checkpoints=checkpoints
                )
                return R1StartOutcome(status="finished", state=finished)

            return await self._run_live(
                run_id,
                user_id,
                checkpoints,
                attempts=record.attempts,
                path="answers",
                work=continue_after_answers,
            )
        finally:
            run_id_var.reset(token)

    async def retry_run(self, user_id: str, run_id: str) -> R1RunView:
        """Claim the failed run and its failed step, then resume R1 at that step, once."""
        token = run_id_var.set(run_id)
        try:
            record = await self._load_for_action(user_id, run_id)
            if self._is_stuck(record):
                raise self._conflict(
                    record,
                    reason="stuck",
                    message="The run was cut off and cannot be retried; start again",
                    status="failed",
                    retryable=False,
                )
            if record.status != "failed":
                raise self._conflict(record, reason="wrong_status", message="The run has not failed")
            failed = record.failed_step
            if failed is None or not failed.retryable or record.attempts >= MAX_RETRY_ATTEMPTS:
                raise self._conflict(
                    record,
                    reason="not_retryable",
                    message="The run cannot be retried",
                    retryable=False,
                )
            if not await self._store.claim_retry(
                run_id, user_id, expected_attempts=record.attempts
            ):
                raise self._conflict(
                    record,
                    reason="cas_lost",
                    message="Another retry of this run already started",
                    retryable=False,
                )
            if not await self._store.claim_failed_step(run_id, failed.step_id):
                # The run claim won but its failed step moved: the rows disagree. Close the run.
                await self._store.set_status(run_id, user_id, to="failed", expected="running")
                raise self._conflict(
                    record,
                    reason="step_conflict",
                    message="The run's failed step changed; start again",
                    status="failed",
                    retryable=False,
                )
            attempts = record.attempts + 1
            self._log(
                logging.INFO,
                "r1_run.retry_started",
                run_id,
                user_id,
                attempts=attempts,
                claimed_step=failed.step_id,
            )
            checkpoints = self._checkpoints(
                run_id, user_id, completed=dict(record.completed), claimed_step=failed.step_id
            )
            payload = self._interpretation.intake_and_assemble_payload(record.raw_input)
            return await self._run_live(
                run_id,
                user_id,
                checkpoints,
                attempts=attempts,
                path="retry",
                work=lambda: self._drive_run(payload, checkpoints),
            )
        finally:
            run_id_var.reset(token)

    async def get_run(self, user_id: str, run_id: str) -> R1RunView:
        """Read-only view of the run for refresh recovery: no LLM calls, no writes."""
        token = run_id_var.set(run_id)
        try:
            try:
                record = await self._store.load_run(run_id, user_id)
            except StateVersionMismatchError as exc:
                self._log(
                    logging.WARNING,
                    "r1_run.status_degraded",
                    run_id,
                    user_id,
                    reason="version_mismatch",
                    found_version=exc.found,
                    expected_version=exc.expected,
                )
                return R1RunView(run_id=run_id, status="failed", retryable=False)
            if record is None:
                self._log(logging.INFO, "r1_run.rejected", run_id, user_id, reason="not_found")
                raise RunNotFoundError(run_id)
            self._log_loaded(record)
            if self._is_stuck(record):
                self._log(
                    logging.WARNING,
                    "r1_run.stuck_reported",
                    run_id,
                    user_id,
                    status=record.status,
                    updated_at=record.updated_at,
                    stale_after_seconds=self._stale_after.total_seconds(),
                )
                return R1RunView(run_id=run_id, status="failed", retryable=False)
            return await self._view(record)
        finally:
            run_id_var.reset(token)

    # ---- stages ------------------------------------------------------------------------------

    def _checkpoints(
        self,
        run_id: str,
        user_id: str,
        *,
        completed: dict[R1StepId, Any],
        allow_calls: bool = True,
        claimed_step: R1StepId | None = None,
    ) -> R1StepCheckpoints:
        """The per-request checkpoint object; its save callback writes this run's step rows."""

        async def save(step_id: R1StepId, result: Any) -> None:
            if step_id == claimed_step:
                saved = await self._store.complete_claimed_step(run_id, step_id, result)
                path = "claimed"
            else:
                saved = await self._store.insert_step(run_id, step_id, result)
                path = "insert"
            if not saved:
                self._log(
                    logging.INFO,
                    "r1_run.rejected",
                    run_id,
                    user_id,
                    reason="step_conflict",
                    step_id=step_id,
                )
                raise RunConflictError(
                    "The run changed while it was running",
                    run_id=run_id,
                    status="running",
                    retryable=None,
                )
            self._log(
                logging.INFO,
                "r1_step.saved",
                run_id,
                user_id,
                step_id=step_id,
                path=path,
                schema_version=STEP_SCHEMA_VERSION,
                output_chars=len(json.dumps(dump_step_output(step_id, result))),
            )

        return R1StepCheckpoints(
            completed=completed,
            allow_calls=allow_calls,
            claimed_step=claimed_step,
            on_completed=save,
        )

    async def _drive_run(
        self, payload: PayloadRecord, checkpoints: R1StepCheckpoints
    ) -> R1StartOutcome:
        """Run R1 from the start; saved steps return their results, the rest are called.

        A paused run whose answers are saved records them and continues to the end, so the same
        path serves start, retry and the rebuild of a finished run.
        """
        outcome = await self._interpretation.start(payload, checkpoints=checkpoints)
        if outcome.status == "finished":
            return outcome
        answers = checkpoints.completed.get("clarification_answers")
        if answers is None:
            return outcome
        self._interpretation.record_clarification_answers(outcome.state, answers)
        state = await self._interpretation.continue_after_answers(
            outcome.state, checkpoints=checkpoints
        )
        return R1StartOutcome(status="finished", state=state)

    async def _replay_to_pause(
        self, record: R1RunRecord, checkpoints: R1StepCheckpoints
    ) -> R1StartOutcome:
        """Rebuild a paused run with no LLM call; an incomplete or unpaused rebuild is a conflict."""
        payload = self._interpretation.intake_and_assemble_payload(record.raw_input)
        try:
            outcome = await self._drive_run(payload, checkpoints)
        except CheckpointMissingError as exc:
            self._log(
                logging.WARNING,
                "r1_run.status_degraded",
                record.run_id,
                record.user_id,
                reason="missing_step",
                step_id=exc.step_id,
            )
            raise self._conflict(
                record,
                reason="missing_step",
                message="The run's saved steps are incomplete; start again",
                status="failed",
                retryable=False,
            ) from exc
        if outcome.status != "needs_answers":
            raise self._conflict(
                record, reason="wrong_status", message="The run is not waiting for answers"
            )
        return outcome

    async def _run_live(
        self,
        run_id: str,
        user_id: str,
        checkpoints: R1StepCheckpoints,
        *,
        attempts: int,
        path: str,
        work: Callable[[], Awaitable[R1StartOutcome]],
    ) -> R1RunView:
        """Run R1's remaining steps, then settle the status; any R1 error fails the run."""
        try:
            outcome = await work()
        except (RunConflictError, RunStoreError):
            # Another execution owns the run, or the database is down: nothing to record here.
            raise
        except Exception as exc:
            raise await self._fail(run_id, user_id, checkpoints, exc, attempts=attempts) from exc
        return await self._settle(run_id, user_id, outcome, path=path)

    async def _settle(
        self, run_id: str, user_id: str, outcome: R1StartOutcome, *, path: str
    ) -> R1RunView:
        """Move the run from `running` to `needs_answers` or `finished`."""
        state = outcome.state
        if outcome.status == "finished":
            # Status and output in one update, so a finished run always carries its output (R2-P1).
            moved = await self._store.mark_finished(
                run_id, user_id, plans=list(state.category_metric_plans)
            )
        else:
            moved = await self._store.set_status(
                run_id, user_id, to=outcome.status, expected="running"
            )
        if not moved:
            current = await self._store.load_run(run_id, user_id)
            status = current.status if current is not None else "failed"
            self._log(logging.INFO, "r1_run.rejected", run_id, user_id, reason="cas_lost", status=status)
            raise RunConflictError(
                "The run changed while it was running", run_id=run_id, status=status, retryable=None
            )
        if outcome.status == "needs_answers":
            self._log(
                logging.INFO,
                "r1_run.paused",
                run_id,
                user_id,
                question_count=len(state.clarification_questions),
                category_ids=[q.category_id for q in state.clarification_questions],
            )
            return R1RunView(
                run_id=run_id,
                status="needs_answers",
                user_requirements_structured=state.extracted,
                questions=list(state.clarification_questions),
            )
        self._log(
            logging.INFO,
            "r1_run.finished",
            run_id,
            user_id,
            plan_count=len(state.category_metric_plans),
            path=path,
        )
        return R1RunView(
            run_id=run_id,
            status="finished",
            user_requirements_structured=state.extracted,
            result=list(state.category_metric_plans),
        )

    async def _fail(
        self,
        run_id: str,
        user_id: str,
        checkpoints: R1StepCheckpoints,
        exc: Exception,
        *,
        attempts: int,
    ) -> R1RunFailedError:
        """Record the failed step (when one was running), set the run failed, build the error."""
        step_id = checkpoints.in_flight
        unexpected = not isinstance(exc, R1_STAGE_ERRORS)
        # A provider failure or a bad body can be retried once, in either phase (decision D5).
        retryable = not unexpected and step_id is not None and attempts < MAX_RETRY_ATTEMPTS
        error_type = _UNEXPECTED if unexpected else type(exc).__name__
        message = repr(exc) if unexpected else str(exc)
        stage = _UNEXPECTED if unexpected else getattr(exc, "stage", None) or "unknown"
        try:
            if step_id is not None:
                await self._store.save_step_failed(
                    run_id,
                    step_id,
                    error_type=error_type,
                    message=message,
                    retryable=retryable,
                    claimed=step_id == checkpoints.claimed_step,
                )
            await self._store.set_status(run_id, user_id, to="failed", expected="running")
        except RunStoreError as store_exc:
            # The database is down too: keep the R1 error as the answer. The row stays
            # `running` and reads as failed once it is stale (D1).
            self._log(
                logging.ERROR,
                "r1_run.failed_not_saved",
                run_id,
                user_id,
                step_id=step_id,
                store_error=str(store_exc),
            )
        fields = {
            "step_id": step_id,
            "stage": stage,
            "error_class": type(exc).__name__,
            "retryable": retryable,
            "attempts": attempts,
        }
        if unexpected:
            logger.exception(
                json.dumps(self._fields("r1_run.failed", run_id, user_id, **fields), default=str),
                exc_info=exc,
            )
        else:
            self._log(logging.ERROR, "r1_run.failed", run_id, user_id, message=message, **fields)
        return R1RunFailedError(
            message,
            run_id=run_id,
            stage=stage,
            retryable=retryable,
            provider_unavailable=isinstance(exc, R1_PROVIDER_ERRORS),
            unexpected=unexpected,
        )

    def _is_stuck(self, record: R1RunRecord) -> bool:
        """True when the run is `running` and has not moved for longer than the threshold."""
        if record.status != "running":
            return False
        try:
            updated_at = datetime.fromisoformat(record.updated_at)
        except ValueError as exc:
            raise RunStoreError(
                f"r1_runs updated_at is not an ISO timestamp: {record.updated_at!r}",
                operation="load_run",
            ) from exc
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - updated_at > self._stale_after

    async def _view(self, record: R1RunRecord) -> R1RunView:
        """What the page shows for a stored run, by status."""
        if record.status == "running":
            return R1RunView(run_id=record.run_id, status="running")
        # The saved extraction output, or None when that step never completed.
        extracted = record.completed.get("extraction")
        if record.status == "needs_answers":
            questions = record.completed.get("clarification_questions")
            if questions is None:
                return self._degraded(record, step_id="clarification_questions")
            if extracted is None:
                return self._degraded(record, step_id="extraction")
            return R1RunView(
                run_id=record.run_id,
                status="needs_answers",
                user_requirements_structured=extracted,
                questions=list(questions.questions),
            )
        if record.status == "finished":
            checkpoints = R1StepCheckpoints(completed=dict(record.completed), allow_calls=False)
            payload = self._interpretation.intake_and_assemble_payload(record.raw_input)
            try:
                outcome = await self._drive_run(payload, checkpoints)
            except CheckpointMissingError as exc:
                return self._degraded(record, step_id=exc.step_id)
            return R1RunView(
                run_id=record.run_id,
                status="finished",
                user_requirements_structured=outcome.state.extracted,
                result=list(outcome.state.category_metric_plans),
            )
        failed = record.failed_step
        retryable = (
            failed is not None and bool(failed.retryable) and record.attempts < MAX_RETRY_ATTEMPTS
        )
        return R1RunView(
            run_id=record.run_id,
            status="failed",
            user_requirements_structured=extracted,
            retryable=retryable,
        )

    # ---- helpers -----------------------------------------------------------------------------

    async def _load_for_action(self, user_id: str, run_id: str) -> R1RunRecord:
        """Load a run for answers or retry. A version mismatch is a conflict: start again."""
        try:
            record = await self._store.load_run(run_id, user_id)
        except StateVersionMismatchError as exc:
            self._log(
                logging.INFO,
                "r1_run.rejected",
                run_id,
                user_id,
                reason="version_mismatch",
                found_version=exc.found,
                expected_version=exc.expected,
            )
            raise RunConflictError(
                "The run was saved by an older version; start again",
                run_id=run_id,
                status="failed",
                retryable=False,
            ) from exc
        if record is None:
            self._log(logging.INFO, "r1_run.rejected", run_id, user_id, reason="not_found")
            raise RunNotFoundError(run_id)
        self._log_loaded(record)
        return record

    def _degraded(self, record: R1RunRecord, *, step_id: str) -> R1RunView:
        """A run whose saved steps cannot rebuild it reads as failed, not retryable."""
        self._log(
            logging.WARNING,
            "r1_run.status_degraded",
            record.run_id,
            record.user_id,
            reason="missing_step",
            step_id=step_id,
            status=record.status,
        )
        return R1RunView(run_id=record.run_id, status="failed", retryable=False)

    def _conflict(
        self,
        record: R1RunRecord,
        *,
        reason: str,
        message: str,
        status: str | None = None,
        retryable: bool | None = None,
    ) -> RunConflictError:
        current_status = status or record.status
        if retryable is None and current_status == "failed":
            failed = record.failed_step
            retryable = (
                failed is not None
                and bool(failed.retryable)
                and record.attempts < MAX_RETRY_ATTEMPTS
            )
        self._log(
            logging.INFO,
            "r1_run.rejected",
            record.run_id,
            record.user_id,
            reason=reason,
            status=current_status,
        )
        return RunConflictError(
            message, run_id=record.run_id, status=current_status, retryable=retryable
        )

    def _log_loaded(self, record: R1RunRecord) -> None:
        failed = record.failed_step
        self._log(
            logging.INFO,
            "r1_run.loaded",
            record.run_id,
            record.user_id,
            status=record.status,
            attempts=record.attempts,
            completed_steps=sorted(record.completed),
            failed_step=failed.step_id if failed is not None else None,
        )

    @staticmethod
    def _fields(event: str, run_id: str, user_id: str, **fields: object) -> dict:
        return {
            "event": event,
            "timestamp": _timestamp(),
            "run_id": run_id,
            "user_id": user_id,
            **fields,
        }

    def _log(self, level: int, event: str, run_id: str, user_id: str, **fields: object) -> None:
        logger.log(level, json.dumps(self._fields(event, run_id, user_id, **fields), default=str))


def create_r1_run_coordinator(
    interpretation: UserRequirementsInterpretation,
    store: R1RunStore,
    *,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> R1RunCoordinator:
    """Composition helper used by the app lifespan and the live tests."""
    return R1RunCoordinator(interpretation, store, stale_after_seconds=stale_after_seconds)
