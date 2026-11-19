import { apiFetch, type ApiErrorBody, type ApiResponse } from '@/lib/apiClient'
import type {
  R1Error,
  R1Result,
  RunWire,
} from '@/features/r1-interpretation/types/run'
import { normalizeRun } from '@/features/r1-interpretation/utils/normalizeRun'
import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'

/** Same-origin path: the dev proxy and the SameSite cookies depend on it. */
const RUNS_PATH = '/api/requirement-interpretation/runs'

/**
 * Start, answers and retry each run several LLM steps inside one request, so they get far
 * longer than the client default. Reading a run is a plain database read and keeps the default.
 */
export const R1_WORK_TIMEOUT_MS = 45_000

/** The body of any non-2xx run response. FastAPI's own 422 uses `detail` instead of `error`. */
type RunErrorBody = ApiErrorBody & {
  run_id?: string
  status?: string
  retryable?: boolean
  detail?: unknown
}

/** An answer as the answers endpoint takes it: `description` only when "other" was chosen. */
export type WireAnswer = { category_id: number; option: number; description?: string }

/**
 * The page keeps each answer's meaning in `description` (the chosen option's text) to show it
 * back to the renter. The backend refuses a `description` unless the choice was "other", so it
 * is dropped here for every other option.
 */
export function toWireAnswers(
  answers: ClarificationAnswer[],
  questions: ClarificationQuestion[],
): WireAnswer[] {
  return answers.map((answer) => {
    const question = questions.find((q) => q.category_id === answer.category_id)
    const chosen = question?.options[answer.option - 1]
    const base = { category_id: answer.category_id, option: answer.option }
    return chosen === 'other' ? { ...base, description: answer.description } : base
  })
}

export function startRun(requirements: string): Promise<R1Result> {
  return call(
    RUNS_PATH,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requirements }),
    },
    R1_WORK_TIMEOUT_MS,
  )
}

export function submitAnswers(runId: string, answers: WireAnswer[]): Promise<R1Result> {
  return call(
    `${RUNS_PATH}/${encodeURIComponent(runId)}/clarification-answers`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    },
    R1_WORK_TIMEOUT_MS,
  )
}

export function retryRun(runId: string): Promise<R1Result> {
  return call(
    `${RUNS_PATH}/${encodeURIComponent(runId)}/retry`,
    { method: 'POST' },
    R1_WORK_TIMEOUT_MS,
  )
}

export function getRun(runId: string): Promise<R1Result> {
  return call(`${RUNS_PATH}/${encodeURIComponent(runId)}`, { method: 'GET' })
}

async function call(path: string, init: RequestInit, timeoutMs?: number): Promise<R1Result> {
  const response = await apiFetch<RunWire & RunErrorBody>(path, init, { timeoutMs })
  if (response.ok) {
    const view = normalizeRun(response.data)
    return view ? { ok: true, view } : { ok: false, error: { kind: 'unavailable' } }
  }
  return { ok: false, error: classify(response) }
}

/** One failed response, by what the page can do about it. */
function classify(response: ApiResponse<RunErrorBody>): R1Error {
  if (response.aborted) {
    return { kind: 'timeout' }
  }
  if (response.networkError) {
    return { kind: 'network' }
  }
  const body = response.data
  switch (response.status) {
    case 401:
      return { kind: 'unauthenticated' }
    case 404:
      return { kind: 'not_found' }
    case 409:
      return { kind: 'conflict', runId: body?.run_id ?? null }
    case 422:
      return { kind: 'rejected', message: typeof body?.error === 'string' ? body.error : '' }
  }
  // A failure the run itself recorded: the body names the run and whether Retry is left.
  if (response.status >= 500 && typeof body?.run_id === 'string' && body.status === 'failed') {
    return { kind: 'run_failed', runId: body.run_id, retryable: body.retryable === true }
  }
  return { kind: 'unavailable' }
}
