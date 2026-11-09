-- R3 step records: one row for each of R3's two expensive steps (R3-C5 Iteration 1), filled the
-- way r2_run_steps is, plus a `degraded` status for a STEP 3 that ended with the breaker open.
-- A record only: resume and status read r3_runs.
-- Safe to run again: every statement is a no-op when its object already exists.
-- Only the backend's service-role key reaches this table (RLS on, no policies).

create table if not exists public.r3_run_steps (
  run_id        uuid not null references public.r3_runs (run_id) on delete cascade,
  -- STEP 3 (finding websites) and STEP 4 (resolving metrics). STEP 1/2 and the catalog are
  -- recomputed, and STEP 5 is covered by the finish write, so they have no row.
  step_id       text not null check (step_id in ('discovery_batch', 'pipelines')),
  status        text not null check (status in ('started', 'completed', 'degraded', 'failed')),
  -- {"schema_version": <int>, "data": ...}: STEP 3's three result dicts, or resolution_results.
  output        jsonb,
  error_type    text,
  error_message text,
  retryable     boolean,
  created_at    timestamptz not null default now(),
  primary key (run_id, step_id),
  -- A `degraded` row keeps what STEP 3 found during the outage; only these two statuses hold data.
  constraint r3_run_steps_output_iff_completed_or_degraded
    check ((status in ('completed', 'degraded')) = (output is not null)),
  constraint r3_run_steps_error_iff_failed
    check ((status = 'failed') = (error_type is not null and retryable is not null))
);

alter table public.r3_run_steps enable row level security;

-- A completed step row is never changed (a degraded or failed one may be claimed by a retry).
create or replace function public.reject_completed_r3_step_update()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if old.status = 'completed' then
    raise exception 'r3_run_steps (%, %) is completed and cannot change',
      old.run_id, old.step_id;
  end if;
  return new;
end;
$$;

drop trigger if exists r3_run_steps_completed_immutable on public.r3_run_steps;
create trigger r3_run_steps_completed_immutable
  before update on public.r3_run_steps
  for each row
  execute function public.reject_completed_r3_step_update();
