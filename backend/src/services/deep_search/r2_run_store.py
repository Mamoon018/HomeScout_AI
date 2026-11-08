"""The R2 run tables: `r2_runs` (one row per run) and `r2_run_steps` (one record per step).

This is the only R2 module that knows about Supabase. Run reads and writes filter on the verified
`user_id` as well as the `run_id`. Every write after the run is created is fenced: it matches only
while the row is `running` at the writing execution's `attempts`, so an older execution that wakes
up late changes nothing (R2-C5). "Save as failed" never touches `state` or `completed_step`, so a
retry resumes from the last good checkpoint. Step writes filter on `run_id` only: the steps table
has no `user_id`, and every step write follows a matched run write for this user (R2-C4).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from postgrest.exceptions import APIError
from pydantic import TypeAdapter
from supabase import AsyncClient

from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import RunStoreError, StateVersionMismatchError
from src.services.deep_search.feature_schemas.schemas import (
    AmenitySearchOutput,
    AmenitySearchState,
    CanonicalPlace,
    EnrichmentBundle,
    R2RunRecord,
    R2StepId,
    R2StepRecord,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

R2_RUNS_TABLE = "r2_runs"
R2_RUN_STEPS_TABLE = "r2_run_steps"

# Bump when `AmenitySearchState` or `AmenitySearchOutput` changes shape. A run saved under another
# version is not resumed: it is failed, not retryable (R2-C3).
R2_STATE_SCHEMA_VERSION = 1

# Bump when a step record's payload changes shape. Checked on every load.
R2_STEP_SCHEMA_VERSION = 1

# Postgres "unique_violation": the step row already exists, so another execution owns it.
_UNIQUE_VIOLATION = "23505"

_STATE_ADAPTER = TypeAdapter(AmenitySearchState)
_OUTPUT_ADAPTER = TypeAdapter(AmenitySearchOutput)
_STEP_ADAPTERS: dict[str, TypeAdapter] = {
    "discovery": TypeAdapter(dict[int, dict[str, CanonicalPlace]]),
    "enrichment": TypeAdapter(dict[str, EnrichmentBundle]),
}


# ---- codecs ------------------------------------------------------------------------------------


def dump_state(state: AmenitySearchState) -> dict:
    """The R2 state as JSON-ready data inside a version envelope."""
    return {
        "version": R2_STATE_SCHEMA_VERSION,
        "state": _STATE_ADAPTER.dump_python(state, mode="json"),
    }


def load_state(data: dict) -> AmenitySearchState:
    """Rebuild the typed state after a version check (int category keys come back as ints)."""
    found = data.get("version") if isinstance(data, dict) else None
    if found != R2_STATE_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, R2_STATE_SCHEMA_VERSION)
    return _STATE_ADAPTER.validate_python(data["state"])


def dump_output(output: AmenitySearchOutput) -> dict:
    """The R2 → R3 handoff as JSON-ready data inside a version envelope."""
    return {
        "version": R2_STATE_SCHEMA_VERSION,
        "output": _OUTPUT_ADAPTER.dump_python(output, mode="json"),
    }


def load_output(data: dict) -> AmenitySearchOutput:
    """Rebuild the typed handoff after a version check."""
    found = data.get("version") if isinstance(data, dict) else None
    if found != R2_STATE_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, R2_STATE_SCHEMA_VERSION)
    return _OUTPUT_ADAPTER.validate_python(data["output"])


def dump_step_output(step_id: R2StepId, result: Any) -> dict:
    """One step's result (discovered_places or enrichment) in R1's step envelope."""
    adapter = _STEP_ADAPTERS[step_id]
    return {
        "schema_version": R2_STEP_SCHEMA_VERSION,
        "data": adapter.dump_python(result, mode="json"),
    }


def load_step_output(step_id: R2StepId, data: dict) -> Any:
    """Rebuild one step's typed result after a version check."""
    found = data.get("schema_version") if isinstance(data, dict) else None
    if found != R2_STEP_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, R2_STEP_SCHEMA_VERSION)
    return _STEP_ADAPTERS[step_id].validate_python(data["data"])


def stale_cutoff_filter(stale_before: datetime) -> str:
    """The claim's OR condition: failed and retryable, or running with no write since the cutoff.

    The cutoff is UTC with a `Z` suffix and quoted, so its `.` and `:` are not read as
    PostgREST filter syntax (traceflow A6).
    """
    cutoff = stale_before.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return (
        "and(status.eq.failed,retryable.is.true),"
        f'and(status.eq.running,updated_at.lt."{cutoff}")'
    )


