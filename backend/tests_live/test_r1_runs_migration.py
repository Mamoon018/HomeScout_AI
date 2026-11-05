"""C6: the r1_runs migration is safe to run again, and no app code creates or alters the table.

Needs SUPABASE_DB_URL (direct Postgres URL of the dev project) and psycopg:
    pip install -r tests_live/requirements.txt
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = next((REPO_ROOT / "supabase" / "migrations").glob("*_create_r1_runs.sql"))
SRC = REPO_ROOT / "backend" / "src"

_EXPECTED_COLUMNS = {
    "run_id", "user_id", "status", "state", "output", "failure_stage", "failure_message",
    "retryable", "attempts", "created_at", "updated_at",
}


@pytest.fixture
def connection(live):
    psycopg = pytest.importorskip("psycopg", reason="psycopg is not installed")
    if not live.supabase_db_url:
        pytest.skip("SUPABASE_DB_URL is not set")
    with psycopg.connect(live.supabase_db_url, autocommit=True) as conn:
        yield conn


def test_migration_runs_twice_keeps_rows_and_one_table(connection, users) -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    connection.execute(sql)
    connection.execute(
        "insert into public.r1_runs (run_id, user_id, status) "
        "values (gen_random_uuid(), %s, 'failed') returning run_id",
        (users[0],),
    )
    try:
        before = connection.execute(
            "select run_id, status, updated_at from public.r1_runs where user_id = %s order by run_id",
            (users[0],),
        ).fetchall()

        connection.execute(sql)  # second run: no error

        after = connection.execute(
            "select run_id, status, updated_at from public.r1_runs where user_id = %s order by run_id",
            (users[0],),
        ).fetchall()
        assert after == before
        tables = connection.execute(
            "select count(*) from information_schema.tables "
            "where table_schema = 'public' and table_name = 'r1_runs'"
        ).fetchone()[0]
        assert tables == 1
        columns = {
            row[0]
            for row in connection.execute(
                "select column_name from information_schema.columns "
                "where table_schema = 'public' and table_name = 'r1_runs'"
            ).fetchall()
        }
        assert columns == _EXPECTED_COLUMNS
        rls = connection.execute(
            "select relrowsecurity from pg_class where oid = 'public.r1_runs'::regclass"
        ).fetchone()[0]
        assert rls is True
    finally:
        connection.execute("delete from public.r1_runs where user_id = %s", (users[0],))


def test_app_code_never_creates_or_alters_r1_runs() -> None:
    pattern = re.compile(r"(create|alter)\s+table[^;]*r1_runs", re.IGNORECASE)
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in SRC.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []
