-- R2 (Amenity Search) runs: one row per run, tied to the user who started it and to the
-- finished R1 run it reads. See R2_R3_Independent_Services_Problem_Context.md (R2-C4).
-- Safe to run again: every statement is a no-op when its object already exists.
-- Only the backend's service-role key reaches this table (RLS on, no policies).

create table if not exists public.r2_runs (
  run_id          uuid primary key,
  user_id         uuid not null references auth.users (id) on delete cascade,
  -- Deleting the R1 run deletes its R2 runs, so an output never points at a missing input.
  r1_run_id       uuid not null references public.r1_runs (run_id) on delete cascade,
  status          text not null check (status in ('running', 'finished', 'failed')),
  -- The single R2 state as {"version": <int>, "state": {...}}.
  state           jsonb not null,
  -- The last checkpointed step; null until the discovery checkpoint (R2-C2).
  completed_step  text check (completed_step in ('discovery')),
  -- R2's finished output for R3 as {"version": <int>, "output": {...}}.
  output          jsonb,
  failure_stage   text,
  failure_message text,
  retryable       boolean not null default false,
  attempts        integer not null default 0 check (attempts >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint r2_runs_output_iff_finished
    check ((status = 'finished') = (output is not null))
);

create index if not exists r2_runs_user_id_idx on public.r2_runs (user_id);

alter table public.r2_runs enable row level security;

-- updated_at moves on every update; the retry claim compares it with the stale cutoff (R2-C5).
create or replace function public.set_r2_runs_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = clock_timestamp();
  return new;
end;
$$;

drop trigger if exists r2_runs_set_updated_at on public.r2_runs;
create trigger r2_runs_set_updated_at
  before update on public.r2_runs
  for each row
  execute function public.set_r2_runs_updated_at();
