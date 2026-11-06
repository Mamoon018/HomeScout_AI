"""Fixture set for R1 over HTTP with step checkpoints (R1 Step Persistence). No live calls.

A fake StructuredLLMProvider returns recorded bodies queued per schema name (optionally raising on
a chosen call). An in-memory FakeRunStore stands in for `r1_runs` and `r1_run_steps`: it enforces
the (run_id, step_id) key, the conditional updates and the completed-immutable rule, and
round-trips every step payload through the real codec, so the coordinator sees exactly what the
database would give it back.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter

from src.app.api.dependencies.deep_search import get_r1_run_coordinator
from src.app.api.dependencies.supabase import get_access_token_verifier
from src.app.main import app
from src.clients.llm_provider import StructuredLLMCaller
from src.exceptions.deep_search import (
    ClarificationAnswerError,
    InputTooShortError,
    R1RunFailedError,
    RunConflictError,
    RunNotFoundError,
    StateVersionMismatchError,
)
from src.exceptions.llm import LLMProviderError
from src.services.auth.session_cookies import ACCESS_TOKEN_COOKIE_POLICY
from src.services.deep_search.feature_schemas.schemas import (
    CLARIFICATION_QUESTIONS_SCHEMA_NAME,
    DEPTH_ASSIGNMENT_SCHEMA_NAME,
    EXTRACTION_SCHEMA_NAME,
    FLAG_RESOLUTION_SCHEMA_NAME,
    INFERRED_CATEGORIES_SCHEMA_NAME,
    METRIC_DEFINITION_SCHEMA_NAME,
    TAXONOMY_MAPPING_SCHEMA_NAME,
    CategoryMetricPlan,
    ClarificationAnswer,
    ClarificationResult,
    R1RunRecord,
    R1StepRecord,
    RequirementInterpretationState,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator
from src.services.deep_search.r1_run_store import (
    R1_WORKFLOW_VERSION,
    dump_state,
    dump_step_output,
    load_step_output,
)
from src.services.deep_search.requirement_interpretation import UserRequirementsInterpretation
from tests.conftest import make_access_token_verifier, mint_access_token

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"

# 100+ English words so the real input check passes.
_REQUIREMENTS = (
    "We are a retired couple moving to a quieter part of town with our old spaniel. "
    "Our grandchildren stay with us most weekends, so we need somewhere for the grandkids "
    "to burn off energy that is safe and close by. I swim three mornings a week and my "
    "husband likes a gym with simple machines rather than a crowded studio, ideally one "
    "we can reach on foot. We do not drive much any more, so walking distance matters a "
    "lot for everything we visit regularly. We read a great deal and we volunteer on "
    "Saturdays at a charity shop. Our dog needs regular check ups because he is getting "
    "older and has stiff joints these days. We would also like the area to feel calm in "
    "the evenings, with good street lighting and benches along the way for resting."
)

_OPTIONS = [
    "a playground with swings and climbing frames",
    "a large park with open grass",
    "an indoor soft play centre",
    "a sports field for team games",
    "other",
]

_EXTRACTION_PAUSE = {
    "explicit_categories": [
        {"name": "gym with simple machines", "characteristics": ["walking distance"]},
        {"name": "somewhere for the grandkids", "characteristics": ["safe", "close by"]},
    ],
    "ambiguity_flags": [
        {
            "phrase": "somewhere for the grandkids",
            "target": "category",
            "category": None,
            "characteristic": None,
        }
    ],
    "persona_facts": ["retired couple", "owns an older dog", "does not drive much"],
}
_EXTRACTION_NO_PAUSE = {
    "explicit_categories": [
        {"name": "gym with simple machines", "characteristics": ["walking distance"]},
    ],
    "ambiguity_flags": [],
    "persona_facts": ["retired couple", "owns an older dog"],
}
_MAPPING_PAUSE = {
    "resolved_categories": [{"taxonomy_node": "gym", "category_id": 0}],
    "unmapped_category_ids": [1],
}
_MAPPING_NO_PAUSE = {
    "resolved_categories": [{"taxonomy_node": "gym", "category_id": 0}],
    "unmapped_category_ids": [],
}
_CLARIFICATION = {
    "questions": [
        {
            "category_id": 1,
            "category": "somewhere for the grandkids",
            "question": "When you say somewhere for the grandkids, which is closest?",
            "options": list(_OPTIONS),
        }
    ]
}
_FLAG_RESOLUTION = {
    "resolved_categories": [
        {"taxonomy_node": "playground", "category_id": 1, "provenance": "confident"}
    ]
}
_INFERENCE = {
    "inferred_categories": [
        {"taxonomy_node": "veterinary_care", "reasoning": "owns an older dog with stiff joints"}
    ]
}


def _metric(label: str) -> dict:
    return {
        "label": label,
        "question": "The customer asked for this category: is it usually quiet or busy?",
        "value_type": "enum",
        "unit": None,
        "enum_values": ["quiet", "mixed", "busy"],
        "evidence_class": "experiential",
        "resolution_source": {
            "web_target": "how busy the venue usually is during weekday mornings",
            "scrape_target": None,
            "review_target": "mentions of crowding or quiet hours in customer reviews",
        },
        "verification": "dominant sentiment across at least 5 reviews mentioning crowding",
        "null_policy": "unknown",
        "band": "operating_details",
    }


def _bodies(*, pause: bool) -> dict[str, list[dict]]:
    ids = [0, 1, 2] if pause else [0, 1]
    depth = {
        "assignments": [{"category_id": cid, "depth": "operating_details"} for cid in ids]
    }
    metrics = {"categories": [{"category_id": cid, "metrics": [_metric("Crowding")]} for cid in ids]}
    bodies = {
        EXTRACTION_SCHEMA_NAME: [_EXTRACTION_PAUSE if pause else _EXTRACTION_NO_PAUSE],
        TAXONOMY_MAPPING_SCHEMA_NAME: [_MAPPING_PAUSE if pause else _MAPPING_NO_PAUSE],
        INFERRED_CATEGORIES_SCHEMA_NAME: [_INFERENCE],
        DEPTH_ASSIGNMENT_SCHEMA_NAME: [depth],
        METRIC_DEFINITION_SCHEMA_NAME: [metrics],
    }
    if pause:
        bodies[CLARIFICATION_QUESTIONS_SCHEMA_NAME] = [_CLARIFICATION]
        bodies[FLAG_RESOLUTION_SCHEMA_NAME] = [_FLAG_RESOLUTION]
    return bodies


class FakeStructuredProvider:
    """Returns recorded bodies per schema name; `fail_once` raises on the next call of a schema."""

    name = "fake"
    model = "fake-model"

    def __init__(self, bodies_by_schema: dict[str, list[dict]]) -> None:
        self.calls: list[str] = []
        self.fail_once: set[str] = set()
        self._by_schema = {
            name: [copy.deepcopy(body) for body in queue] for name, queue in bodies_by_schema.items()
        }

    async def generate_structured(
        self, *, instruction: str, user_content: str, json_schema: dict, schema_name: str
    ) -> dict:
        self.calls.append(schema_name)
        if schema_name in self.fail_once:
            self.fail_once.discard(schema_name)
            raise LLMProviderError("injected failure", failure_class="availability")
        queue = self._by_schema.get(schema_name)
        if not queue:
            raise LLMProviderError(f"no recorded body left for {schema_name}")
        return queue.pop(0)

    def refill(self, bodies_by_schema: dict[str, list[dict]]) -> None:
        for name, queue in bodies_by_schema.items():
            self._by_schema.setdefault(name, []).extend(copy.deepcopy(body) for body in queue)

    async def aclose(self) -> None:
        return None



class FakeRunStore:
    """In-memory `r1_runs` + `r1_run_steps` with the store's method names and rules."""

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.steps: dict[str, dict[str, dict]] = {}
        self.step_history: list[tuple[str, str, str]] = []  # (run_id, step_id, new status)
        self.completed_update_attempts = 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _run(self, run_id: str, user_id: str) -> dict | None:
        row = self.runs.get(run_id)
        return row if row is not None and row["user_id"] == user_id else None

    def _step_update(self, run_id: str, step_id: str, expected: str) -> dict | None:
        row = self.steps.get(run_id, {}).get(step_id)
        if row is None:
            return None
        if row["status"] == "completed":
            self.completed_update_attempts += 1  # the database trigger would reject this
            return None
        return row if row["status"] == expected else None

    async def create_run(self, run_id: str, user_id: str, raw_input: str) -> None:
        self.runs[run_id] = {
            "run_id": run_id,
            "user_id": user_id,
            "workflow_version": R1_WORKFLOW_VERSION,
            "raw_input": raw_input,
            "status": "running",
            "attempts": 0,
            "updated_at": self._now(),
        }
        self.steps[run_id] = {}

    async def set_status(self, run_id, user_id, *, to, expected) -> bool:
        row = self._run(run_id, user_id)
        if row is None or row["status"] != expected:
            return False
        row.update(status=to, updated_at=self._now())
        return True

    async def claim_retry(self, run_id, user_id, *, expected_attempts) -> bool:
        row = self._run(run_id, user_id)
        if row is None or row["status"] != "failed" or row["attempts"] != expected_attempts:
            return False
        row.update(status="running", attempts=expected_attempts + 1, updated_at=self._now())
        return True

    async def insert_step(self, run_id, step_id, result) -> bool:
        if step_id in self.steps[run_id]:
            return False
        self.steps[run_id][step_id] = {
            "status": "completed",
            "output": json.loads(json.dumps(dump_step_output(step_id, result))),
        }
        self.step_history.append((run_id, step_id, "completed"))
        return True

    async def complete_claimed_step(self, run_id, step_id, result) -> bool:
        row = self._step_update(run_id, step_id, "started")
        if row is None:
            return False
        row.update(status="completed", output=json.loads(json.dumps(dump_step_output(step_id, result))))
        self.step_history.append((run_id, step_id, "completed"))
        return True

    async def claim_failed_step(self, run_id, step_id) -> bool:
        row = self._step_update(run_id, step_id, "failed")
        if row is None:
            return False
        row.update(status="started", error_type=None, error_message=None, retryable=None)
        self.step_history.append((run_id, step_id, "started"))
        return True

    async def save_step_failed(self, run_id, step_id, *, error_type, message, retryable, claimed) -> None:
        values = {"status": "failed", "error_type": error_type, "error_message": message,
                  "retryable": retryable}
        if claimed:
            row = self._step_update(run_id, step_id, "started")
            assert row is not None
            row.update(values)
        else:
            assert step_id not in self.steps[run_id]
            self.steps[run_id][step_id] = dict(values)
        self.step_history.append((run_id, step_id, "failed"))

    async def load_run(self, run_id, user_id) -> R1RunRecord | None:
        row = self._run(run_id, user_id)
        if row is None:
            return None
        if row["workflow_version"] != R1_WORKFLOW_VERSION:
            raise StateVersionMismatchError(row["workflow_version"], R1_WORKFLOW_VERSION)
        steps = {
            step_id: R1StepRecord(
                step_id=step_id,
                status=step["status"],
                output=load_step_output(step_id, step["output"]) if step.get("output") else None,
                error_type=step.get("error_type"),
                error_message=step.get("error_message"),
                retryable=step.get("retryable"),
            )
            for step_id, step in self.steps[run_id].items()
        }
        return R1RunRecord(
            run_id=row["run_id"],
            user_id=row["user_id"],
            status=row["status"],
            raw_input=row["raw_input"],
            attempts=row["attempts"],
            updated_at=row["updated_at"],
            steps=steps,
        )


def _interpretation(provider: FakeStructuredProvider) -> UserRequirementsInterpretation:
    return UserRequirementsInterpretation(StructuredLLMCaller([provider]))


def _coordinator(
    *, pause: bool = True, store: FakeRunStore | None = None
) -> tuple[R1RunCoordinator, FakeStructuredProvider, FakeRunStore]:
    provider = FakeStructuredProvider(_bodies(pause=pause))
    store = store or FakeRunStore()
    return R1RunCoordinator(_interpretation(provider), store), provider, store


def _queue_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(remaining))


def _json(state: RequirementInterpretationState) -> str:
    return json.dumps(dump_state(state), sort_keys=True)


_PLANS = TypeAdapter(list[CategoryMetricPlan])


def _plans_json(plans) -> str:
    return json.dumps(_PLANS.dump_python(list(plans), mode="json"), sort_keys=True)


_ANSWER = [ClarificationAnswer(category_id=1, option=1)]

_START_STEPS = {"extraction", "taxonomy_mapping", "clarification_questions"}
_AFTER_ANSWERS = {"clarification_answers", "flag_resolution", "category_inference",
                  "depth_assignment", "metric_definition"}


# ---------------------------------------------------------------------------------------------
# R1 entry points (decision logic unchanged; no checkpoints)
# ---------------------------------------------------------------------------------------------


