-- R1's finished output for R2 (R2-P1): `category_metric_plans` as plain JSON, written in the
-- same UPDATE that sets `finished`. Its shape is tied to `workflow_version`.
-- Safe to run again: every statement is a no-op when its object already exists.

alter table public.r1_runs add column if not exists output jsonb;

-- A finished run always has an output, and no other run has one.
-- NOT VALID: runs finished before this column have `output = null` (they read as 404 for R2,
-- no backfill). The check still applies to every new insert and update; finished rows are
-- terminal and never updated again.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'r1_runs_output_iff_finished'
      and conrelid = 'public.r1_runs'::regclass
  ) then
    alter table public.r1_runs
      add constraint r1_runs_output_iff_finished
      check ((status = 'finished') = (output is not null)) not valid;
  end if;
end;
$$;
