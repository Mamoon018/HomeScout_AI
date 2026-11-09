"""C4: one service that runs an R1 step around the run store and applies the status rules.

- Start: input check -> create the row -> R1 start -> save as paused or finished.
- Answers: load -> record answers -> save the answers -> continue R1 -> save as finished.
- Retry: load a failed, retryable run -> count the retry -> continue R1 -> save.
Any R1 error saves the run as failed with its stage. The in-memory state is never saved after a
failed continue, so the row keeps the clean copy from just before the resume (pass counter 1).
"""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from src.core.logging import DEEP_SEARCH_LOGGER_NAME, run_id_var
from src.exceptions.deep_search import (
    R1_PROVIDER_ERRORS,
    R1_STAGE_ERRORS,
    ClarificationAnswerError,
    R1RunFailedError,
    RunConflictError,
    RunNotFoundError,
    RunStoreError,
    StateVersionMismatchError,
)
from src.services.deep_search.feature_schemas.schemas import (
    ClarificationAnswer,
    R1RunRecord,
    R1RunView,
    RequirementInterpretationState,
)
from src.services.deep_search.r1_run_store import R1RunStore
from src.services.deep_search.requirement_interpretation import UserRequirementsInterpretation

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

# A run can be retried once. A failed retry is saved with retryable false.
MAX_RETRY_ATTEMPTS = 1

_UNEXPECTED_STAGE = "unexpected"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class R1RunCoordinator:
    """Ties R1's entry points to the run store under one status per run."""

    def __init__(
        self,
        interpretation: UserRequirementsInterpretation,
        store: R1RunStore,
    ) -> None:
        self._interpretation = interpretation
        self._store = store

    @property
    def store(self) -> R1RunStore:
        """The store, so R2 can read finished output through the same object."""
        return self._store

    async def start_run(self, user_id: str, raw_input: str) -> R1RunView:
        """Check the input, create the run, then run R1 until it pauses or finishes."""
        # Input that fails the check raises here, before any row exists (no run ID is issued).
        payload = self._interpretation.intake_and_assemble_payload(raw_input)

        run_id = str(uuid4())
        token = run_id_var.set(run_id)
        try:
            await self._store.create_run(run_id, user_id)
            self._log(
                logging.INFO,
                "r1_run.created",
                run_id,
                user_id,
                word_count=len(payload.normalized_text.split()),
            )
            try:
                outcome = await self._interpretation.start(payload)
            except R1_STAGE_ERRORS as exc:
                raise await self._fail(run_id, user_id, exc, retryable=False, attempts=0)
            except Exception as exc:
                raise await self._fail_unexpected(run_id, user_id, exc) from exc

            state = outcome.state
            if outcome.status == "needs_answers":
                await self._store.save_as_paused(run_id, user_id, state)
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
                    questions=list(state.clarification_questions),
                )

            await self._store.save_as_finished(run_id, user_id, state)
            self._log_finished(run_id, user_id, state, path="start")
            return R1RunView(
                run_id=run_id, status="finished", result=list(state.category_metric_plans)
            )
        finally:
            run_id_var.reset(token)

    async def submit_answers(
        self,
        user_id: str,
        run_id: str,
        answers: list[ClarificationAnswer],
    ) -> R1RunView:
        """Record the answers on the paused run, save them, then continue R1 from the saved state."""
        token = run_id_var.set(run_id)
        try:
            record = await self._load_for_action(user_id, run_id)
            if record.status != "needs_answers":
                raise self._conflict(
                    record, reason="wrong_status", message="The run is not waiting for answers"
                )
            assert record.state is not None  # a paused row always carries its state.
            state = record.state

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

            saved = await self._store.save_answers(
                run_id, user_id, state, expected_updated_at=record.updated_at
            )
            if not saved:
                raise self._conflict(
                    record,
                    reason="cas_lost",
                    message="The run changed while the answers were being saved",
                    status="needs_answers",
                )
            self._log(
                logging.INFO,
                "r1_run.answers_saved",
                run_id,
                user_id,
                answer_count=len(answers),
                other_count=sum(1 for answer in answers if answer.description is not None),
            )
            return await self._continue_and_save(record, state, is_retry=False)
        finally:
            run_id_var.reset(token)

    async def retry_run(self, user_id: str, run_id: str) -> R1RunView:
        """Run the resume steps again on the saved state and saved answers, once."""
        token = run_id_var.set(run_id)
        try:
            record = await self._load_for_action(user_id, run_id)
            if record.status != "failed":
                raise self._conflict(record, reason="wrong_status", message="The run has not failed")
            if not record.retryable or record.attempts >= MAX_RETRY_ATTEMPTS:
                raise self._conflict(
                    record, reason="not_retryable", message="The run cannot be retried"
                )
            assert record.state is not None  # retryable is only set after the answers were saved.

            started = await self._store.mark_retry_started(
                run_id, user_id, expected_attempts=record.attempts
            )
            if not started:
                raise self._conflict(
                    record,
                    reason="cas_lost",
                    message="Another retry of this run already started",
                    retryable=False,
                )
            self._log(
                logging.INFO,
                "r1_run.retry_started",
                run_id,
                user_id,
                attempts=record.attempts + 1,
            )
            return await self._continue_and_save(record, record.state, is_retry=True)
        finally:
            run_id_var.reset(token)

    async def get_run(self, user_id: str, run_id: str) -> R1RunView:
        """Read-only view of the run for refresh recovery: no LLM calls, no writes."""
        token = run_id_var.set(run_id)
        try:
            try:
                record = await self._store.load_run(run_id, user_id)
            except StateVersionMismatchError as exc:
                # The saved state cannot be read by this code. Report it as a failure the
                # customer must start again from, without writing (the status read changes nothing).
                self._log(
                    logging.WARNING,
                    "r1_run.status_degraded",
                    run_id,
                    user_id,
                    found_version=exc.found,
                    expected_version=exc.expected,
                )
                return R1RunView(run_id=run_id, status="failed", retryable=False)
            if record is None:
                self._log(logging.INFO, "r1_run.rejected", run_id, user_id, reason="not_found")
                raise RunNotFoundError(run_id)
            return _view(record)
        finally:
            run_id_var.reset(token)

    async def _load_for_action(self, user_id: str, run_id: str) -> R1RunRecord:
        """Load a run for answers or retry; a version mismatch fails the run (not retryable)."""
        try:
            record = await self._store.load_run(run_id, user_id)
        except StateVersionMismatchError as exc:
            await self._store.save_as_failed(
                run_id, user_id, stage=exc.stage, message=str(exc), retryable=False
            )
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
        return record

    async def _continue_and_save(
        self,
        record: R1RunRecord,
        state: RequirementInterpretationState,
        *,
        is_retry: bool,
    ) -> R1RunView:
        """Shared resume tail: continue R1, then save as finished or as failed."""
        run_id, user_id = record.run_id, record.user_id
        attempts = record.attempts + (1 if is_retry else 0)
        try:
            state = await self._interpretation.continue_after_answers(state)
        except R1_STAGE_ERRORS as exc:
            # Answers are saved, so a provider failure or a bad body can be retried once.
            retryable = attempts < MAX_RETRY_ATTEMPTS
            raise await self._fail(run_id, user_id, exc, retryable=retryable, attempts=attempts)
        except Exception as exc:
            raise await self._fail_unexpected(run_id, user_id, exc) from exc

        await self._store.save_as_finished(run_id, user_id, state)
        self._log_finished(run_id, user_id, state, path="retry" if is_retry else "answers")
        return R1RunView(run_id=run_id, status="finished", result=list(state.category_metric_plans))

    async def _fail(
        self,
        run_id: str,
        user_id: str,
        exc: Exception,
        *,
        retryable: bool,
        attempts: int,
    ) -> R1RunFailedError:
        """Save the run as failed with the R1 error's stage and build the typed error to raise."""
        stage = getattr(exc, "stage", "unknown")
        await self._save_failed_quietly(run_id, user_id, stage, str(exc), retryable)
        self._log(
            logging.ERROR,
            "r1_run.failed",
            run_id,
            user_id,
            stage=stage,
            error_class=type(exc).__name__,
            retryable=retryable,
            attempts=attempts,
            message=str(exc),
        )
        error = R1RunFailedError(
            str(exc),
            run_id=run_id,
            stage=stage,
            retryable=retryable,
            provider_unavailable=isinstance(exc, R1_PROVIDER_ERRORS),
        )
        error.__cause__ = exc
        return error

    async def _fail_unexpected(self, run_id: str, user_id: str, exc: Exception) -> R1RunFailedError:
        """A non-R1 exception (a bug) still leaves one clear status: failed, not retryable."""
        await self._save_failed_quietly(run_id, user_id, _UNEXPECTED_STAGE, repr(exc), False)
        logger.exception(
            json.dumps(
                {
                    "event": "r1_run.failed",
                    "timestamp": _timestamp(),
                    "run_id": run_id,
                    "user_id": user_id,
                    "stage": _UNEXPECTED_STAGE,
                    "error_class": type(exc).__name__,
                    "retryable": False,
                }
            ),
            exc_info=exc,
        )
        return R1RunFailedError(
            repr(exc),
            run_id=run_id,
            stage=_UNEXPECTED_STAGE,
            retryable=False,
            provider_unavailable=False,
            unexpected=True,
        )

    async def _save_failed_quietly(
        self, run_id: str, user_id: str, stage: str, message: str, retryable: bool
    ) -> None:
        """Save as failed; if the database is down too, log it and keep the R1 error as the answer."""
        try:
            await self._store.save_as_failed(
                run_id, user_id, stage=stage, message=message, retryable=retryable
            )
        except RunStoreError as store_exc:
            self._log(
                logging.ERROR,
                "r1_run.failed_not_saved",
                run_id,
                user_id,
                stage=stage,
                store_error=str(store_exc),
            )

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
        current_retryable = (
            retryable
            if retryable is not None
            else (record.retryable if current_status == "failed" else None)
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
            message, run_id=record.run_id, status=current_status, retryable=current_retryable
        )

    def _log_finished(
        self, run_id: str, user_id: str, state: RequirementInterpretationState, *, path: str
    ) -> None:
        self._log(
            logging.INFO,
            "r1_run.finished",
            run_id,
            user_id,
            plan_count=len(state.category_metric_plans),
            path=path,
        )

    def _log(self, level: int, event: str, run_id: str, user_id: str, **fields: object) -> None:
        logger.log(
            level,
            json.dumps(
                {
                    "event": event,
                    "timestamp": _timestamp(),
                    "run_id": run_id,
                    "user_id": user_id,
                    **fields,
                },
                default=str,
            ),
        )


def _view(record: R1RunRecord) -> R1RunView:
    """What the page shows for a stored run, by status."""
    if record.status == "needs_answers":
        assert record.state is not None
        return R1RunView(
            run_id=record.run_id,
            status="needs_answers",
            questions=list(record.state.clarification_questions),
        )
    if record.status == "finished":
        return R1RunView(run_id=record.run_id, status="finished", result=list(record.output or []))
    return R1RunView(run_id=record.run_id, status="failed", retryable=record.retryable)


def create_r1_run_coordinator(
    interpretation: UserRequirementsInterpretation,
    store: R1RunStore,
) -> R1RunCoordinator:
    """Composition helper used by the app lifespan and the live tests."""
    return R1RunCoordinator(interpretation, store)