async def test_pause_parity_with_one_call_interpret(monkeypatch: pytest.MonkeyPatch) -> None:
    _queue_input(monkeypatch, ["1"])
    one_call = await _interpretation(FakeStructuredProvider(_bodies(pause=True))).interpret(
        _REQUIREMENTS
    )

    r1 = _interpretation(FakeStructuredProvider(_bodies(pause=True)))
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
    assert outcome.status == "needs_answers"
    resumed = await r1.resume(copy.deepcopy(outcome.state), _ANSWER)

    assert _json(resumed) == _json(one_call)
    assert resumed.category_resolution_passes == 2


async def test_no_pause_parity_with_one_call_interpret() -> None:
    one_call = await _interpretation(FakeStructuredProvider(_bodies(pause=False))).interpret(
        _REQUIREMENTS
    )
    r1 = _interpretation(FakeStructuredProvider(_bodies(pause=False)))
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))

    assert outcome.status == "finished"
    assert outcome.state.clarification_questions == []
    assert _json(outcome.state) == _json(one_call)


async def test_web_and_terminal_answers_build_the_same_user_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for option, typed in ((2, None), (5, "a quiet garden with a sandpit")):
        r1 = _interpretation(FakeStructuredProvider(_bodies(pause=True)))
        outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
        web_state = copy.deepcopy(outcome.state)
        terminal_state = copy.deepcopy(outcome.state)

        r1.record_clarification_answers(
            web_state, [ClarificationAnswer(category_id=1, option=option, description=typed)]
        )
        _queue_input(monkeypatch, [str(option)] + ([typed] if typed else []))
        r1.collect_clarification_responses(
            terminal_state,
            ClarificationResult(questions=terminal_state.clarification_questions),
        )
        assert web_state.user_responses == terminal_state.user_responses
        expected = typed if typed else _OPTIONS[option - 1]
        assert web_state.user_responses[1].response == expected


@pytest.mark.parametrize(
    "answers",
    [
        [],
        [ClarificationAnswer(category_id=1, option=1), ClarificationAnswer(category_id=1, option=2)],
        [ClarificationAnswer(category_id=9, option=1)],
        [ClarificationAnswer(category_id=1, option=5)],
        [ClarificationAnswer(category_id=1, option=5, description="   ")],
        [ClarificationAnswer(category_id=1, option=2, description="extra")],
    ],
    ids=["missing", "duplicate", "unknown", "other_no_text", "other_blank", "text_on_non_other"],
)
async def test_invalid_answers_are_rejected_and_nothing_is_written(answers) -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    with pytest.raises(ClarificationAnswerError):
        await coordinator.submit_answers(USER_A, view.run_id, answers)
    assert set(store.steps[view.run_id]) == _START_STEPS
    assert store.runs[view.run_id]["status"] == "needs_answers"


async def test_resume_never_generates_questions_again() -> None:
    provider = FakeStructuredProvider(_bodies(pause=True))
    r1 = _interpretation(provider)
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
    await r1.resume(outcome.state, _ANSWER)

    assert provider.calls.count(CLARIFICATION_QUESTIONS_SCHEMA_NAME) == 1
    assert outcome.state.category_resolution_passes == 2


# ---------------------------------------------------------------------------------------------
# Step payload codec
# ---------------------------------------------------------------------------------------------


