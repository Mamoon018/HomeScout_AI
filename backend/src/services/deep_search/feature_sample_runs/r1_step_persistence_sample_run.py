"""Manual, stage-by-stage run of R1 Step Persistence: retry a run that failed at its last step.

Not a test: it asserts nothing and writes nothing to Supabase or to disk. It seeds one run as the
earlier R1 steps would have left it (seven completed step rows saved through the real step codec,
and a failed, retryable `metric_definition` row), so no earlier mechanism is re-run. Rows live in
an in-memory holder with the store's method names; every payload round-trips through the real
`dump_step_output` / `load_step_output`. Then it drives the real `R1RunCoordinator.retry_run`:
claim the run and the failed step, replay the seven saved steps with no LLM call, make the one
live `metric_definition` call, save it, finish the run. Last, `get_run` rebuilds the finished run
from its rows alone and its plans are compared with the retry's result.

From `backend/`:
    python -m src.services.deep_search.feature_sample_runs.r1_step_persistence_sample_run
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import (
    R1_STAGE_ERRORS,
    CheckpointMissingError,
    R1RunFailedError,
    RunConflictError,
    StateVersionMismatchError,
)
from src.services.deep_search.feature_schemas.schemas import (
    R1_STEP_ORDER,
    ClarificationAnswer,
    ClarificationResult,
    DepthAssignmentResult,
    ExtractedRequirements,
    FlagResolutionResult,
    InferredCategoriesResult,
    R1RunRecord,
    R1StepRecord,
    TaxonomyMappingResult,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator
from src.services.deep_search.r1_run_store import (
    R1_WORKFLOW_VERSION,
    dump_step_output,
    load_step_output,
)
from src.services.deep_search.requirement_interpretation import (
    LLM_PROVIDER_ATTEMPT_EVENT,
    LLM_PROVIDER_RAW_BODY_EVENT,
    create_requirement_interpretation,
)

_RULE = "=" * 78
_RUN_ID = "6f1c2a4e-0000-4000-8000-00000000a001"
_USER_ID = "6f1c2a4e-0000-4000-8000-0000000000b1"

# A new case (not a prompt worked pair, not another sample runner's case): a single father who
# starts early shifts at a bakery, with a daughter learning to swim and a diabetic cat.
_RAW_INPUT = (
    "I am a single father and I start work at a bakery at five most mornings, so I shop and "
    "run errands either very early or late in the evening. My daughter is seven and has just "
    "started swimming lessons twice a week after school, so a pool with lessons for children "
    "that we can reach easily matters a lot. I also need somewhere for my daughter after "
    "school on the two days I finish late, ideally somewhere supervised and calm where she "
    "can read or do homework. Our cat is old and diabetic, so a vet who knows how to manage "
    "insulin for cats should be close by. We do not own a car and use buses or walk, and I "
    "would like a supermarket that is open before six in the morning near home."
)

_EXTRACTED = ExtractedRequirements.model_validate(
    {
        "explicit_categories": [
            {"category_id": 0, "name": "supermarket", "characteristics": ["open before six"]},
            {
                "category_id": 1,
                "name": "pool with lessons for children",
                "characteristics": ["twice a week", "easy to reach"],
            },
            {
                "category_id": 2,
                "name": "somewhere for my daughter after school",
                "characteristics": ["supervised", "calm", "can read or do homework"],
            },
            {
                "category_id": 3,
                "name": "vet",
                "characteristics": ["manages insulin for diabetic cats", "close by"],
            },
        ],
        "ambiguity_flags": [
            {
                "phrase": "somewhere for my daughter after school",
                "target": "category",
                "category": None,
                "characteristic": None,
                "category_id": 2,
            }
        ],
        "persona_facts": [
            "single father",
            "starts work at five in the morning",
            "daughter aged seven",
            "owns an old diabetic cat",
            "no car; uses buses or walks",
        ],
    }
)
_MAPPING = TaxonomyMappingResult.model_validate(
    {
        "resolved_categories": [
            {"taxonomy_node": "supermarket", "category_id": 0},
            {"taxonomy_node": "swimming_pool", "category_id": 1},
            {"taxonomy_node": "veterinary_care", "category_id": 3},
        ],
        "unmapped_category_ids": [2],
    }
)
_QUESTIONS = ClarificationResult.model_validate(
    {
        "questions": [
            {
                "category_id": 2,
                "category": "somewhere for my daughter after school",
                "question": "For your daughter after school, which place is closest to what you mean?",
                "options": [
                    "a public library with a children's section",
                    "a community centre with an after-school club",
                    "a sports club with supervised sessions",
                    "an art studio with children's classes",
                    "other",
                ],
            }
        ]
    }
)
_ANSWERS = [ClarificationAnswer(category_id=2, option=1)]
_FLAGS = FlagResolutionResult.model_validate(
    {
        "resolved_categories": [
            {"taxonomy_node": "library", "category_id": 2, "provenance": "confident"}
        ]
    }
)
_INFERENCE = InferredCategoriesResult.model_validate(
    {
        "inferred_categories": [
            {
                "taxonomy_node": "laundry",
                "reasoning": "a single parent with early shifts and no car has little time for laundry",
            }
        ]
    }
)
_DEPTHS = DepthAssignmentResult.model_validate(
    {
        "assignments": [
            {"category_id": 0, "depth": "operating_details"},
            {"category_id": 1, "depth": "specific_attributes"},
            {"category_id": 2, "depth": "operating_details"},
            {"category_id": 3, "depth": "specific_attributes"},
            {"category_id": 4, "depth": "basic_profile"},
        ]
    }
)

_SEEDED_STEPS: dict[str, Any] = {
    "extraction": _EXTRACTED,
    "taxonomy_mapping": _MAPPING,
    "clarification_questions": _QUESTIONS,
    "clarification_answers": _ANSWERS,
    "flag_resolution": _FLAGS,
    "category_inference": _INFERENCE,
    "depth_assignment": _DEPTHS,
}

# Execute stages whose calls the replay must NOT make (their steps are saved).
_REPLAYED_STAGES = (
    "execute_and_validate",
    "execute_taxonomy_mapping",
    "execute_clarification_questions",
    "execute_flag_resolution",
    "execute_category_inference",
    "execute_depth_assignment",
)


class _MemoryRunRows:
    """The two run tables in memory, with `R1RunStore`'s method names and its codec."""

    def __init__(self) -> None:
        self.run: dict = {}
        self.steps: dict[str, dict] = {}
        self.writes: list[str] = []

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def seed(self) -> None:
        self.run = {
            "run_id": _RUN_ID,
            "user_id": _USER_ID,
            "workflow_version": R1_WORKFLOW_VERSION,
            "raw_input": _RAW_INPUT,
            "status": "failed",
            "attempts": 0,
            "updated_at": self._now(),
        }
        for step_id, result in _SEEDED_STEPS.items():
            self.steps[step_id] = {
                "step_id": step_id,
                "status": "completed",
                "output": json.loads(json.dumps(dump_step_output(step_id, result))),
            }
        self.steps["metric_definition"] = {
            "step_id": "metric_definition",
            "status": "failed",
            "error_type": "MetricDefinitionProviderError",
            "error_message": "seeded: no provider answered on the first attempt",
            "retryable": True,
        }

    def _owned(self, run_id: str, user_id: str) -> bool:
        return self.run.get("run_id") == run_id and self.run.get("user_id") == user_id

    async def set_status(self, run_id, user_id, *, to, expected) -> bool:
        if not self._owned(run_id, user_id) or self.run["status"] != expected:
            return False
        self.run.update(status=to, updated_at=self._now())
        self.writes.append(f"r1_runs: status {expected} -> {to}")
        return True

    async def claim_retry(self, run_id, user_id, *, expected_attempts) -> bool:
        if (not self._owned(run_id, user_id) or self.run["status"] != "failed"
                or self.run["attempts"] != expected_attempts):
            return False
        self.run.update(status="running", attempts=expected_attempts + 1, updated_at=self._now())
        self.writes.append(f"r1_runs: claim_retry, attempts {expected_attempts} -> {expected_attempts + 1}")
        return True

    async def claim_failed_step(self, run_id, step_id) -> bool:
        row = self.steps.get(step_id)
        if row is None or row["status"] != "failed":
            return False
        self.steps[step_id] = {"step_id": step_id, "status": "started"}
        self.writes.append(f"r1_run_steps[{step_id}]: failed -> started")
        return True

    async def insert_step(self, run_id, step_id, result) -> bool:
        if step_id in self.steps:
            return False
        self.steps[step_id] = {
            "step_id": step_id,
            "status": "completed",
            "output": json.loads(json.dumps(dump_step_output(step_id, result))),
        }
        self.writes.append(f"r1_run_steps[{step_id}]: inserted completed")
        return True

    async def complete_claimed_step(self, run_id, step_id, result) -> bool:
        row = self.steps.get(step_id)
        if row is None or row["status"] != "started":
            return False
        self.steps[step_id] = {
            "step_id": step_id,
            "status": "completed",
            "output": json.loads(json.dumps(dump_step_output(step_id, result))),
        }
        self.writes.append(f"r1_run_steps[{step_id}]: started -> completed")
        return True

    async def save_step_failed(self, run_id, step_id, *, error_type, message, retryable, claimed) -> None:
        self.steps[step_id] = {
            "step_id": step_id,
            "status": "failed",
            "error_type": error_type,
            "error_message": message,
            "retryable": retryable,
        }
        self.writes.append(f"r1_run_steps[{step_id}]: failed ({error_type}, retryable={retryable})")

    async def load_run(self, run_id, user_id) -> R1RunRecord | None:
        if not self._owned(run_id, user_id):
            return None
        steps = {
            step_id: R1StepRecord(
                step_id=step_id,
                status=row["status"],
                output=load_step_output(step_id, row["output"]) if row.get("output") else None,
                error_type=row.get("error_type"),
                error_message=row.get("error_message"),
                retryable=row.get("retryable"),
            )
            for step_id, row in self.steps.items()
        }
        return R1RunRecord(
            run_id=self.run["run_id"],
            user_id=self.run["user_id"],
            status=self.run["status"],
            raw_input=self.run["raw_input"],
            attempts=self.run["attempts"],
            updated_at=self.run["updated_at"],
            steps=steps,
        )


