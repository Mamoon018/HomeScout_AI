"""C2 + C3: the R1 state's saved form and the `r1_runs` row operations.

This is the only module in the feature that knows about Supabase. Every read and write filters
on the verified `user_id` as well as the `run_id`, and every write is one single-row update, so
a run's status and data always change together.
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
    CategoryMetricPlan,
    R1RunRecord,
    RequirementInterpretationState,
)

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

R1_RUNS_TABLE = "r1_runs"

# Bump when RequirementInterpretationState changes shape. A saved state with another version is
# rejected (the run is failed and the customer starts again), never upgraded.
STATE_SCHEMA_VERSION = 1

_STATE_ADAPTER = TypeAdapter(RequirementInterpretationState)
_OUTPUT_ADAPTER = TypeAdapter(list[CategoryMetricPlan])

# Written at "Create a run". The row exists before R1 runs, and only three statuses exist, so it
# starts as a not-retryable failure; pausing or finishing overwrites it. A process that dies
# mid-start therefore leaves an honest "start again" row.
START_PLACEHOLDER_STAGE = "start"
START_PLACEHOLDER_MESSAGE = "The run did not finish its first step"


def dump_state(state: RequirementInterpretationState) -> dict:
    """The state as JSON-ready data inside a version envelope."""
    return {
        "version": STATE_SCHEMA_VERSION,
        "state": _STATE_ADAPTER.dump_python(state, mode="json"),
    }


def load_state(data: dict) -> RequirementInterpretationState:
    """Rebuild the typed state (int keys, frozen payload, Literals) after a version check."""
    found = data.get("version") if isinstance(data, dict) else None
    if found != STATE_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, STATE_SCHEMA_VERSION)
    return _STATE_ADAPTER.validate_python(data["state"])


def dump_output(plans: list[CategoryMetricPlan]) -> list:
    return _OUTPUT_ADAPTER.dump_python(plans, mode="json")


def load_output(data: list) -> list[CategoryMetricPlan]:
    return _OUTPUT_ADAPTER.validate_python(data)


class R1RunStore:
    """Create, load and update `r1_runs` rows through the async service-role client."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create_run(self, run_id: str, user_id: str) -> None:
        """Add the run's row after the input check and before the rest of R1 runs."""
        await self._execute(
            "create_run",
            self._table().insert(
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "status": "failed",
                    "failure_stage": START_PLACEHOLDER_STAGE,
                    "failure_message": START_PLACEHOLDER_MESSAGE,
                    "retryable": False,
                }
            ),
        )

    async def save_as_paused(
        self, run_id: str, user_id: str, state: RequirementInterpretationState
    ) -> None:
        """Write the state (with its questions) and set `needs_answers`."""
        await self._update(
            "save_as_paused",
            run_id,
            user_id,
            {
                "status": "needs_answers",
                "state": dump_state(state),
                "failure_stage": None,
                "failure_message": None,
                "retryable": False,
            },
        )

    async def save_answers(
        self,
        run_id: str,
        user_id: str,
        state: RequirementInterpretationState,
        *,
        expected_updated_at: str,
    ) -> bool:
        """Write the state with the answers before R1 resumes. False if the row moved since load."""
        rows = await self._update(
            "save_answers",
            run_id,
            user_id,
            {"state": dump_state(state)},
            extra_filters={"status": "needs_answers", "updated_at": expected_updated_at},
        )
        return len(rows) == 1

    async def save_as_finished(
        self, run_id: str, user_id: str, state: RequirementInterpretationState
    ) -> None:
        """Write the final state and R1's output, and set `finished`."""
        await self._update(
            "save_as_finished",
            run_id,
            user_id,
            {
                "status": "finished",
                "state": dump_state(state),
                "output": dump_output(state.category_metric_plans),
                "failure_stage": None,
                "failure_message": None,
                "retryable": False,
            },
        )

    async def mark_retry_started(
        self, run_id: str, user_id: str, *, expected_attempts: int
    ) -> bool:
        """Count the retry and close the retry door before it runs. False if another retry won."""
        rows = await self._update(
            "mark_retry_started",
            run_id,
            user_id,
            {"attempts": expected_attempts + 1, "retryable": False},
            extra_filters={"status": "failed", "attempts": expected_attempts, "retryable": True},
        )
        return len(rows) == 1

    async def save_as_failed(
        self,
        run_id: str,
        user_id: str,
        *,
        stage: str,
        message: str,
        retryable: bool,
    ) -> None:
        """Set `failed` with its stage, message and retryable flag. The saved state is untouched."""
        await self._update(
            "save_as_failed",
            run_id,
            user_id,
            {
                "status": "failed",
                "failure_stage": stage,
                "failure_message": message,
                "retryable": retryable,
            },
        )

    async def load_run(self, run_id: str, user_id: str) -> R1RunRecord | None:
        """Read the run by run_id and user_id. None when it does not exist for this user."""
        rows = await self._select("load_run", run_id, user_id, "*")
        if not rows:
            return None
        row = rows[0]
        state = load_state(row["state"]) if row.get("state") is not None else None
        output = load_output(row["output"]) if row.get("output") is not None else None
        return R1RunRecord(
            run_id=str(row["run_id"]),
            user_id=str(row["user_id"]),
            status=row["status"],
            state=state,
            output=output,
            failure_stage=row.get("failure_stage"),
            failure_message=row.get("failure_message"),
            retryable=bool(row.get("retryable")),
            attempts=int(row.get("attempts") or 0),
            updated_at=str(row["updated_at"]),
        )

    async def get_finished_output(
        self, run_id: str, user_id: str
    ) -> list[CategoryMetricPlan] | None:
        """R1's output for R2, or None unless the run is `finished`."""
        rows = await self._select(
            "get_finished_output", run_id, user_id, "output", extra_filters={"status": "finished"}
        )
        if not rows or rows[0].get("output") is None:
            return None
        return load_output(rows[0]["output"])

    def _table(self) -> Any:
        return self._client.table(R1_RUNS_TABLE)

    async def _update(
        self,
        operation: str,
        run_id: str,
        user_id: str,
        values: dict,
        *,
        extra_filters: dict | None = None,
    ) -> list[dict]:
        query = self._table().update(values).eq("run_id", run_id).eq("user_id", user_id)
        for column, value in (extra_filters or {}).items():
            query = query.eq(column, value)
        return await self._execute(operation, query)

    async def _select(
        self,
        operation: str,
        run_id: str,
        user_id: str,
        columns: str,
        *,
        extra_filters: dict | None = None,
    ) -> list[dict]:
        query = self._table().select(columns).eq("run_id", run_id).eq("user_id", user_id)
        for column, value in (extra_filters or {}).items():
            query = query.eq(column, value)
        return await self._execute(operation, query.limit(1))

    async def _execute(self, operation: str, query: Any) -> list[dict]:
        """Run one query; turn SDK and transport errors into one typed store error."""
        try:
            response = await query.execute()
        except (APIError, httpx.HTTPError) as exc:
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
            raise RunStoreError(f"r1_runs {operation} failed: {exc}", operation=operation) from exc
        return list(response.data or [])
