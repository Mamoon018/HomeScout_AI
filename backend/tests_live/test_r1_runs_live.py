"""C6 live checks for C1-C5: real LLM responses (recorded once, replayed), the real `r1_runs` table.

Run from backend/:  pytest tests_live
Each full R1 run makes about 5-7 real LLM calls; replayed paths make none.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
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
    ClarificationAnswer,
)
from src.services.deep_search.r1_run_coordinator import R1RunCoordinator
from src.services.deep_search.r1_run_store import R1RunStore, dump_state, load_state
from tests_live.conftest import (
    NO_PAUSE_REQUIREMENTS,
    PAUSE_REQUIREMENTS,
    make_verifier,
    mint_token,
    replay_interpretation,
)

_BASE = "/api/requirement-interpretation/runs"


def _first_option_answers(questions) -> list[ClarificationAnswer]:
    """Option 1 for every question, the same answers the recording used at the terminal."""
    answers = []
    for question in questions:
        description = "1" if question.options[0] == "other" else None
        answers.append(
            ClarificationAnswer(category_id=question.category_id, option=1, description=description)
        )
    return answers


def _same(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


async def _row(db_client, run_id: str) -> dict:
    response = await db_client.table("r1_runs").select("*").eq("run_id", run_id).execute()
    return response.data[0]


# ------------------------------------------------------------------------------------------- C1


async def test_pause_parity_through_the_real_table(pause_tape, db_client, users) -> None:
    tape, one_call_state = pause_tape
    r1, provider = replay_interpretation(tape)
    coordinator = R1RunCoordinator(r1, R1RunStore(db_client))

    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    assert view.status == "needs_answers"
    finished = await coordinator.submit_answers(
        users[0], view.run_id, _first_option_answers(view.questions)
    )

    assert finished.status == "finished"
    assert _same((await _row(db_client, view.run_id))["state"], one_call_state)
    assert provider.calls.count(CLARIFICATION_QUESTIONS_SCHEMA_NAME) == 1
    assert load_state(one_call_state).category_resolution_passes == 2


async def test_no_pause_parity(no_pause_tape) -> None:
    tape, one_call_state = no_pause_tape
    r1, _ = replay_interpretation(tape)
    outcome = await r1.start(r1.intake_and_assemble_payload(NO_PAUSE_REQUIREMENTS))
    assert outcome.status == "finished"
    assert _same(dump_state(outcome.state), one_call_state)


# ------------------------------------------------------------------------------------------- C3


async def test_store_transitions_failed_keeps_state_and_finished_output(
    pause_tape, db_client, users
) -> None:
    tape, _ = pause_tape
    r1, provider = replay_interpretation(tape)
    store = R1RunStore(db_client)
    coordinator = R1RunCoordinator(r1, store)

    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    paused = await _row(db_client, view.run_id)
    assert paused["status"] == "needs_answers" and paused["output"] is None
    assert await store.get_finished_output(view.run_id, users[0]) is None

    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(users[0], view.run_id, _first_option_answers(view.questions))
    failed = await _row(db_client, view.run_id)
    assert failed["status"] == "failed" and failed["retryable"] is True
    saved = load_state(failed["state"])
    assert saved.user_responses and saved.category_resolution_passes == 1

    provider.rewind()
    finished = await coordinator.retry_run(users[0], view.run_id)
    assert finished.status == "finished"
    row = await _row(db_client, view.run_id)
    assert row["attempts"] == 1
    output = await store.get_finished_output(view.run_id, users[0])
    assert output is not None and output == finished.result


async def test_user_id_filter_on_every_operation(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, _ = replay_interpretation(tape)
    store = R1RunStore(db_client)
    coordinator = R1RunCoordinator(r1, store)
    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)

    assert await store.load_run(view.run_id, users[1]) is None
    assert await store.get_finished_output(view.run_id, users[1]) is None
    await store.save_as_failed(view.run_id, users[1], stage="x", message="x", retryable=True)
    assert (await _row(db_client, view.run_id))["status"] == "needs_answers"
    with pytest.raises(RunNotFoundError):
        await coordinator.submit_answers(users[1], view.run_id, _first_option_answers(view.questions))


async def test_row_level_security_blocks_the_publishable_key(
    settings, pause_tape, db_client, users
) -> None:
    tape, _ = pause_tape
    r1, _ = replay_interpretation(tape)
    view = await R1RunCoordinator(r1, R1RunStore(db_client)).start_run(users[0], PAUSE_REQUIREMENTS)

    public = await acreate_client(settings.supabase_url, settings.supabase_publishable_key)
    try:
        read = await public.table("r1_runs").select("*").eq("run_id", view.run_id).execute()
        assert read.data == []
        await public.table("r1_runs").update({"status": "finished"}).eq(
            "run_id", view.run_id
        ).execute()
    except Exception:
        pass  # a rejected write is as good as an ignored one
    finally:
        await public.postgrest.aclose()
    assert (await _row(db_client, view.run_id))["status"] == "needs_answers"


# ------------------------------------------------------------------------------------------- C4


async def test_start_failure_saves_failed_not_retryable(pause_tape, db_client, users) -> None:
    tape, _ = pause_tape
    r1, provider = replay_interpretation(tape)
    provider.fail_once.add(TAXONOMY_MAPPING_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await R1RunCoordinator(r1, R1RunStore(db_client)).start_run(users[0], PAUSE_REQUIREMENTS)
    row = await _row(db_client, caught.value.run_id)
    assert row["status"] == "failed" and row["retryable"] is False


async def test_retry_parity_and_limit(pause_tape, db_client, users) -> None:
    tape, one_call_state = pause_tape
    r1, provider = replay_interpretation(tape)
    coordinator = R1RunCoordinator(r1, R1RunStore(db_client))
    view = await coordinator.start_run(users[0], PAUSE_REQUIREMENTS)
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError):
        await coordinator.submit_answers(users[0], view.run_id, _first_option_answers(view.questions))

    provider.rewind()
    provider.fail_once.add(INFERRED_CATEGORIES_SCHEMA_NAME)
    with pytest.raises(R1RunFailedError) as caught:
        await coordinator.retry_run(users[0], view.run_id)
    assert caught.value.retryable is False
    row = await _row(db_client, view.run_id)
    assert row["attempts"] == 1 and row["retryable"] is False
    with pytest.raises(RunConflictError):
        await coordinator.retry_run(users[0], view.run_id)

    # A clean resume of a fresh run, replaying the same responses, equals the one-call state.
    r1_clean, _ = replay_interpretation(tape)
    clean = R1RunCoordinator(r1_clean, R1RunStore(db_client))
    clean_view = await clean.start_run(users[0], PAUSE_REQUIREMENTS)
    await clean.submit_answers(users[0], clean_view.run_id, _first_option_answers(clean_view.questions))
    assert _same((await _row(db_client, clean_view.run_id))["state"], one_call_state)


async def test_restart_between_steps(pause_tape, db_client, users) -> None:
    tape, one_call_state = pause_tape
    r1_first, _ = replay_interpretation(tape)
    view = await R1RunCoordinator(r1_first, R1RunStore(db_client)).start_run(
        users[0], PAUSE_REQUIREMENTS
    )

    # Brand-new R1, coordinator and store objects; only the row in r1_runs is shared.
    r1_second, _ = replay_interpretation(tape)
    await R1RunCoordinator(r1_second, R1RunStore(db_client)).submit_answers(
        users[0], view.run_id, _first_option_answers(view.questions)
    )
    assert _same((await _row(db_client, view.run_id))["state"], one_call_state)


# ------------------------------------------------------------------------------------------- C5


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
            again = await client.post(
                f"{_BASE}/{run_id}/clarification-answers", json={"answers": answers}
            )
            assert again.status_code == 409
            assert (await client.post(f"{_BASE}/{run_id}/retry")).status_code == 409
    finally:
        app.dependency_overrides.clear()