class _RecordCollector(logging.Handler):
    """Keeps the service's structured records so this script can print the attempt trail."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass

    def events(self, *names: str) -> list[dict]:
        return [record for record in self.records if record.get("event") in names]


async def run_sample() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    rows = _MemoryRunRows()
    rows.seed()
    interpretation = create_requirement_interpretation(settings)
    coordinator = R1RunCoordinator(interpretation, rows, stale_after_seconds=180.0)
    try:
        _section("SEEDED RUN ROW (r1_runs)")
        print(json.dumps({k: v for k, v in rows.run.items() if k != "raw_input"}, indent=2))
        print(f"raw_input words: {len(_RAW_INPUT.split())}")
        _section("SEEDED STEP ROWS (r1_run_steps, in run order)")
        for step_id in R1_STEP_ORDER:
            row = rows.steps.get(step_id)
            if row is None:
                print(f"{step_id:<24} (no row)")
                continue
            size = len(json.dumps(row["output"])) if row.get("output") else 0
            detail = f"{size} chars" if size else f"{row.get('error_type')} retryable={row.get('retryable')}"
            print(f"{step_id:<24} {row['status']:<10} {detail}")

        view = await coordinator.retry_run(_USER_ID, _RUN_ID)

        _section("RETRY CLAIM AND WRITES (in order)")
        for line in rows.writes:
            print(line)

        _section("REPLAY - PROVIDER ATTEMPTS FOR SAVED STEPS (must be 0)")
        replayed = [
            attempt for attempt in collector.events(LLM_PROVIDER_ATTEMPT_EVENT)
            if attempt.get("stage") in _REPLAYED_STAGES
        ]
        print(f"attempts: {len(replayed)}")
        loaded = [r for r in collector.events("r1_run.loaded")]
        if loaded:
            print(f"completed steps at load: {loaded[0].get('completed_steps')}")
            print(f"failed step at load:     {loaded[0].get('failed_step')}")

        _section("LIVE STEP - metric_definition PROVIDER ATTEMPTS")
        _print_attempts(collector, "execute_metric_definition")

        _section("SAVED CHECKPOINT ROW - metric_definition")
        row = rows.steps["metric_definition"]
        print(f"status: {row['status']}")
        print(f"schema_version: {row['output']['schema_version']}")
        print(f"json size: {len(json.dumps(row['output']))} chars")
        for saved in collector.events("r1_step.saved"):
            print(f"r1_step.saved: step={saved['step_id']} path={saved['path']}")

        _section("RUN STATUS AFTER RETRY")
        print(f"view status: {view.status}   row status: {rows.run['status']}   attempts: {rows.run['attempts']}")

        calls_before_read = len(collector.events(LLM_PROVIDER_ATTEMPT_EVENT))
        status_view = await coordinator.get_run(_USER_ID, _RUN_ID)
        calls_during_read = len(collector.events(LLM_PROVIDER_ATTEMPT_EVENT)) - calls_before_read

        _section("STATUS READ - REBUILT FROM ROWS ONLY")
        print(f"provider attempts during the status read: {calls_during_read}")
        retry_plans = [plan.__dict__ for plan in view.result or []]
        read_plans = [plan.__dict__ for plan in status_view.result or []]
        print(f"plans equal the retry's result: {json.dumps(retry_plans, default=str) == json.dumps(read_plans, default=str)}")
        _section("RESULT - CATEGORY METRIC PLANS")
        for plan in status_view.result or []:
            print(
                f"[{plan.category_id}] {plan.taxonomy_node} ({plan.depth}): "
                f"{len(plan.predefined_metrics)} pre-defined, "
                f"{[metric.label for metric in plan.specific_metrics]}"
            )
    finally:
        await interpretation.aclose()


def _print_attempts(collector: _RecordCollector, stage: str) -> None:
    for attempt in collector.events(LLM_PROVIDER_ATTEMPT_EVENT):
        if attempt.get("stage") != stage:
            continue
        line = f"{attempt['provider']} ({attempt['model']}): {attempt['outcome']}"
        detail = attempt.get("detail")
        print(f"{line} - {detail}" if detail else line)
    for answer in collector.events(LLM_PROVIDER_RAW_BODY_EVENT):
        if answer.get("stage") != stage:
            continue
        print(f"\nraw decoded body from {answer['provider']}:")
        print(json.dumps(answer["body"], indent=2, ensure_ascii=False))


def main() -> int:
    try:
        asyncio.run(run_sample())
    except (
        *R1_STAGE_ERRORS,
        R1RunFailedError,
        RunConflictError,
        CheckpointMissingError,
        StateVersionMismatchError,
    ) as exc:
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {getattr(exc, 'stage', 'unknown')}")
        print(f"message:   {exc}")
        return 1
    return 0


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


if __name__ == "__main__":
    sys.exit(main())
