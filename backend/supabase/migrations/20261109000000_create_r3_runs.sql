-- R3 (Specific Metric Resolution) runs: one row per run, tied to the user who started it and to
-- the finished R2 run it reads. See R2_R3_Independent_Services_Problem_Context.md (R3-C5).
-- Safe to run again: every statement is a no-op when its object already exists.
-- Only the backend's service-role key reaches this table (RLS on, no policies).

create table if not exists public.r3_runs (
  run_id          uuid primary key,
  user_id         uuid not null references auth.users (id) on delete cascade,
  -- Deleting the R2 run deletes its R3 runs, so a run never points at a missing input.
  r2_run_id       uuid not null references public.r2_runs (run_id) on delete cascade,
  status          text not null check (status in ('running', 'finished', 'failed')),
  -- The single R3 state as {"version": <int>, "state": {...}}; tuple-keyed dicts as entry lists.
  state           jsonb not null,
  -- The last checkpointed step; null until a clean STEP 3 checkpoint (R3-C3).
  completed_step  text check (completed_step in ('discovery_batch')),
  -- R3's finished output as {"version": <int>, "output": [{category_id, place_id, value}]}.
  output          jsonb,
  failure_stage   text,
  failure_message text,
  retryable       boolean not null default false,
  attempts        integer not null default 0 check (attempts >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint r3_runs_output_iff_finished
    check ((status = 'finished') = (output is not null))
);

create index if not exists r3_runs_user_id_idx on public.r3_runs (user_id);

alter table public.r3_runs enable row level security;

-- updated_at moves on every update; the retry claim compares it with the stale cutoff (R3-C6).
create or replace function public.set_r3_runs_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = clock_timestamp();
  return new;
end;
$$;

drop trigger if exists r3_runs_set_updated_at on public.r3_runs;
create trigger r3_runs_set_updated_at
  before update on public.r3_runs
  for each row
  execute function public.set_r3_runs_updated_at();
