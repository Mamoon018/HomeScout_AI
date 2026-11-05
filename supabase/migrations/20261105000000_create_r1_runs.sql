-- R1 (Requirement Interpretation) runs: one row per run, tied to the user who started it.
-- Safe to run again: every statement is a no-op when its object already exists.
-- Only the backend's service-role key reaches this table (RLS on, no policies).

create table if not exists public.r1_runs (
  run_id uuid primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  status text not null check (status in ('needs_answers', 'finished', 'failed')),
  -- The single R1 state as {"version": <int>, "state": {...}}, incl. questions and answers.
  state jsonb,
  -- R1's finished output for R2 (category_metric_plans).
  output jsonb,
  failure_stage text,
  failure_message text,
  retryable boolean not null default false,
  attempts integer not null default 0 check (attempts >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Only a finished run carries an output, so R2 can never read an unfinished one.
  constraint r1_runs_output_only_when_finished
    check ((status = 'finished') = (output is not null))
);

create index if not exists r1_runs_user_id_idx on public.r1_runs (user_id);

alter table public.r1_runs enable row level security;

-- Every update moves updated_at, which the backend uses as a compare-and-set guard.
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
