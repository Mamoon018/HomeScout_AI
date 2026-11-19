import { apiFetch, type ApiErrorBody, type ApiResponse } from '@/lib/apiClient'
import type { R3Error, R3Result, R3RunStatus, R3RunWire } from '@/features/places-metrics/types/r3Run'
import { normalizeR3Run } from '@/features/places-metrics/utils/normalizeR3Run'

/** Same-origin path: the dev proxy and the SameSite cookies depend on it. */
const RUNS_PATH = '/api/specific-metric-resolution/runs'

/**
 * Start and retry answer 202 at once (the minutes of research run in a background task) and the
 * status call is a store read, so every call keeps the client's default timeout.
 */

type RunErrorBody = ApiErrorBody & { run_id?: string; status?: string; retryable?: boolean }

/** Starts R3 for a finished R2 run. Body is exactly `{ r2_run_id }` (extra fields are refused). */
export function startR3Run(r2RunId: string): Promise<R3Result> {
  return call(RUNS_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ r2_run_id: r2RunId }),
  })
}

/** Resumes a failed, retryable run (one retry per run). */
export function retryR3Run(runId: string): Promise<R3Result> {
  return call(`${RUNS_PATH}/${encodeURIComponent(runId)}/retry`, { method: 'POST' })
}

/** Reads a run's status, and its result once finished. */
export function getR3Run(runId: string): Promise<R3Result> {
  return call(`${RUNS_PATH}/${encodeURIComponent(runId)}`, { method: 'GET' })
}

async function call(path: string, init: RequestInit): Promise<R3Result> {
  const response = await apiFetch<R3RunWire & RunErrorBody>(path, init)
  if (response.ok) {
    const view = normalizeR3Run(response.data)
    return view ? { ok: true, view } : { ok: false, error: { kind: 'unavailable' } }
  }
  return { ok: false, error: classify(response) }
}

const STATUSES: readonly R3RunStatus[] = ['running', 'finished', 'failed']

/** Every non-2xx the controller can send, by what the page can do next. */
function classify(response: ApiResponse<RunErrorBody>): R3Error {
  if (response.aborted) return { kind: 'timeout' }
  if (response.networkError) return { kind: 'network' }
  const body = response.data
  switch (response.status) {
    case 401:
      return { kind: 'unauthenticated' }
    case 404:
      return { kind: 'not_found' }
    case 409: {
      const status = STATUSES.find((s) => s === body?.status) ?? null
      return { kind: 'conflict', status, retryable: status === 'failed' ? body?.retryable === true : null }
    }
    case 422:
      return { kind: 'rejected' }
  }
  return { kind: 'unavailable' }
}
