"""Fixture set for R1 over HTTP (C1, C2, C4, C5). No live calls.

A fake StructuredLLMProvider returns recorded bodies queued per schema name (optionally raising on
a chosen call), and an in-memory FakeRunStore stands in for `r1_runs`. It round-trips every saved
state through JSON, so the coordinator sees exactly what the database would give it back.
"""

from __future__ import annotations

import copy
import itertools
import json

import pytest
from httpx import ASGITransport, AsyncClient

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
    ClarificationAnswer,
    ClarificationResult,
    R1RunRecord,
    RequirementInterpretationState,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator
from src.services.deep_search.r1_run_store import (
    START_PLACEHOLDER_STAGE,
    dump_output,
    dump_state,
    load_output,
    load_state,
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
    """In-memory `r1_runs` with the store's method names; states round-trip through JSON."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self._clock = itertools.count(1)

    def _touch(self, row: dict) -> None:
        row["updated_at"] = f"t{next(self._clock)}"

    def _row(self, run_id: str, user_id: str) -> dict | None:
        row = self.rows.get(run_id)
        return row if row is not None and row["user_id"] == user_id else None

    async def create_run(self, run_id: str, user_id: str) -> None:
        row = {
            "run_id": run_id,
            "user_id": user_id,
            "status": "failed",
            "state": None,
            "output": None,
            "failure_stage": START_PLACEHOLDER_STAGE,
            "failure_message": "placeholder",
            "retryable": False,
            "attempts": 0,
        }
        self._touch(row)
        self.rows[run_id] = row

    async def save_as_paused(self, run_id, user_id, state) -> None:
        row = self._row(run_id, user_id)
        row.update(status="needs_answers", state=json.loads(json.dumps(dump_state(state))),
                   failure_stage=None, failure_message=None, retryable=False)
        self._touch(row)

    async def save_answers(self, run_id, user_id, state, *, expected_updated_at) -> bool:
        row = self._row(run_id, user_id)
        if row is None or row["status"] != "needs_answers" or row["updated_at"] != expected_updated_at:
            return False
        row["state"] = json.loads(json.dumps(dump_state(state)))
        self._touch(row)
        return True

    async def save_as_finished(self, run_id, user_id, state) -> None:
        row = self._row(run_id, user_id)
        row.update(status="finished", state=json.loads(json.dumps(dump_state(state))),
                   output=json.loads(json.dumps(dump_output(state.category_metric_plans))),
                   failure_stage=None, failure_message=None, retryable=False)
        self._touch(row)

    async def mark_retry_started(self, run_id, user_id, *, expected_attempts) -> bool:
        row = self._row(run_id, user_id)
        if (row is None or row["status"] != "failed" or not row["retryable"]
                or row["attempts"] != expected_attempts):
            return False
        row.update(attempts=expected_attempts + 1, retryable=False)
        self._touch(row)
        return True

    async def save_as_failed(self, run_id, user_id, *, stage, message, retryable) -> None:
        row = self._row(run_id, user_id)
        row.update(status="failed", failure_stage=stage, failure_message=message, retryable=retryable)
        self._touch(row)

    async def load_run(self, run_id, user_id) -> R1RunRecord | None:
        row = self._row(run_id, user_id)
        if row is None:
            return None
        return R1RunRecord(
            run_id=row["run_id"],
            user_id=row["user_id"],
            status=row["status"],
            state=load_state(row["state"]) if row["state"] is not None else None,
            output=load_output(row["output"]) if row["output"] is not None else None,
            failure_stage=row["failure_stage"],
            failure_message=row["failure_message"],
            retryable=row["retryable"],
            attempts=row["attempts"],
            updated_at=row["updated_at"],
        )


def _interpretation(provider: FakeStructuredProvider) -> UserRequirementsInterpretation:
    return UserRequirementsInterpretation(StructuredLLMCaller([provider]))


def _coordinator(*, pause: bool = True) -> tuple[R1RunCoordinator, FakeStructuredProvider, FakeRunStore]:
    provider = FakeStructuredProvider(_bodies(pause=pause))
    store = FakeRunStore()
    return R1RunCoordinator(_interpretation(provider), store), provider, store


def _queue_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(remaining))


def _json(state: RequirementInterpretationState) -> str:
    return json.dumps(dump_state(state), sort_keys=True)


_ANSWER = [ClarificationAnswer(category_id=1, option=1)]


# ---------------------------------------------------------------------------------------------
# C1: resumable entry points
# ---------------------------------------------------------------------------------------------


async def test_pause_parity_with_one_call_interpret(monkeypatch: pytest.MonkeyPatch) -> None:
    _queue_input(monkeypatch, ["1"])
    one_call = await _interpretation(FakeStructuredProvider(_bodies(pause=True))).interpret(
        _REQUIREMENTS
    )

    r1 = _interpretation(FakeStructuredProvider(_bodies(pause=True)))
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
    assert outcome.status == "needs_answers"
    saved = json.loads(json.dumps(dump_state(outcome.state)))
    resumed = await r1.resume(load_state(saved), _ANSWER)

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
        web_state = load_state(json.loads(json.dumps(dump_state(outcome.state))))
        terminal_state = load_state(json.loads(json.dumps(dump_state(outcome.state))))

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
    r1 = _interpretation(FakeStructuredProvider(_bodies(pause=True)))
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
    with pytest.raises(ClarificationAnswerError):
        r1.record_clarification_answers(outcome.state, answers)
    assert outcome.state.user_responses == {}


async def test_resume_never_generates_questions_again() -> None:
    provider = FakeStructuredProvider(_bodies(pause=True))
    r1 = _interpretation(provider)
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
    calls_at_pause = list(provider.calls)
    await r1.resume(outcome.state, _ANSWER)

    assert calls_at_pause.count(CLARIFICATION_QUESTIONS_SCHEMA_NAME) == 1
    assert provider.calls.count(CLARIFICATION_QUESTIONS_SCHEMA_NAME) == 1
    assert outcome.state.category_resolution_passes == 2


# ---------------------------------------------------------------------------------------------
# C2: state serialization
# ---------------------------------------------------------------------------------------------


async def test_paused_and_finished_states_round_trip_exactly() -> None:
    r1 = _interpretation(FakeStructuredProvider(_bodies(pause=True)))
    outcome = await r1.start(r1.intake_and_assemble_payload(_REQUIREMENTS))
    paused = load_state(json.loads(json.dumps(dump_state(outcome.state))))
    assert paused == outcome.state

    finished = await r1.resume(paused, _ANSWER)
    again = load_state(json.loads(json.dumps(dump_state(finished))))
    assert again == finished
    assert all(isinstance(key, int) for key in again.user_responses)
    assert again.resolved is not None and again.resolved.payload == again.payload


def test_version_mismatch_raises_typed_error() -> None:
    with pytest.raises(StateVersionMismatchError):
        load_state({"version": 999, "state": {}})
    with pytest.raises(StateVersionMismatchError):
        load_state({"state": {}})


# ---------------------------------------------------------------------------------------------
# C4: run coordinator
# ---------------------------------------------------------------------------------------------


async def test_input_failing_the_check_creates_no_row() -> None:
    coordinator, _, store = _coordinator()
    with pytest.raises(InputTooShortError):
        await coordinator.start_run(USER_A, "too short")
    assert store.rows == {}


async def test_start_pauses_with_questions_or_finishes() -> None:
    coordinator, _, store = _coordinator(pause=True)
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert view.status == "needs_answers"
    assert [q.category_id for q in view.questions] == [1]
    row = store.rows[view.run_id]
    assert row["status"] == "needs_answers" and row["user_id"] == USER_A
    assert row["state"]["state"]["clarification_questions"][0]["category_id"] == 1

    coordinator, _, store = _coordinator(pause=False)
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert view.status == "finished" and view.result
    assert store.rows[view.run_id]["output"] is not None


async def test_start_failure_is_saved_as_failed_not_retryable() -> None:
    coordinator, provider, store = _coordinator()
    provider.fail_once.add(TAXONOMY_MAPPING_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.start_run(USER_A, _REQUIREMENTS)
    assert caught.value.provider_unavailable is True
    row = store.rows[caught.value.run_id]
    assert row["status"] == "failed" and row["retryable"] is False
    assert row["failure_stage"] == "execute_taxonomy_mapping"


async def test_resume_failure_keeps_answers_and_clean_state_and_is_retryable() -> None:
    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)

    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    assert caught.value.retryable is True
    row = store.rows[view.run_id]
    assert row["status"] == "failed" and row["retryable"] is True
    saved = load_state(row["state"])
    assert 1 in saved.user_responses
    assert saved.category_resolution_passes == 1


async def test_retry_gives_the_same_final_state_as_a_resume_that_never_failed() -> None:
    clean, _, clean_store = _coordinator()
    clean_view = await clean.start_run(USER_A, _REQUIREMENTS)
    await clean.submit_answers(USER_A, clean_view.run_id, _ANSWER)

    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    # The failed attempt consumed the flag-resolution body; queue the same one for the retry.
    provider.refill({FLAG_RESOLUTION_SCHEMA_NAME: [_FLAG_RESOLUTION]})
    retried = await coordinator.retry_run(USER_A, view.run_id)

    assert retried.status == "finished"
    assert store.rows[view.run_id]["attempts"] == 1
    assert (
        json.dumps(store.rows[view.run_id]["state"], sort_keys=True)
        == json.dumps(clean_store.rows[clean_view.run_id]["state"], sort_keys=True)
    )


async def test_retry_limit_is_one() -> None:
    coordinator, provider, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    provider.refill({FLAG_RESOLUTION_SCHEMA_NAME: [_FLAG_RESOLUTION]})
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.retry_run(USER_A, view.run_id)

    assert caught.value.retryable is False
    row = store.rows[view.run_id]
    assert row["attempts"] == 1 and row["retryable"] is False
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(USER_A, view.run_id)


async def test_retry_refused_when_not_failed_or_not_retryable() -> None:
    coordinator, _, _ = _coordinator()
    paused = await coordinator.start_run(USER_A, _REQUIREMENTS)
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(USER_A, paused.run_id)

    coordinator, provider, _ = _coordinator()
    provider.fail_once.add(EXTRACTION_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.start_run(USER_A, _REQUIREMENTS)
    with pytest.raises(RunConflictError) as conflict:
        await coordinator.retry_run(USER_A, caught.value.run_id)
    assert conflict.value.retryable is False


async def test_version_mismatch_fails_the_run_on_answers_and_reads_as_failed_on_get() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    store.rows[view.run_id]["state"]["version"] = 0

    status_view = await coordinator.get_run(USER_A, view.run_id)
    assert status_view.status == "failed" and status_view.retryable is False
    assert store.rows[view.run_id]["status"] == "needs_answers"  # the read wrote nothing

    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    row = store.rows[view.run_id]
    assert row["status"] == "failed" and row["retryable"] is False


async def test_answers_twice_and_other_users_runs() -> None:
    coordinator, _, _ = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    with pytest.raises(RunNotFoundError):
        await coordinator.submit_answers(USER_B, view.run_id, _ANSWER)
    with pytest.raises(RunNotFoundError):
        await coordinator.get_run(USER_B, view.run_id)

    await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)
    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)


async def test_lost_compare_and_set_on_answers_is_a_conflict() -> None:
    coordinator, _, store = _coordinator()
    view = await coordinator.start_run(USER_A, _REQUIREMENTS)
    original_load = store.load_run

    async def stale_load(run_id, user_id):
        record = await original_load(run_id, user_id)
        store._touch(store.rows[run_id])  # another request moved the row after this load
        return record

    store.load_run = stale_load
    with pytest.raises(RunConflictError):
        await coordinator.submit_answers(USER_A, view.run_id, _ANSWER)


async def test_restart_between_steps_with_fresh_objects() -> None:
    store = FakeRunStore()
    first = R1RunCoordinator(_interpretation(FakeStructuredProvider(_bodies(pause=True))), store)
    view = await first.start_run(USER_A, _REQUIREMENTS)

    second = R1RunCoordinator(_interpretation(FakeStructuredProvider(_bodies(pause=True))), store)
    finished = await second.submit_answers(USER_A, view.run_id, _ANSWER)

    clean, _, clean_store = _coordinator()
    clean_view = await clean.start_run(USER_A, _REQUIREMENTS)
    await clean.submit_answers(USER_A, clean_view.run_id, _ANSWER)
    assert finished.status == "finished"
    assert store.rows[view.run_id]["state"] == clean_store.rows[clean_view.run_id]["state"]


# ---------------------------------------------------------------------------------------------
# C5: HTTP endpoints (routes -> controllers -> coordinator)
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

        provider.refill({FLAG_RESOLUTION_SCHEMA_NAME: [_FLAG_RESOLUTION]})
        retried = await client.post(f"{_BASE}/{run_id}/retry")
        assert retried.status_code == 200 and retried.json()["status"] == "finished"

        provider.refill(_bodies(pause=True))
        provider.fail_once.add(EXTRACTION_SCHEMA_NAME)
        start_failed = await client.post(_BASE, json={"requirements": _REQUIREMENTS})
        assert start_failed.status_code == 503
        assert start_failed.json()["retryable"] is False


async def test_endpoints_answer_503_when_runs_are_not_configured() -> None:
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    try:
        async with await _client() as client:
            response = await client.get(f"{_BASE}/33333333-3333-4333-8333-333333333333")
        assert response.status_code == 503
        assert response.json() == {"error": "Requirement interpretation is not available"}
    finally:
        app.dependency_overrides.clear()
