"""The R1 run migrations are safe to run again, keep the old runs read-only, and no app code
creates or alters the run tables.

Needs SUPABASE_DB_URL (direct Postgres URL of the dev project) and psycopg:
    pip install -r tests_live/requirements.txt
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from postgrest.exceptions import APIError

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "backend" / "supabase" / "migrations"
# Applied in filename order: the old whole-state table first, then the two-table schema.
RUN_MIGRATIONS = [
    next(MIGRATIONS.glob("*_create_r1_runs.sql")),
    next(MIGRATIONS.glob("*_create_r1_run_steps.sql")),
]
SRC = REPO_ROOT / "backend" / "src"

_RUN_COLUMNS = {
    "run_id", "user_id", "workflow_version", "raw_input", "status", "attempts",
    "created_at", "updated_at",
}
_STEP_COLUMNS = {
    "run_id", "step_id", "status", "output", "error_type", "error_message", "retryable",
    "created_at",
}


@pytest.fixture
def connection(live):
    psycopg = pytest.importorskip("psycopg", reason="psycopg is not installed")
    if not live.supabase_db_url:
        pytest.skip("SUPABASE_DB_URL is not set")
    with psycopg.connect(live.supabase_db_url, autocommit=True) as conn:
        yield conn


def _apply(connection) -> None:
    for migration in RUN_MIGRATIONS:
        connection.execute(migration.read_text(encoding="utf-8"))


def _columns(connection, table: str) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'public' and table_name = %s",
            (table,),
        ).fetchall()
    }


def test_migrations_run_twice_keep_rows_and_build_both_tables(connection, users) -> None:
    _apply(connection)
    run_id = connection.execute(
        "insert into public.r1_runs (run_id, user_id, workflow_version, raw_input, status) "
        "values (gen_random_uuid(), %s, 1, 'text', 'running') returning run_id",
        (users[0],),
    ).fetchone()[0]
    connection.execute(
        "insert into public.r1_run_steps (run_id, step_id, status, output) "
        "values (%s, 'extraction', 'completed', '{\"schema_version\": 1, \"data\": {}}')",
        (run_id,),
    )
    try:
        before = connection.execute(
            "select run_id, status, updated_at from public.r1_runs where user_id = %s",
            (users[0],),
        ).fetchall()

        _apply(connection)  # second run: no error, nothing changes

        after = connection.execute(
            "select run_id, status, updated_at from public.r1_runs where user_id = %s",
            (users[0],),
        ).fetchall()
        assert after == before
        assert _columns(connection, "r1_runs") == _RUN_COLUMNS
        assert _columns(connection, "r1_run_steps") == _STEP_COLUMNS
        assert "state" in _columns(connection, "r1_runs_legacy")
        for table in ("r1_runs", "r1_run_steps"):
            rls = connection.execute(
                "select relrowsecurity from pg_class where oid = %s::regclass", (f"public.{table}",)
            ).fetchone()[0]
            assert rls is True
    finally:
        connection.execute("delete from public.r1_runs where user_id = %s", (users[0],))


def test_completed_step_is_immutable(connection, users) -> None:
    psycopg = pytest.importorskip("psycopg")
    _apply(connection)
    run_id = connection.execute(
        "insert into public.r1_runs (run_id, user_id, workflow_version, raw_input, status) "
        "values (gen_random_uuid(), %s, 1, 'text', 'running') returning run_id",
        (users[0],),
    ).fetchone()[0]
    try:
        connection.execute(
            "insert into public.r1_run_steps (run_id, step_id, status, output) "
            "values (%s, 'extraction', 'completed', '{\"schema_version\": 1, \"data\": {}}')",
            (run_id,),
        )
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                "update public.r1_run_steps set status = 'failed', error_type = 'x', "
                "retryable = false, output = null where run_id = %s",
                (run_id,),
            )
    finally:
        connection.execute("delete from public.r1_runs where user_id = %s", (users[0],))


async def test_legacy_table_refuses_service_role_writes(connection, db_client) -> None:
    _apply(connection)
    with pytest.raises(APIError):
        await db_client.table("r1_runs_legacy").update({"status": "finished"}).eq(
            "status", "never-matches"
        ).execute()


def test_app_code_never_creates_or_alters_the_run_tables() -> None:
    pattern = re.compile(r"(create|alter)\s+table[^;]*r1_run", re.IGNORECASE)
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in SRC.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []
