-- R2 step records: one row per non-reproducible step of a run (R2-C4 Iteration 1), filled the
-- way r1_run_steps is. A record only: resume and status read r2_runs.
-- Safe to run again: every statement is a no-op when its object already exists.
-- Only the backend's service-role key reaches this table (RLS on, no policies).

create table if not exists public.r2_run_steps (
  run_id        uuid not null references public.r2_runs (run_id) on delete cascade,
  -- `attachment` is pure and recomputed, so it has no row.
  step_id       text not null check (step_id in ('discovery', 'enrichment')),
  status        text not null check (status in ('started', 'completed', 'failed')),
  -- {"schema_version": <int>, "data": ...}: discovered_places or enrichment.
  output        jsonb,
  error_type    text,
  error_message text,
  retryable     boolean,
  created_at    timestamptz not null default now(),
  primary key (run_id, step_id),
  constraint r2_run_steps_output_iff_completed
    check ((status = 'completed') = (output is not null)),
  constraint r2_run_steps_error_iff_failed
    check ((status = 'failed') = (error_type is not null and retryable is not null))
);

alter table public.r2_run_steps enable row level security;

-- A completed step row is never changed.
create or replace function public.reject_completed_r2_step_update()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if old.status = 'completed' then
    raise exception 'r2_run_steps (%, %) is completed and cannot change',
      old.run_id, old.step_id;
  end if;
  return new;
end;
$$;

drop trigger if exists r2_run_steps_completed_immutable on public.r2_run_steps;
create trigger r2_run_steps_completed_immutable
  before update on public.r2_run_steps
  for each row
  execute function public.reject_completed_r2_step_update();
