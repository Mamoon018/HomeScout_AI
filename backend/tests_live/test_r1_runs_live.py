"""Live checks for R1 Step Persistence: real LLM responses (recorded once, replayed) and the real
`r1_runs` / `r1_run_steps` tables of the dev project.

Run from backend/:  pytest tests_live
Each full R1 run makes about 5-7 real LLM calls; replayed paths make none.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter
from supabase import acreate_client

from src.app.api.dependencies.deep_search import get_r1_run_coordinator
from src.app.api.dependencies.supabase import get_access_token_verifier
from src.app.main import app
from src.exceptions.deep_search import R1RunFailedError, RunConflictError, RunNotFoundError
from src.services.auth.session_cookies import ACCESS_TOKEN_COOKIE_POLICY
from src.services.deep_search.feature_schemas.schemas import (
    CLARIFICATION_QUESTIONS_SCHEMA_NAME,
    INFERRED_CATEGORIES_SCHEMA_NAME,
    TAXONOMY_MAPPING_SCHEMA_NAME,
    CategoryMetricPlan,
    ClarificationAnswer,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator
from src.services.deep_search.r1_run_store import R1RunStore, dump_state
from tests_live.conftest import (
    NO_PAUSE_REQUIREMENTS,
    PAUSE_REQUIREMENTS,
    make_verifier,
    mint_token,
    replay_interpretation,
)

_BASE = "/api/requirement-interpretation/runs"
_PLANS = TypeAdapter(list[CategoryMetricPlan])


def _first_option_answers(questions) -> list[ClarificationAnswer]:
    """Option 1 for every question, the same answers the recording used at the terminal."""
    answers = []
    for question in questions:
        description = "1" if question.options[0] == "other" else None
        answers.append(
            ClarificationAnswer(category_id=question.category_id, option=1, description=description)
        )
    return answers


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _plans(plans) -> list:
    return _PLANS.dump_python(list(plans), mode="json")


async def _run_row(db_client, run_id: str) -> dict:
    response = await db_client.table("r1_runs").select("*").eq("run_id", run_id).execute()
    return response.data[0]


async def _step_rows(db_client, run_id: str) -> dict[str, dict]:
    response = await db_client.table("r1_run_steps").select("*").eq("run_id", run_id).execute()
    return {row["step_id"]: row for row in response.data}


# ------------------------------------------------------------------------------- parity + replay


async def test_pause_parity_through_the_real_tables(pause_tape, db_client, users) -> None:
    tape, one_call_state = pause_tape
    r1, provider = replay_interpretation(tape)
    store = R1RunStore(db_client)
    coordinator = R1RunCoordinator(r1, store)

    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    assert view.status == "needs_answers"
    finished = await coordinator.submit_answers(
        users[0], view.run_id, _first_option_answers(view.questions)
    )

    assert finished.status == "finished"
    assert _same(_plans(finished.result), one_call_state["category_metric_plans"])
    assert provider.calls.count(CLARIFICATION_QUESTIONS_SCHEMA_NAME) == 1

    # V3: one embedded read returns the run and all its step rows.
    record = await store.load_run(view.run_id, users[0])
    assert record is not None and record.status == "finished"
    assert set(record.completed) == set(await _step_rows(db_client, view.run_id))
    assert "clarification_answers" in record.completed

    # V2: the status read rebuilds the finished run from its rows alone, with no LLM call.
    calls = len(provider.calls)
    status_view = await coordinator.get_run(users[0], view.run_id)
    assert len(provider.calls) == calls
    assert _same(_plans(status_view.result), one_call_state["category_metric_plans"])


async def test_no_pause_parity(no_pause_tape) -> None:
    tape, one_call_state = no_pause_tape
    r1, _ = replay_interpretation(tape)
    outcome = await r1.start(r1.intake_and_assemble_payload(NO_PAUSE_REQUIREMENTS))
    assert outcome.status == "finished"
    assert _same(dump_state(outcome.state), one_call_state)


# ------------------------------------------------------------------------------- store rows


async def test_step_rows_failure_and_retry_on_the_real_tables(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, provider = replay_interpretation(tape)
    coordinator = R1RunCoordinator(r1, R1RunStore(db_client))

    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    run = await _run_row(db_client, view.run_id)
    assert run["status"] == "needs_answers" and run["raw_input"] == PAUSE_REQUIREMENTS
    steps = await _step_rows(db_client, view.run_id)
    assert set(steps) == {"extraction", "taxonomy_mapping", "clarification_questions"}
    assert all(row["status"] == "completed" and row["output"]["schema_version"] == 1
               for row in steps.values())

    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.submit_answers(users[0], view.run_id, _first_option_answers(view.questions))
    assert caught.value.retryable is True
    steps = await _step_rows(db_client, view.run_id)
    assert steps["clarification_answers"]["status"] == "completed"
    failed = steps["category_inference"]
    assert failed["status"] == "failed" and failed["retryable"] is True
    assert failed["output"] is None and failed["error_type"]
    assert (await _run_row(db_client, view.run_id))["status"] == "failed"

    finished = await coordinator.retry_run(users[0], view.run_id)
    assert finished.status == "finished"
    assert (await _run_row(db_client, view.run_id))["attempts"] == 1
    steps = await _step_rows(db_client, view.run_id)
    assert steps["category_inference"]["status"] == "completed"
    assert steps["category_inference"]["error_type"] is None


async def test_user_id_filter_on_every_run_operation(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, _ = replay_interpretation(tape)
    store = R1RunStore(db_client)
    coordinator = R1RunCoordinator(r1, store)
    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)

    assert await store.load_run(view.run_id, users[1]) is None
    assert await store.set_status(view.run_id, users[1], to="failed", expected="needs_answers") is False
    assert await store.claim_retry(view.run_id, users[1], expected_attempts=0) is False
    assert (await _run_row(db_client, view.run_id))["status"] == "needs_answers"
    with pytest.raises(RunNotFoundError):
        await coordinator.submit_answers(users[1], view.run_id, _first_option_answers(view.questions))


async def test_completed_step_cannot_be_overwritten(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, _ = replay_interpretation(tape)
    store = R1RunStore(db_client)
    view = await R1RunCoordinator(r1, store).start_run(users[0], PAUSE_REQUIREMENTS)
    record = await store.load_run(view.run_id, users[0])
    extracted = record.completed["extraction"]

    # A second insert of the same step is refused by the primary key (the store says False).
    assert await store.insert_step(view.run_id, "extraction", extracted) is False
    # A conditional update of a completed row matches nothing.
    assert await store.complete_claimed_step(view.run_id, "extraction", extracted) is False
    assert await store.claim_failed_step(view.run_id, "extraction") is False


async def test_row_level_security_blocks_the_publishable_key(
    settings, pause_tape, db_client, users
) -> None:
    tape, _ = pause_tape
    r1, _ = replay_interpretation(tape)
    view = await R1RunCoordinator(r1, R1RunStore(db_client)).start_run(users[0], PAUSE_REQUIREMENTS)

    public = await acreate_client(settings.supabase_url, settings.supabase_publishable_key)
    try:
        for table in ("r1_runs", "r1_run_steps"):
            read = await public.table(table).select("*").eq("run_id", view.run_id).execute()
            assert read.data == []
        await public.table("r1_runs").update({"status": "finished"}).eq(
            "run_id", view.run_id
        ).execute()
    except Exception:
        pass  # a rejected write is as good as an ignored one
    finally:
        await public.postgrest.aclose()
    assert (await _run_row(db_client, view.run_id))["status"] == "needs_answers"


# ------------------------------------------------------------------------------- coordinator


async def test_start_failure_is_retryable_and_resumes(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, provider = replay_interpretation(tape)
    coordinator = R1RunCoordinator(r1, R1RunStore(db_client))
    provider.fail_once.add(TAXONOMY_MAPPING_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    assert caught.value.retryable is True
    steps = await _step_rows(db_client, caught.value.run_id)
    assert steps["extraction"]["status"] == "completed"
    assert steps["taxonomy_mapping"]["status"] == "failed"

    resumed = await coordinator.retry_run(users[0], caught.value.run_id)
    assert resumed.status == "needs_answers"


async def test_retry_parity_and_limit(pause_tape, db_client, users) -> None:
    tape, one_call_state = pause_tape
    r1, provider = replay_interpretation(tape)
    coordinator = R1RunCoordinator(r1, R1RunStore(db_client))
    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(users[0], view.run_id, _first_option_answers(view.questions))

    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.retry_run(users[0], view.run_id)
    assert caught.value.retryable is False
    assert (await _run_row(db_client, view.run_id))["attempts"] == 1
    assert (await _step_rows(db_client, view.run_id))["category_inference"]["retryable"] is False
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(users[0], view.run_id)

    # A retry that succeeds gives the same plans as the one-call run.
    r1_retry, retry_provider = replay_interpretation(tape)
    retrying = R1RunCoordinator(r1_retry, R1RunStore(db_client))
    second = await retrying.start_run(users[0], PAUSE_REQUIREMENTS)
    retry_provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await retrying.submit_answers(users[0], second.run_id, _first_option_answers(second.questions))
    finished = await retrying.retry_run(users[0], second.run_id)
    assert _same(_plans(finished.result), one_call_state["category_metric_plans"])


async def test_restart_between_steps(pause_tape, db_client, users) -> None:
    tape, one_call_state = pause_tape
    r1_first, _ = replay_interpretation(tape)
    view = await R1RunCoordinator(r1_first, R1RunStore(db_client)).start_run(
        users[0], PAUSE_REQUIREMENTS
    )

    # Brand-new R1, coordinator and store objects; only the rows in the run tables are shared.
    r1_second, _ = replay_interpretation(tape)
    finished = await R1RunCoordinator(r1_second, R1RunStore(db_client)).submit_answers(
        users[0], view.run_id, _first_option_answers(view.questions)
    )
    assert _same(_plans(finished.result), one_call_state["category_metric_plans"])


# ------------------------------------------------------------------------------- HTTP


async def test_http_flow_status_codes_and_ownership(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, _ = replay_interpretation(tape)
    coordinator = R1RunCoordinator(r1, R1RunStore(db_client))
    app.dependency_overrides[get_access_token_verifier] = make_verifier
    app.dependency_overrides[get_r1_run_coordinator] = lambda: coordinator
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anonymous:
            assert (await anonymous.post(_BASE, json={"requirements": "x"})).status_code == 401

        async with AsyncClient(transport=transport, base_url="https://test") as client:
            client.cookies.set(ACCESS_TOKEN_COOKIE_POLICY.name, mint_token(users[0]))
            assert (await client.post(_BASE, json={"requirements": "too short"})).status_code == 422
            started = await client.post(_BASE, json={"requirements": PAUSE_REQUIREMENTS})
            assert started.status_code == 201 and started.json()["status"] == "needs_answers"
            run_id = started.json()["run_id"]
            questions = started.json()["questions"]

            async with AsyncClient(transport=transport, base_url="https://test") as other:
                other.cookies.set(ACCESS_TOKEN_COOKIE_POLICY.name, mint_token(users[1]))
                assert (await other.get(f"{_BASE}/{run_id}")).status_code == 404

            assert (await client.get(f"{_BASE}/{run_id}")).json()["status"] == "needs_answers"
            answers = [
                {"category_id": q["category_id"], "option": 1}
                | ({"description": "1"} if q["options"][0] == "other" else {})
                for q in questions
            ]
            answered = await client.post(
                f"{_BASE}/{run_id}/clarification-answers", json={"answers": answers}
            )
            assert answered.status_code == 200 and answered.json()["status"] == "finished"
            assert answered.json()["result"]
            assert (await client.get(f"{_BASE}/{run_id}")).json()["result"] == answered.json()["result"]
            again = await client.post(
                f"{_BASE}/{run_id}/clarification-answers", json={"answers": answers}
            )
            assert again.status_code == 409
            assert (await client.post(f"{_BASE}/{run_id}/retry")).status_code == 409
    finally:
        app.dependency_overrides.clear()
