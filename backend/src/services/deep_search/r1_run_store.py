"""The R1 run tables: `r1_runs` (one row per run) and `r1_run_steps` (one checkpoint per step).

This is the only module in the feature that knows about Supabase. Run reads and writes filter
on the verified `user_id` as well as the `run_id`. Step writes filter on `run_id` only: the steps
table has no `user_id`, and every step write follows a run read made with the verified user in
the same request. Every write is one single-row statement, so a row's status and data always
change together. See R1_Persistence_Schema_Design.md.
"""

import json
import logging
from typing import Any

import httpx
from postgrest.exceptions import APIError
from pydantic import TypeAdapter
from supabase import AsyncClient

from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import RunStoreError, StateVersionMismatchError
from src.services.deep_search.feature_schemas.schemas import (
    ClarificationAnswer,
    ClarificationResult,
    DepthAssignmentResult,
    ExtractedRequirements,
    FlagResolutionResult,
    InferredCategoriesResult,
    MetricDefinitionResult,
    R1RunRecord,
    R1RunStatus,
    R1StepId,
    R1StepRecord,
    RequirementInterpretationState,
    TaxonomyMappingResult,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

R1_RUNS_TABLE = "r1_runs"
R1_RUN_STEPS_TABLE = "r1_run_steps"

# Bump when R1's workflow changes so that saved steps no longer rebuild the same state. A run
# saved under another version is not resumed: it reads as failed, not retryable.
R1_WORKFLOW_VERSION = 1

# Bump when one step's payload model changes shape. Checked on every load.
STEP_SCHEMA_VERSION = 1

# Postgres "unique_violation": the step row already exists, so another execution owns it.
_UNIQUE_VIOLATION = "23505"

# One validation model per step payload, applied before write and after read.
_STEP_ADAPTERS: dict[str, TypeAdapter] = {
    "extraction": TypeAdapter(ExtractedRequirements),
    "taxonomy_mapping": TypeAdapter(TaxonomyMappingResult),
    "clarification_questions": TypeAdapter(ClarificationResult),
    "clarification_answers": TypeAdapter(list[ClarificationAnswer]),
    "flag_resolution": TypeAdapter(FlagResolutionResult),
    "category_inference": TypeAdapter(InferredCategoriesResult),
    "depth_assignment": TypeAdapter(DepthAssignmentResult),
    "metric_definition": TypeAdapter(MetricDefinitionResult),
}

_STATE_ADAPTER = TypeAdapter(RequirementInterpretationState)


def dump_step_output(step_id: R1StepId, result: Any) -> dict:
    """The step's result as JSON-ready data inside a version envelope."""
    adapter = _STEP_ADAPTERS[step_id]
    return {
        "schema_version": STEP_SCHEMA_VERSION,
        "data": adapter.dump_python(adapter.validate_python(result), mode="json"),
    }


def load_step_output(step_id: R1StepId, data: dict) -> Any:
    """Rebuild the step's typed result after a version check."""
    found = data.get("schema_version") if isinstance(data, dict) else None
    if found != STEP_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, STEP_SCHEMA_VERSION)
    return _STEP_ADAPTERS[step_id].validate_python(data["data"])


def dump_state(state: RequirementInterpretationState) -> dict:
    """A full state as JSON data, for parity checks and printing only. Never stored."""
    return _STATE_ADAPTER.dump_python(state, mode="json")


