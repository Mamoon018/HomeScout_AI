"""The R3 run tables: `r3_runs` (one row per run) and `r3_run_steps` (one record per step).

This is the only R3 module that knows about Supabase. Run reads and writes filter on the verified
`user_id` as well as the `run_id`. Every write after the run is created is fenced: it matches only
while the row is `running` at the writing execution's `attempts`, so an older execution that wakes
up late changes nothing (R3-C6). "Save as failed" never touches `state` or `completed_step`, so a
retry resumes from the last good checkpoint. Step writes filter on `run_id` only: the steps table
has no `user_id`, and every step write follows a matched run write for this user (R3-C5).

R3's state holds four dicts keyed by `(category_id, place_id)` and, inside every resolution
record, an evidence store whose lookup table is keyed by a tuple too. JSON can't key by a tuple,
so this module writes each tuple-keyed dict as a list of `{category_id, place_id, value}` entries
in insertion order, and rebuilds the evidence lookup table from its items on load (R3-C4).
"""

import dataclasses
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
    AmenityMetricsSet,
    AmenityResolutionRecord,
    CanonicalPlace,
    CategoryMetricPlan,
    DiscoverySearchRecord,
    OfficialGateRecord,
    PredefinedMetricsRecord,
    R3RunRecord,
    R3StepId,
    R3StepRecord,
    SpecificMetricResolutionState,
    SpecificMetricsRecord,
    WebsiteSearchResult,
)
from src.services.deep_search.r2_run_store import stale_cutoff_filter

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

R3_RUNS_TABLE = "r3_runs"
R3_RUN_STEPS_TABLE = "r3_run_steps"

# Bump when `SpecificMetricResolutionState` or the output changes shape. A run saved under another
# version is not resumed: it is failed, not retryable (R3-C4).
R3_STATE_SCHEMA_VERSION = 1

# Bump when a step record's payload changes shape. Checked on every load.
R3_STEP_SCHEMA_VERSION = 1

# Postgres "unique_violation": the step row already exists, so another execution owns it.
_UNIQUE_VIOLATION = "23505"

# The state fields with ordinary keys (int / str), each through its own adapter.
_PLAIN_ADAPTERS: dict[str, TypeAdapter] = {
    "category_metric_plans": TypeAdapter(list[CategoryMetricPlan]),
    "discovered_places": TypeAdapter(dict[int, dict[str, CanonicalPlace]]),
    "predefined_records": TypeAdapter(dict[int, dict[str, PredefinedMetricsRecord]]),
    "specific_records": TypeAdapter(dict[int, dict[str, SpecificMetricsRecord]]),
    "amenity_records": TypeAdapter(AmenityMetricsSet | None),
}

# The state fields keyed by `(category_id, place_id)`: one adapter for the value type each.
_KEYED_ADAPTERS: dict[str, TypeAdapter] = {
    "website_search_results": TypeAdapter(WebsiteSearchResult),
    "discovery_search_results": TypeAdapter(DiscoverySearchRecord),
    "official_gate_results": TypeAdapter(OfficialGateRecord),
    "resolution_results": TypeAdapter(AmenityResolutionRecord),
}

# STEP 3's three result dicts: the `discovery_batch` step row's payload.
_STEP3_FIELDS = ("official_gate_results", "discovery_search_results", "website_search_results")

_RESOLUTION = "resolution_results"

# A state field the codec does not know would be dropped from every save without an error.
# Fail at import instead, so a new field is added here (and versioned) on purpose.
_STATE_FIELDS = {f.name for f in dataclasses.fields(SpecificMetricResolutionState)}
if _STATE_FIELDS != set(_PLAIN_ADAPTERS) | set(_KEYED_ADAPTERS):
    raise RuntimeError(
        "r3_run_store codec does not cover SpecificMetricResolutionState exactly: "
        f"{sorted(_STATE_FIELDS ^ (set(_PLAIN_ADAPTERS) | set(_KEYED_ADAPTERS)))}"
    )


# ---- codecs ------------------------------------------------------------------------------------


def _encode_keyed(field_name: str, mapping: dict[tuple[int, str], Any]) -> list[dict]:
    """A tuple-keyed dict as `{category_id, place_id, value}` entries, in insertion order."""
    adapter = _KEYED_ADAPTERS[field_name]
    entries = []
    for (category_id, place_id), value in mapping.items():
        data = adapter.dump_python(value, mode="json")
        if field_name == _RESOLUTION and data.get("phase1") is not None:
            # The evidence lookup table is keyed by a tuple and is rebuilt from `items` on load.
            data["phase1"]["metrics_source_content"]["_index"] = {}
        entries.append({"category_id": category_id, "place_id": place_id, "value": data})
    return entries


def _decode_keyed(field_name: str, entries: list[dict]) -> dict[tuple[int, str], Any]:
    """Rebuild a tuple-keyed dict from its entries, in the same order."""
    adapter = _KEYED_ADAPTERS[field_name]
    mapping: dict[tuple[int, str], Any] = {}
    for entry in entries:
        value = adapter.validate_python(entry["value"])
        if field_name == _RESOLUTION and value.phase1 is not None:
            content = value.phase1.metrics_source_content
            # Same objects as `items`, keyed as `MetricsSourceContent.record` keys them.
            content._index = {
                (item.source_kind, item.url, item.shaped_text): item for item in content.items
            }
        mapping[(int(entry["category_id"]), str(entry["place_id"]))] = value
    return mapping


