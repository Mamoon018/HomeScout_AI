import { EXTRACTION } from '@/test/fixtures/r1Extraction'
import { PLAN } from '@/test/fixtures/r1Plan'
import { QUESTIONS } from '@/test/fixtures/r1Questions'

/** Drops null values at every depth, the way the backend's run responses do. */
export function dropNulls<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map(dropNulls) as T
  }
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, v]) => v !== null)
        .map(([k, v]) => [k, dropNulls(v)]),
    ) as T
  }
  return value
}

export const RUN_ID = '3f2b8c1e-0000-4000-8000-000000000000'

const extraction = dropNulls(EXTRACTION)

/** Run bodies exactly as the endpoints send them, one per status. */
export const BODY = {
  paused: {
    run_id: RUN_ID,
    status: 'needs_answers',
    user_requirements_structured: extraction,
    questions: QUESTIONS,
  },
  finished: {
    run_id: RUN_ID,
    status: 'finished',
    user_requirements_structured: extraction,
    result: dropNulls(PLAN),
  },
  running: { run_id: RUN_ID, status: 'running' },
  failed: (retryable: boolean, withExtraction = true) => ({
    run_id: RUN_ID,
    status: 'failed',
    ...(withExtraction ? { user_requirements_structured: extraction } : {}),
    retryable,
  }),
}

/** The body of a 5xx the run itself recorded. */
export const RUN_FAILED_BODY = (retryable: boolean) => ({
  error: 'Requirement interpretation failed',
  run_id: RUN_ID,
  status: 'failed',
  retryable,
})
