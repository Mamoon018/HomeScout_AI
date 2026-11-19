/**
 * The status endpoint's body → `R3RunView`. Checks the top level only (status, ids, the rows'
 * keys); each row's record is read field by field later, in `buildPlacesMetrics`.
 */
import type { R3Row, R3RunStatus, R3RunView, R3RunWire } from '@/features/places-metrics/types/r3Run'

const STATUSES: readonly R3RunStatus[] = ['running', 'finished', 'failed']

/** Null when the body is not a run (missing id or an unknown status). */
export function normalizeR3Run(wire: R3RunWire | null): R3RunView | null {
  if (!wire || typeof wire.run_id !== 'string') return null
  const status = STATUSES.find((s) => s === wire.status)
  if (!status) return null

  let result: R3Row[] | null = null
  if (status === 'finished') {
    // A finished body always carries `result`; without it the run cannot be shown.
    if (!Array.isArray(wire.result)) return null
    result = wire.result.flatMap((row) => {
      if (typeof row?.category_id !== 'number' || typeof row.place_id !== 'string' || !row.value) return []
      return [
        {
          categoryId: row.category_id,
          placeId: row.place_id,
          websiteUrl: typeof row.website?.url === 'string' && row.website.url ? row.website.url : null,
          record: row.value,
        },
      ]
    })
  }

  return {
    runId: wire.run_id,
    status,
    completedStep: wire.completed_step === 'discovery_batch' ? 'discovery_batch' : null,
    result,
    retryable: status === 'failed' ? wire.retryable === true : null,
    // A missing parent never rejects the body: status shows from R3 alone; the chain stops later.
    r2RunId: typeof wire.r2_run_id === 'string' && wire.r2_run_id ? wire.r2_run_id : null,
  }
}
