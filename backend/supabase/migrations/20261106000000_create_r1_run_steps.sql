-- R1 runs become two tables: one row per run (r1_runs) and one checkpoint per
-- non-reproducible step (r1_run_steps). See R1_Persistence_Schema_Design.md.
-- Safe to run again: every statement is a no-op when its object already exists.
-- Only the backend's service-role key reaches these tables (RLS on, no policies).

-- 1. Keep the old whole-state runs as a read-only legacy table (decision D3).
--    The rename runs only while the old-shape table (with a `state` column) is still
--    called r1_runs and no legacy table exists yet.
do $$
begin
  if to_regclass('public.r1_runs_legacy') is null
     and to_regclass('public.r1_runs') is not null
     and exists (select 1 from information_schema.columns
                 where table_schema = 'public' and table_name = 'r1_runs'
                   and column_name = 'state') then
    alter table public.r1_runs rename to r1_runs_legacy;
    -- Index names are unique per schema, so free the names the new table needs.
    alter table public.r1_runs_legacy rename constraint r1_runs_pkey to r1_runs_legacy_pkey;
    alter index public.r1_runs_user_id_idx rename to r1_runs_legacy_user_id_idx;
    drop trigger if exists r1_runs_set_updated_at on public.r1_runs_legacy;
  end if;
  -- Read-only: no role may write to it (grants apply even to the service role).
  if to_regclass('public.r1_runs_legacy') is not null then
    revoke insert, update, delete, truncate on public.r1_runs_legacy
      from anon, authenticated, service_role;
  end if;
end;
$$;

-- 2. R1 runs: one row per run, tied to the user who started it.
create table if not exists public.r1_runs (
  run_id           uuid primary key,
  user_id          uuid not null references auth.users (id) on delete cascade,
  -- The R1 workflow version that wrote this run; a mismatch means "start again".
  workflow_version integer not null check (workflow_version >= 1),
  -- The customer's requirements, stored as is (decision D2). Intake is recomputed from it.
  raw_input        text not null,
  status           text not null
                   check (status in ('running', 'needs_answers', 'finished', 'failed')),
  attempts         integer not null default 0 check (attempts >= 0),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists r1_runs_user_id_idx on public.r1_runs (user_id);

-- 3. R1 checkpoints: one row per non-reproducible step of a run.
create table if not exists public.r1_run_steps (
  run_id        uuid not null references public.r1_runs (run_id) on delete cascade,
  step_id       text not null check (step_id in (
                  'extraction', 'taxonomy_mapping', 'clarification_questions',
                  'clarification_answers', 'flag_resolution', 'category_inference',
                  'depth_assignment', 'metric_definition')),
  status        text not null check (status in ('started', 'completed', 'failed')),
  -- The step's validated result as {"schema_version": <int>, "data": {...}}.
  output        jsonb,
  error_type    text,
  error_message text,
  retryable     boolean,
  created_at    timestamptz not null default now(),
  primary key (run_id, step_id),
  constraint r1_run_steps_output_iff_completed
    check ((status = 'completed') = (output is not null)),
  constraint r1_run_steps_error_iff_failed
    check ((status = 'failed') = (error_type is not null and retryable is not null))
);

alter table public.r1_runs      enable row level security;
alter table public.r1_run_steps enable row level security;

-- 4. updated_at moves on every run update; the status read uses it to spot a stuck run (D1).
create or replace function public.set_r1_runs_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = clock_timestamp();
  return new;
end;
$$;

drop trigger if exists r1_runs_set_updated_at on public.r1_runs;
create trigger r1_runs_set_updated_at
  before update on public.r1_runs
  for each row
  execute function public.set_r1_runs_updated_at();

-- 5. A completed checkpoint is never changed.
create or replace function public.reject_completed_r1_step_update()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if old.status = 'completed' then
    raise exception 'r1_run_steps (%, %) is completed and cannot change',
      old.run_id, old.step_id;
  end if;
  return new;
end;
$$;

drop trigger if exists r1_run_steps_completed_immutable on public.r1_run_steps;
create trigger r1_run_steps_completed_immutable
  before update on public.r1_run_steps
  for each row
  execute function public.reject_completed_r1_step_update();