def dump_state(state: SpecificMetricResolutionState) -> dict:
    """The R3 state as JSON-ready data inside a version envelope."""
    data: dict[str, Any] = {
        name: adapter.dump_python(getattr(state, name), mode="json")
        for name, adapter in _PLAIN_ADAPTERS.items()
    }
    for name in _KEYED_ADAPTERS:
        data[name] = _encode_keyed(name, getattr(state, name))
    return {"version": R3_STATE_SCHEMA_VERSION, "state": data}


def load_state(data: dict) -> SpecificMetricResolutionState:
    """Rebuild the typed state after a version check (tuple keys and lookup tables rebuilt)."""
    found = data.get("version") if isinstance(data, dict) else None
    if found != R3_STATE_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, R3_STATE_SCHEMA_VERSION)
    raw = data["state"]
    fields: dict[str, Any] = {
        name: adapter.validate_python(raw[name]) for name, adapter in _PLAIN_ADAPTERS.items()
    }
    for name in _KEYED_ADAPTERS:
        fields[name] = _decode_keyed(name, raw[name])
    return SpecificMetricResolutionState(**fields)


def dump_resolution_entries(results: dict[tuple[int, str], AmenityResolutionRecord]) -> list[dict]:
    """R3's result as plain JSON rows `{category_id, place_id, value}` (the status body)."""
    return _encode_keyed(_RESOLUTION, results)


def dump_output(results: dict[tuple[int, str], AmenityResolutionRecord]) -> dict:
    """R3's finished output (`resolution_results`) inside a version envelope."""
    return {"version": R3_STATE_SCHEMA_VERSION, "output": dump_resolution_entries(results)}


def load_output(data: dict) -> dict[tuple[int, str], AmenityResolutionRecord]:
    """Rebuild the typed output after a version check."""
    found = data.get("version") if isinstance(data, dict) else None
    if found != R3_STATE_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, R3_STATE_SCHEMA_VERSION)
    return _decode_keyed(_RESOLUTION, data["output"])


def dump_step_output(step_id: R3StepId, state: SpecificMetricResolutionState) -> dict:
    """One step's result in the step envelope: STEP 3's three dicts, or `resolution_results`."""
    if step_id == "discovery_batch":
        payload: Any = {name: _encode_keyed(name, getattr(state, name)) for name in _STEP3_FIELDS}
    else:
        payload = _encode_keyed(_RESOLUTION, state.resolution_results)
    return {"schema_version": R3_STEP_SCHEMA_VERSION, "data": payload}


def load_step_output(step_id: R3StepId, data: dict) -> Any:
    """Rebuild one step's typed result after a version check."""
    found = data.get("schema_version") if isinstance(data, dict) else None
    if found != R3_STEP_SCHEMA_VERSION:
        raise StateVersionMismatchError(found, R3_STEP_SCHEMA_VERSION)
    if step_id == "discovery_batch":
        return {name: _decode_keyed(name, data["data"][name]) for name in _STEP3_FIELDS}
    return _decode_keyed(_RESOLUTION, data["data"])


def state_chars(state: SpecificMetricResolutionState) -> int:
    """The saved state's JSON size, for the checkpoint / finish log lines (codec cost watch)."""
    return len(json.dumps(dump_state(state), ensure_ascii=False))


# ---- store -------------------------------------------------------------------------------------


class R3RunStore:
    """Create, load and update rows of `r3_runs` and `r3_run_steps` through the async client."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    # ---- run rows ----------------------------------------------------------------------------

    async def create_run(
        self, run_id: str, user_id: str, r2_run_id: str, state: SpecificMetricResolutionState
    ) -> None:
        """Add the run's row: `running`, attempts 0, no checkpoint yet, the initial state."""
        await self._execute(
            "create_run",
            self._client.table(R3_RUNS_TABLE).insert(
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "r2_run_id": r2_run_id,
                    "status": "running",
                    "state": dump_state(state),
                    "completed_step": None,
                    "retryable": False,
                    "attempts": 0,
                }
            ),
        )

    async def save_checkpoint(
        self, run_id: str, user_id: str, *, attempts: int, state: SpecificMetricResolutionState
    ) -> bool:
        """Write the state after a clean STEP 3. False when a newer execution owns the row."""
        rows = await self._execute(
            "save_checkpoint",
            self._fenced(
                self._client.table(R3_RUNS_TABLE).update(
                    {"state": dump_state(state), "completed_step": "discovery_batch"}
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
        state: SpecificMetricResolutionState,
        output: dict[tuple[int, str], AmenityResolutionRecord],
    ) -> bool:
        """Write the final state and output and set `finished` in one fenced update."""
        rows = await self._execute(
            "save_finished",
            self._fenced(
                self._client.table(R3_RUNS_TABLE).update(
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
                self._client.table(R3_RUNS_TABLE).update(
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
        """The single-execution guard: one update; only one request can match (R3-C6)."""
        rows = await self._execute(
            "claim_retry",
            self._client.table(R3_RUNS_TABLE)
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
            self._client.table(R3_RUNS_TABLE)
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

    async def load_run(self, run_id: str, user_id: str) -> R3RunRecord | None:
        """Read the run and its step rows in one request. None when it is not this user's run."""
        rows = await self._execute(
            "load_run",
            self._client.table(R3_RUNS_TABLE)
            .select(f"*, {R3_RUN_STEPS_TABLE}(step_id, status, error_type, retryable)")
            .eq("run_id", run_id)
            .eq("user_id", user_id)
            .limit(1),
        )
        if not rows:
            return None
        row = rows[0]
        if R3_RUN_STEPS_TABLE not in row or not isinstance(row[R3_RUN_STEPS_TABLE], list):
            # The embedded read did not return the steps. Fail loudly rather than read the run as
            # one with no step rows, which would insert duplicates on the next write.
            raise RunStoreError("r3_runs load_run did not return the run's steps", operation="load_run")
        steps: dict[R3StepId, R3StepRecord] = {
            step["step_id"]: R3StepRecord(
                step_id=step["step_id"],
                status=step["status"],
                error_type=step.get("error_type"),
                retryable=step.get("retryable"),
            )
            for step in row[R3_RUN_STEPS_TABLE]
        }
        output = row.get("output")
        return R3RunRecord(
            run_id=str(row["run_id"]),
            user_id=str(row["user_id"]),
            r2_run_id=str(row["r2_run_id"]),
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

    # ---- step rows ---------------------------------------------------------------------------

    async def insert_step(
        self, run_id: str, step_id: R3StepId, state: SpecificMetricResolutionState
    ) -> bool:
        """Record a completed step. False when the row already exists (another execution)."""
        return await self._insert_step_row(
            "insert_step",
            {
                "run_id": run_id,
                "step_id": step_id,
                "status": "completed",
                "output": dump_step_output(step_id, state),
            },
        )

    async def complete_claimed_step(
        self, run_id: str, step_id: R3StepId, state: SpecificMetricResolutionState
    ) -> bool:
        """Move the retried step from `started` to `completed` with its new output."""
        rows = await self._execute(
            "complete_claimed_step",
            self._client.table(R3_RUN_STEPS_TABLE)
            .update({"status": "completed", "output": dump_step_output(step_id, state)})
            .eq("run_id", run_id)
            .eq("step_id", step_id)
            .eq("status", "started"),
        )
        return len(rows) == 1

    async def save_step_degraded(
        self,
        run_id: str,
        step_id: R3StepId,
        state: SpecificMetricResolutionState,
        *,
        claimed: bool,
    ) -> bool:
        """Keep what a breaker-open step found: a new `degraded` row, or `started → degraded`."""
        values = {"status": "degraded", "output": dump_step_output(step_id, state)}
        if claimed:
            rows = await self._execute(
                "save_step_degraded",
                self._client.table(R3_RUN_STEPS_TABLE)
                .update(values)
                .eq("run_id", run_id)
                .eq("step_id", step_id)
                .eq("status", "started"),
            )
            return len(rows) == 1
        return await self._insert_step_row(
            "save_step_degraded", {"run_id": run_id, "step_id": step_id, **values}
        )

    async def save_step_failed(
        self,
        run_id: str,
        step_id: R3StepId,
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
        if claimed:
            rows = await self._execute(
                "save_step_failed",
                self._client.table(R3_RUN_STEPS_TABLE)
                .update(values)
                .eq("run_id", run_id)
                .eq("step_id", step_id)
                .eq("status", "started"),
            )
            return len(rows) == 1
        return await self._insert_step_row(
            "save_step_failed", {"run_id": run_id, "step_id": step_id, **values}
        )

    async def claim_step(self, run_id: str, step_id: R3StepId) -> bool:
        """Move a `failed` or `degraded` step to `started`, clearing its error and output."""
        rows = await self._execute(
            "claim_step",
            self._client.table(R3_RUN_STEPS_TABLE)
            .update(
                {
                    "status": "started",
                    "output": None,
                    "error_type": None,
                    "error_message": None,
                    "retryable": None,
                }
            )
            .eq("run_id", run_id)
            .eq("step_id", step_id)
            .in_("status", ["failed", "degraded"]),
        )
        return len(rows) == 1

    # ---- shared ------------------------------------------------------------------------------

    async def _insert_step_row(self, operation: str, values: dict) -> bool:
        """Insert one step row. False on a duplicate key (another execution owns the row)."""
        try:
            await self._execute(
                operation, self._client.table(R3_RUN_STEPS_TABLE).insert(values), conflict_ok=True
            )
        except _StepConflict:
            return False
        return True

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
                    "event": "r3_run.store_error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": operation,
                    "error_class": type(exc).__name__,
                    "detail": str(exc),
                }
            )
        )


class _StepConflict(Exception):
    """Internal: an insert hit an existing step row (unique violation)."""
