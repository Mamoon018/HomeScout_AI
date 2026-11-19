import { apiFetch, type ApiErrorBody, type ApiResponse } from '@/lib/apiClient'
import type {
  R2Error,
  R2Result,
  R2RunStatus,
  R2RunWire,
  StartInput,
} from '@/features/r2-proximity/types/r2'
import { normalizeR2Run } from '@/features/r2-proximity/utils/normalizeR2Run'

/** Same-origin path: the dev proxy and the SameSite cookies depend on it. */
const RUNS_PATH = '/api/amenity-search/runs'

/**
 * Start and retry answer 202 at once (the work runs in a background task) and the status call
 * is a store read, so every call keeps the client's default timeout.
 */

type RunErrorBody = ApiErrorBody & {
  run_id?: string
  status?: string
  retryable?: boolean
  detail?: unknown
}

export function startR2Run(input: StartInput): Promise<R2Result> {
  return call(RUNS_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      r1_run_id: input.r1RunId,
      origin: { latitude: input.latitude, longitude: input.longitude },
      radius_km: input.radiusKm,
    }),
  })
}

export function retryR2Run(runId: string): Promise<R2Result> {
  return call(`${RUNS_PATH}/${encodeURIComponent(runId)}/retry`, { method: 'POST' })
}

export function getR2Run(runId: string): Promise<R2Result> {
  return call(`${RUNS_PATH}/${encodeURIComponent(runId)}`, { method: 'GET' })
}

async function call(path: string, init: RequestInit): Promise<R2Result> {
  const response = await apiFetch<R2RunWire & RunErrorBody>(path, init)
  if (response.ok) {
    const view = normalizeR2Run(response.data)
    return view ? { ok: true, view } : { ok: false, error: { kind: 'unavailable' } }
  }
  return { ok: false, error: classify(response) }
}

const STATUSES: readonly R2RunStatus[] = ['running', 'finished', 'failed']

function classify(response: ApiResponse<RunErrorBody>): R2Error {
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
    case 409: {
      const status = STATUSES.find((s) => s === body?.status) ?? null
      return {
        kind: 'conflict',
        status,
        retryable: status === 'failed' ? body?.retryable === true : null,
      }
    }
    case 422:
      return { kind: 'rejected', message: typeof body?.error === 'string' ? body.error : '' }
  }
  return { kind: 'unavailable' }
}