# ---- store -------------------------------------------------------------------------------------


class R2RunStore:
    """Create, load and update rows of `r2_runs` and `r2_run_steps` through the async client."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    # ---- run rows ----------------------------------------------------------------------------

    async def create_run(
        self, run_id: str, user_id: str, r1_run_id: str, state: AmenitySearchState
    ) -> None:
        """Add the run's row: `running`, attempts 0, no checkpoint yet, the initial state."""
        await self._execute(
            "create_run",
            self._client.table(R2_RUNS_TABLE).insert(
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "r1_run_id": r1_run_id,
                    "status": "running",
                    "state": dump_state(state),
                    "completed_step": None,
                    "retryable": False,
                    "attempts": 0,
                }
            ),
        )

    async def save_checkpoint(
        self,
        run_id: str,
        user_id: str,
        *,
        attempts: int,
        state: AmenitySearchState,
        completed_step: str,
    ) -> bool:
        """Write the state and the completed step. False when a newer execution owns the row."""
        rows = await self._execute(
            "save_checkpoint",
            self._fenced(
                self._client.table(R2_RUNS_TABLE).update(
                    {"state": dump_state(state), "completed_step": completed_step}
                ),
                run_id,
                user_id,
                attempts,
            ),
        )
        return len(rows) == 1

    async def save_finished(
        self,
        run_id: str,
        user_id: str,
        *,
        attempts: int,
        state: AmenitySearchState,
        output: AmenitySearchOutput,
    ) -> bool:
        """Write the final state and output and set `finished` in one fenced update."""
        rows = await self._execute(
            "save_finished",
            self._fenced(
                self._client.table(R2_RUNS_TABLE).update(
                    {
                        "status": "finished",
                        "state": dump_state(state),
                        "output": dump_output(output),
                        "retryable": False,
                        # A retried run that finishes no longer carries its earlier failure.
                        "failure_stage": None,
                        "failure_message": None,
                    }
                ),
                run_id,
                user_id,
                attempts,
            ),
        )
        return len(rows) == 1

    async def save_failed(
        self,
        run_id: str,
        user_id: str,
        *,
        attempts: int,
        stage: str,
        message: str,
        retryable: bool,
    ) -> bool:
        """Set `failed` with its stage, message and `retryable`; state and checkpoint untouched."""
        rows = await self._execute(
            "save_failed",
            self._fenced(
                self._client.table(R2_RUNS_TABLE).update(
                    {
                        "status": "failed",
                        "failure_stage": stage,
                        "failure_message": message,
                        "retryable": retryable,
                    }
                ),
                run_id,
                user_id,
                attempts,
            ),
        )
        return len(rows) == 1

    async def claim_retry(
        self,
        run_id: str,
        user_id: str,
        *,
        expected_attempts: int,
        stale_before: datetime,
    ) -> bool:
        """The single-execution guard: one update; only one request can match (R2-C5)."""
        rows = await self._execute(
            "claim_retry",
            self._client.table(R2_RUNS_TABLE)
            .update({"status": "running", "attempts": expected_attempts + 1, "retryable": False})
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .eq("attempts", expected_attempts)
            .or_(stale_cutoff_filter(stale_before)),
        )
        return len(rows) == 1

    async def mark_version_mismatch(self, run_id: str, user_id: str) -> None:
        """Close a run saved by another version: failed, not retryable (never a finished one)."""
        await self._execute(
            "mark_version_mismatch",
            self._client.table(R2_RUNS_TABLE)
            .update(
                {
                    "status": "failed",
                    "failure_stage": StateVersionMismatchError.stage,
                    "failure_message": "The run was saved by another version; start again",
                    "retryable": False,
                }
            )
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .neq("status", "finished"),
        )

    async def load_run(self, run_id: str, user_id: str) -> R2RunRecord | None:
        """Read the run and its step rows in one request. None when it is not this user's run."""
        rows = await self._execute(
            "load_run",
            self._client.table(R2_RUNS_TABLE)
            .select(f"*, {R2_RUN_STEPS_TABLE}(step_id, status, error_type, retryable)")
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .limit(1),
        )
        if not rows:
            return None
        row = rows[0]
        if R2_RUN_STEPS_TABLE not in row or not isinstance(row[R2_RUN_STEPS_TABLE], list):
            # The embedded read did not return the steps. Fail loudly rather than read the run as
            # one with no step rows, which would insert duplicates on the next write.
            raise RunStoreError("r2_runs load_run did not return the run's steps", operation="load_run")
        steps: dict[R2StepId, R2StepRecord] = {
            step["step_id"]: R2StepRecord(
                step_id=step["step_id"],
                status=step["status"],
                error_type=step.get("error_type"),
                retryable=step.get("retryable"),
            )
            for step in row[R2_RUN_STEPS_TABLE]
        }
        output = row.get("output")
        return R2RunRecord(
            run_id=str(row["run_id"]),
            user_id=str(row["user_id"]),
            r1_run_id=str(row["r1_run_id"]),
            status=row["status"],
            state=load_state(row["state"]),
            completed_step=row.get("completed_step"),
            attempts=int(row.get("attempts") or 0),
            retryable=bool(row.get("retryable")),
            updated_at=str(row["updated_at"]),
            output=load_output(output) if output is not None else None,
            failure_stage=row.get("failure_stage"),
            steps=steps,
        )

    async def get_finished_output(self, run_id: str, user_id: str) -> AmenitySearchOutput | None:
        """R2's handoff for R3, or None unless the run is this user's and `finished`."""
        rows = await self._execute(
            "get_finished_output",
            self._client.table(R2_RUNS_TABLE)
            .select("output")
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .eq("status", "finished")
            .limit(1),
        )
        if not rows or rows[0].get("output") is None:
            return None
        return load_output(rows[0]["output"])

    # ---- step rows ---------------------------------------------------------------------------

    async def insert_step(self, run_id: str, step_id: R2StepId, result: Any) -> bool:
        """Record a completed step. False when the row already exists (another execution)."""
        try:
            await self._execute(
                "insert_step",
                self._client.table(R2_RUN_STEPS_TABLE).insert(
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

    async def complete_claimed_step(self, run_id: str, step_id: R2StepId, result: Any) -> bool:
        """Move the retried step from `started` to `completed` with its output."""
        rows = await self._execute(
            "complete_claimed_step",
            self._client.table(R2_RUN_STEPS_TABLE)
            .update({"status": "completed", "output": dump_step_output(step_id, result)})
            .eq("run_id", run_id)
            .eq("step_id", step_id)
            .eq("status", "started"),
        )
        return len(rows) == 1

    async def claim_failed_step(self, run_id: str, step_id: R2StepId) -> bool:
        """Move the failed step to `started` and clear its error, before the retry runs it."""
        rows = await self._execute(
            "claim_failed_step",
            self._client.table(R2_RUN_STEPS_TABLE)
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
        step_id: R2StepId,
        *,
        error_type: str,
        message: str,
        retryable: bool,
        claimed: bool,
    ) -> bool:
        """Record the step's failure: a new row, or `started → failed` for a claimed step.

        False when the row could not be written (a duplicate insert, or a claimed row that moved).
        """
        values = {
            "status": "failed",
            "error_type": error_type,
            "error_message": message,
            "retryable": retryable,
        }
        table = self._client.table(R2_RUN_STEPS_TABLE)
        if claimed:
            rows = await self._execute(
                "save_step_failed",
                table.update(values)
                .eq("run_id", run_id)
                .eq("step_id", step_id)
                .eq("status", "started"),
            )
            return len(rows) == 1
        try:
            await self._execute(
                "save_step_failed",
                table.insert({"run_id": run_id, "step_id": step_id, **values}),
                conflict_ok=True,
            )
        except _StepConflict:
            return False
        return True

    # ---- shared ------------------------------------------------------------------------------

    @staticmethod
    def _fenced(query: Any, run_id: str, user_id: str, attempts: int) -> Any:
        """Match only this user's row while `running` at this execution's attempts (the fence)."""
        return (
            query.eq("run_id", run_id)
            .eq("user_id", user_id)
            .eq("status", "running")
            .eq("attempts", attempts)
        )

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
                    "event": "r2_run.store_error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": operation,
                    "error_class": type(exc).__name__,
                    "detail": str(exc),
                }
            )
        )


class _StepConflict(Exception):
    """Internal: an insert hit an existing step row (unique violation)."""