async def test_every_step_payload_round_trips_and_checks_its_version() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    rows = store.steps[view.run_id]
    assert set(rows) == _START_STEPS | _AFTER_ANSWERS
    for step_id, row in rows.items():
        result = load_step_output(step_id, row["output"])
        assert json.loads(json.dumps(dump_step_output(step_id, result))) == row["output"]

    with pytest.raises(StateVersionMismatchError):
        load_step_output("extraction", {"schema_version": 999, "data": {}})
    with pytest.raises(StateVersionMismatchError):
        load_step_output("extraction", {"data": {}})


# ---------------------------------------------------------------------------------------------
# Coordinator: checkpoints, replay, failure, retry, status
# ---------------------------------------------------------------------------------------------


async def test_input_failing_the_check_creates_no_row() -> None:
    coordinator, _, store = _coordinator()
    with pytest.raises(InputTooShortError):
        await coordinator.start_run(USER_A, "too short")
    assert store.runs == {}


async def test_start_saves_one_row_per_llm_step_then_pauses_or_finishes() -> None:
    coordinator, _, store = _coordinator(pause=True)
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert view.status == "needs_answers"
    assert [q.category_id for q in view.questions] == [1]
    run = store.runs[view.run_id]
    assert run["status"] == "needs_answers" and run["user_id"] == USER_A
    assert run["raw_input"] == _REQUIREMENTS
    assert set(store.steps[view.run_id]) == _START_STEPS
    assert all(row["status"] == "completed" for row in store.steps[view.run_id].values())

    coordinator, _, store = _coordinator(pause=False)
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert view.status == "finished" and view.result
    assert set(store.steps[view.run_id]) == {
        "extraction", "taxonomy_mapping", "category_inference", "depth_assignment",
        "metric_definition",
    }


async def test_answers_replay_saved_steps_without_llm_calls_and_match_interpret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _queue_input(monkeypatch, ["1"])
    one_call = await _interpretation(FakeStructuredProvider(_bodies(pause=True))).interpret(
        _REQUIREMENTS
    )
    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    calls_at_pause = len(provider.calls)
    finished = await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)

    after = provider.calls[calls_at_pause:]
    assert EXTRACTION_SCHEMA_NAME not in after
    assert TAXONOMY_MAPPING_SCHEMA_NAME not in after
    assert CLARIFICATION_QUESTIONS_SCHEMA_NAME not in after
    assert finished.status == "finished"
    assert _plans_json(finished.result) == _plans_json(one_call.category_metric_plans)
    assert store.runs[view.run_id]["status"] == "finished"


async def test_status_read_rebuilds_the_finished_run_with_no_llm_call() -> None:
    coordinator, provider, _ = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    finished = await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    calls = len(provider.calls)

    status_view = await coordinator.get_run(USER_A, view.run_id)
    assert len(provider.calls) == calls
    assert status_view.status == "finished"
    assert _plans_json(status_view.result) == _plans_json(finished.result)

    paused_coordinator, paused_provider, _ = _coordinator()
    paused = await paused_coordinator.start_run(USER_A, _REQUIREMENTS)
    calls = len(paused_provider.calls)
    paused_view = await paused_coordinator.get_run(USER_A, paused.run_id)
    assert len(paused_provider.calls) == calls
    assert paused_view.status == "needs_answers" and paused_view.questions == paused.questions