class R1RunStore:
    """Create, load and update rows of `r1_runs` and `r1_run_steps` through the async client."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    # ---- run rows ----------------------------------------------------------------------------

    async def create_run(self, run_id: str, user_id: str, raw_input: str) -> None:
        """Add the run's row after the input check and before the first LLM step."""
        await self._execute(
            "create_run",
            self._client.table(R1_RUNS_TABLE).insert(
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "workflow_version": R1_WORKFLOW_VERSION,
                    "raw_input": raw_input,
                    "status": "running",
                    "attempts": 0,
                }
            ),
        )

    async def set_status(
        self,
        run_id: str,
        user_id: str,
        *,
        to: R1RunStatus,
        expected: R1RunStatus,
    ) -> bool:
        """Move the run's status only when it is still `expected`. False when it moved."""
        rows = await self._execute(
            "set_status",
            self._client.table(R1_RUNS_TABLE)
            .update({"status": to})
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .eq("status", expected),
        )
        return len(rows) == 1

    async def claim_retry(self, run_id: str, user_id: str, *, expected_attempts: int) -> bool:
        """Count the retry and set `running` in one update. False if another retry won."""
        rows = await self._execute(
            "claim_retry",
            self._client.table(R1_RUNS_TABLE)
            .update({"status": "running", "attempts": expected_attempts + 1})
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .eq("status", "failed")
            .eq("attempts", expected_attempts),
        )
        return len(rows) == 1

    async def load_run(self, run_id: str, user_id: str) -> R1RunRecord | None:
        """Read the run and all its steps in one request. None when it is not this user's run."""
        rows = await self._execute(
            "load_run",
            self._client.table(R1_RUNS_TABLE)
            .select(f"*, {R1_RUN_STEPS_TABLE}(*)")
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .limit(1),
        )
        if not rows:
            return None
        row = rows[0]
        if R1_RUN_STEPS_TABLE not in row or not isinstance(row[R1_RUN_STEPS_TABLE], list):
            # The embedded read did not return the steps. Fail loudly rather than read the run
            # as one with no saved steps, which would replay it from the start.
            raise RunStoreError("r1_runs load_run did not return the run's steps", operation="load_run")
        found = row.get("workflow_version")
        if found != R1_WORKFLOW_VERSION:
            raise StateVersionMismatchError(found, R1_WORKFLOW_VERSION)
        steps: dict[R1StepId, R1StepRecord] = {}
        for step_row in row[R1_RUN_STEPS_TABLE]:
            step_id = step_row["step_id"]
            output = step_row.get("output")
            steps[step_id] = R1StepRecord(
                step_id=step_id,
                status=step_row["status"],
                output=load_step_output(step_id, output) if output is not None else None,
                error_type=step_row.get("error_type"),
                error_message=step_row.get("error_message"),
                retryable=step_row.get("retryable"),
            )
        return R1RunRecord(
            run_id=str(row["run_id"]),
            user_id=str(row["user_id"]),
            status=row["status"],
            raw_input=row["raw_input"],
            attempts=int(row.get("attempts") or 0),
            updated_at=str(row["updated_at"]),
            steps=steps,
        )

    # ---- step rows ---------------------------------------------------------------------------

    async def insert_step(self, run_id: str, step_id: R1StepId, result: Any) -> bool:
        """Save a completed step. False when the step row already exists (another execution)."""
        try:
            await self._execute(
                "insert_step",
                self._client.table(R1_RUN_STEPS_TABLE).insert(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "status": "completed",
                        "output": dump_step_output(step_id, result),
                    }
                ),
                conflict_ok=True,
            )
        except _StepConflict:
            return False
        return True

    async def complete_claimed_step(self, run_id: str, step_id: R1StepId, result: Any) -> bool:
        """Move the retried step from `started` to `completed` with its output."""
        rows = await self._execute(
            "complete_claimed_step",
            self._client.table(R1_RUN_STEPS_TABLE)
            .update({"status": "completed", "output": dump_step_output(step_id, result)})
            .eq("run_id", run_id)
            .eq("step_id", step_id)
            .eq("status", "started"),
        )
        return len(rows) == 1

    async def claim_failed_step(self, run_id: str, step_id: R1StepId) -> bool:
        """Move the failed step to `started` and clear its error, before the retry runs it."""
        rows = await self._execute(
            "claim_failed_step",
            self._client.table(R1_RUN_STEPS_TABLE)
            .update(
                {"status": "started", "error_type": None, "error_message": None, "retryable": None}
            )
            .eq("run_id", run_id)
            .eq("step_id", step_id)
            .eq("status", "failed"),
        )
        return len(rows) == 1

    async def save_step_failed(
        self,
        run_id: str,
        step_id: R1StepId,
        *,
        error_type: str,
        message: str,
        retryable: bool,
        claimed: bool,
    ) -> None:
        """Record the step's failure: a new row, or `started → failed` for a claimed retry step."""
        values = {
            "status": "failed",
            "error_type": error_type,
            "error_message": message,
            "retryable": retryable,
        }
        table = self._client.table(R1_RUN_STEPS_TABLE)
        if claimed:
            query = (
                table.update(values)
                .eq("run_id", run_id)
                .eq("step_id", step_id)
                .eq("status", "started")
            )
        else:
            query = table.insert({"run_id": run_id, "step_id": step_id, **values})
        await self._execute("save_step_failed", query)

    # ---- shared ------------------------------------------------------------------------------

    async def _execute(self, operation: str, query: Any, *, conflict_ok: bool = False) -> list[dict]:
        """Run one query; turn SDK and transport errors into one typed store error."""
        try:
            response = await query.execute()
        except APIError as exc:
            if conflict_ok and exc.code == _UNIQUE_VIOLATION:
                raise _StepConflict() from exc
            self._log_error(operation, exc)
            raise RunStoreError(f"{operation} failed: {exc}", operation=operation) from exc
        except httpx.HTTPError as exc:
            self._log_error(operation, exc)
            raise RunStoreError(f"{operation} failed: {exc}", operation=operation) from exc
        return list(response.data or [])

    @staticmethod
    def _log_error(operation: str, exc: Exception) -> None:
        logger.error(
            json.dumps(
                {
                    "event": "r1_run.store_error",
                    "operation": operation,
                    "error_class": type(exc).__name__,
                    "detail": str(exc),
                }
            )
        )


class _StepConflict(Exception):
    """Internal: an insert hit an existing step row (unique violation)."""