async def test_start_failure_is_retryable_and_retry_calls_only_the_remaining_steps() -> None:
    coordinator, provider, store = _coordinator(pause=False)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert caught.value.retryable is True and caught.value.provider_unavailable is True
    run_id = caught.value.run_id
    failed = store.steps[run_id]["category_inference"]
    assert failed["status"] == "failed" and failed["retryable"] is True
    assert store.runs[run_id]["status"] == "failed"

    calls_before = len(provider.calls)
    retried = await coordinator.retry_run(USER_A, run_id)
    assert retried.status == "finished"
    assert provider.calls[calls_before:] == [
        INFERRED_CATEGORIES_SCHEMA_NAME, DEPTH_ASSIGNMENT_SCHEMA_NAME, METRIC_DEFINITION_SCHEMA_NAME
    ]


async def test_extraction_failure_retry_reruns_from_the_saved_requirements() -> None:
    coordinator, provider, store = _coordinator(pause=False)
    provider.fail_once.add(EXTRACTION_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert caught.value.retryable is True
    assert store.steps[caught.value.run_id]["extraction"]["status"] == "failed"

    retried = await coordinator.retry_run(USER_A, caught.value.run_id)
    assert retried.status == "finished"
    assert store.steps[caught.value.run_id]["extraction"]["status"] == "completed"


async def test_retried_step_updates_its_own_row() -> None:
    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    await coordinator.retry_run(USER_A, view.run_id)

    history = [status for run, step, status in store.step_history
               if run == view.run_id and step == "category_inference"]
    assert history == ["failed", "started", "completed"]
    assert store.completed_update_attempts == 0


async def test_retry_after_answers_gives_the_same_result_as_a_run_that_never_failed() -> None:
    clean, _, _ = _coordinator()
    clean_view = await clean.start_run(USER_A, _REQUIREMENTS)
    clean_finished = await clean.submit_answers(USER_A, clean_view.run_id, _ANSWER)

    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    assert caught.value.retryable is True
    assert store.steps[view.run_id]["flag_resolution"]["status"] == "completed"

    calls_before = len(provider.calls)
    retried = await coordinator.retry_run(USER_A, view.run_id)
    assert FLAG_RESOLUTION_SCHEMA_NAME not in provider.calls[calls_before:]
    assert retried.status == "finished"
    assert store.runs[view.run_id]["attempts"] == 1
    assert _plans_json(retried.result) == _plans_json(clean_finished.result)


async def test_retry_limit_is_one() -> None:
    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.retry_run(USER_A, view.run_id)

    assert caught.value.retryable is False
    assert store.runs[view.run_id]["attempts"] == 1
    assert store.steps[view.run_id]["category_inference"]["retryable"] is False
    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, view.run_id)
    assert conflict.value.retryable is False
    assert (await coordinator.get_run(USER_A, view.run_id)).retryable is False


async def test_a_second_concurrent_retry_loses_the_claim() -> None:
    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)

    assert await store.claim_retry(view.run_id, USER_A, expected_attempts=0) is True
    assert await store.claim_retry(view.run_id, USER_A, expected_attempts=0) is False
    store.runs[view.run_id]["status"] = "failed"  # back to the state the second request loaded
    store.runs[view.run_id]["attempts"] = 0
    original = store.claim_retry

    async def lost_claim(run_id, user_id, *, expected_attempts):
        await original(run_id, user_id, expected_attempts=expected_attempts)  # the other request wins
        return False

    store.claim_retry = lost_claim
    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, view.run_id)
    assert "Another retry" in str(conflict.value)


async def test_retry_refused_when_the_run_has_not_failed() -> None:
    coordinator, _, _ = _coordinator()
    paused = await coordinator.start_run(USER_A, _REQUIREMENTS)
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(USER_A, paused.run_id)


async def test_a_stuck_running_run_reads_as_failed_and_cannot_be_retried() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    run = store.runs[view.run_id]
    run["status"] = "running"

    young = await coordinator.get_run(USER_A, view.run_id)
    assert young.status == "running"

    run["updated_at"] = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    stuck = await coordinator.get_run(USER_A, view.run_id)
    assert stuck.status == "failed" and stuck.retryable is False
    assert run["status"] == "running"  # the read wrote nothing
    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, view.run_id)
    assert conflict.value.retryable is False


async def test_missing_checkpoint_reads_as_failed_and_blocks_answers() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    del store.steps[view.run_id]["clarification_questions"]

    status_view = await coordinator.get_run(USER_A, view.run_id)
    assert status_view.status == "failed" and status_view.retryable is False
    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)


async def test_version_mismatch_reads_as_failed_and_blocks_actions() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    store.runs[view.run_id]["workflow_version"] = R1_WORKFLOW_VERSION + 1

    status_view = await coordinator.get_run(USER_A, view.run_id)
    assert status_view.status == "failed" and status_view.retryable is False
    assert store.runs[view.run_id]["status"] == "needs_answers"  # the read wrote nothing
    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)

    store.runs[view.run_id]["workflow_version"] = R1_WORKFLOW_VERSION
    store.steps[view.run_id]["extraction"]["output"]["schema_version"] = 999
    assert (await coordinator.get_run(USER_A, view.run_id)).status == "failed"


async def test_answers_twice_and_other_users_runs() -> None:
    coordinator, _, _ = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    with pytest.raises(RunNotFoundError):
        await coordinator.submit_answers(USER_B, view.run_id, _ANSWER)
    with pytest.raises(RunNotFoundError):
        await coordinator.get_run(USER_B, view.run_id)
    with pytest.raises(RunNotFoundError):
        await coordinator.retry_run(USER_B, view.run_id)

    await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)


async def test_status_moved_while_answers_were_checked_is_a_conflict() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    original_load = store.load_run

    async def stale_load(run_id, user_id):
        record = await original_load(run_id, user_id)
        store.runs[run_id]["status"] = "running"  # another request moved the row after this load
        return record

    store.load_run = stale_load
    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    assert "clarification_answers" not in store.steps[view.run_id]


async def test_restart_between_steps_with_fresh_objects() -> None:
    store = FakeRunStore()
    first, _, _ = _coordinator(store=store)
    view = await first.start_run(USER_A, _REQUIREMENTS)

    second, _, _ = _coordinator(store=store)
    finished = await second.submit_answers(USER_A, view.run_id, _ANSWER)

    clean, _, _ = _coordinator()
    clean_view = await clean.start_run(USER_A, _REQUIREMENTS)
    clean_finished = await clean.submit_answers(USER_A, clean_view.run_id, _ANSWER)
    assert finished.status == "finished"
    assert _plans_json(finished.result) == _plans_json(clean_finished.result)


# ---------------------------------------------------------------------------------------------
# HTTP endpoints (routes -> controllers -> coordinator)
# ---------------------------------------------------------------------------------------------

_BASE = "/api/requirement-interpretation/runs"


@pytest.fixture
def http_coordinator():
    coordinator, provider, store = _coordinator()
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    app.dependency_overrides[get_r1_run_coordinator] = lambda: coordinator
    yield coordinator, provider, store
    app.dependency_overrides.clear()


async def _client(user_id: str | None = USER_A) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    if user_id is not None:
        client.cookies.set(ACCESS_TOKEN_COOKIE_POLICY.name, mint_access_token(subject=user_id))
    return client


async def test_every_endpoint_requires_login(http_coordinator) -> None:
    run = "33333333-3333-4333-8333-333333333333"
    async with await _client(None) as client:
        responses = [
            await client.post(_BASE, json={"requirements": _REQUIREMENTS}),
            await client.post(f"{_BASE}/{run}/clarification-answers", json={"answers": []}),
            await client.post(f"{_BASE}/{run}/retry"),
            await client.get(f"{_BASE}/{run}"),
        ]
    assert [r.status_code for r in responses] == [401, 401, 401, 401]


async def test_http_happy_path_and_status_codes(http_coordinator) -> None:
    async with await _client() as client:
        assert (await client.post(_BASE, json={"requirements": "too short"})).status_code == 422

        started = await client.post(_BASE, json={"requirements": _REQUIREMENTS})
        assert started.status_code == 201
        body = started.json()
        assert body["status"] == "needs_answers" and body["questions"][0]["category_id"] == 1
        run_id = body["run_id"]

        status_view = await client.get(f"{_BASE}/{run_id}")
        assert status_view.status_code == 200 and status_view.json()["status"] == "needs_answers"

        bad = await client.post(
            f"{_BASE}/{run_id}/clarification-answers",
            json={"answers": [{"category_id": 1, "option": 9}]},
        )
        assert bad.status_code == 422
        wrong = await client.post(
            f"{_BASE}/{run_id}/clarification-answers",
            json={"answers": [{"category_id": 7, "option": 1}]},
        )
        assert wrong.status_code == 422

        answered = await client.post(
            f"{_BASE}/{run_id}/clarification-answers",
            json={"answers": [{"category_id": 1, "option": 1}]},
        )
        assert answered.status_code == 200
        result = answered.json()
        assert result["status"] == "finished"
        assert {plan["category_id"] for plan in result["result"]} == {0, 1, 2}

        finished_view = await client.get(f"{_BASE}/{run_id}")
        assert finished_view.json()["result"] == result["result"]

        again = await client.post(
            f"{_BASE}/{run_id}/clarification-answers",
            json={"answers": [{"category_id": 1, "option": 1}]},
        )
        assert again.status_code == 409
        assert (await client.post(f"{_BASE}/{run_id}/retry")).status_code == 409

    async with await _client(USER_B) as other:
        assert (await other.get(f"{_BASE}/{run_id}")).status_code == 404
        assert (await other.post(f"{_BASE}/{run_id}/retry")).status_code == 404


async def test_http_failure_bodies_carry_retryable(http_coordinator) -> None:
    _, provider, _ = http_coordinator
    async with await _client() as client:
        run_id = (await client.post(_BASE, json={"requirements": _REQUIREMENTS})).json()["run_id"]
        provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
        failed = await client.post(
            f"{_BASE}/{run_id}/clarification-answers",
            json={"answers": [{"category_id": 1, "option": 1}]},
        )
        assert failed.status_code == 503
        assert failed.json() == {
            "error": "Requirement interpretation failed",
            "run_id": run_id,
            "status": "failed",
            "retryable": True,
        }
        status_view = (await client.get(f"{_BASE}/{run_id}")).json()
        assert status_view == {"run_id": run_id, "status": "failed", "retryable": True}

        retried = await client.post(f"{_BASE}/{run_id}/retry")
        assert retried.status_code == 200 and retried.json()["status"] == "finished"

        provider.refill(_bodies(pause=True))
        provider.fail_once.add(EXTRACTION_SCHEMA_NAME)
        start_failed = await client.post(_BASE, json={"requirements": _REQUIREMENTS})
        assert start_failed.status_code == 503
        assert start_failed.json()["retryable"] is True  # D5: the requirements are saved


async def test_endpoints_answer_503_when_runs_are_not_configured() -> None:
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    try:
        async with await _client() as client:
            response = await client.get(f"{_BASE}/33333333-3333-4333-8333-333333333333")
        assert response.status_code == 503
        assert response.json() == {"error": "Requirement interpretation is not available"}
    finally:
        app.dependency_overrides.clear()
