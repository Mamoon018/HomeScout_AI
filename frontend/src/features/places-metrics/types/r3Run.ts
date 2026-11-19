/**
 * R3 (Specific Metric Resolution) as the backend sends it, and the run view the page works with.
 *
 * Source of truth: `backend/src/schemas/specific_metric_resolution.py` (response model),
 * `.../controllers/specific_metric_resolution.py` (`exclude_none` at the top level only; `result`
 * is dumped without it, so its nested nulls are sent), and `AmenityResolutionRecord` /
 * `MetricResolutionEntry` in `feature_schemas/schemas.py` (the shape of each row's `value`).
 * Every field is optional here: the normalizer checks what arrives.
 */

export type R3RunStatus = 'running' | 'finished' | 'failed'

/** One quote a resolved answer rests on. `url` is null for a Google review. */
export type ResolutionEvidenceWire = {
  source?: string
  url?: string | null
  quote?: string
}

/** One kept metric: the resolution turn's verdict for one question about one place. */
export type MetricResolutionWire = {
  metric_label?: string
  web_value?: string | null
  scrape_value?: string | null
  reviews_value?: string | null
  relation?: string
  verification_met?: boolean
  final_value?: string | number | boolean | null
  opinion_mixed?: boolean
  basis?: string
  evidence?: ResolutionEvidenceWire[]
}

/** One evidence item the search found (phase 1); read for source counts and the check date. */
export type EvidenceItemWire = {
  source_kind?: string
  url?: string | null
  retrieved_at?: string
  metric_labels?: string[]
}

/** The amenity's resolution record (`AmenityResolutionRecord` as JSON). */
export type ResolutionRecordWire = {
  category_id?: number
  place_id?: string
  /** `completed`, `resolution_call_failed` or `pipeline_error`. */
  outcome?: string
  kept?: Record<string, MetricResolutionWire>
  /** Label → `no_evidence`, `verification_unmet`, … (see `UnresolvedReason`). */
  unresolved?: Record<string, string>
  phase1?: {
    metrics_source_content?: { items?: EvidenceItemWire[] }
    /** Label → `{ status: not_searched | ok | empty | failed, … }`. */
    metric_outcomes?: Record<string, { status?: string }>
  } | null
}

export type R3ResultRowWire = {
  category_id?: number
  place_id?: string
  website?: { url?: string | null; origin?: string }
  value?: ResolutionRecordWire
}

export type R3RunWire = {
  run_id?: string
  /** The R2 run this run started from (the chain's next link). */
  r2_run_id?: string
  status?: string
  completed_step?: string
  result?: R3ResultRowWire[]
  retryable?: boolean
}

/** One finished row, checked: ids present, the record kept as sent. */
export type R3Row = {
  categoryId: number
  placeId: string
  websiteUrl: string | null
  record: ResolutionRecordWire
}

export type R3RunView = {
  runId: string
  status: R3RunStatus
  /** `discovery_batch` once every place's website was looked up ("researching" begins). */
  completedStep: 'discovery_batch' | null
  /** One row per amenity; null unless `status` is `finished`. */
  result: R3Row[] | null
  /** Set when `status` is `failed`: Retry when true, Start again when false. */
  retryable: boolean | null
  /** The R2 run this run started from; null when the body did not name one. */
  r2RunId: string | null
}

/** Why a call did not give a run, by what the page can do about it. */
export type R3Error =
  /** 422: the R2 run id was refused. */
  | { kind: 'rejected' }
  /** 409 on retry: not retryable now. `status` is the run's current status. */
  | { kind: 'conflict'; status: R3RunStatus | null; retryable: boolean | null }
  /** 404: no such run (on start: no finished R2 run for this user). */
  | { kind: 'not_found' }
  | { kind: 'unauthenticated' }
  | { kind: 'timeout' }
  | { kind: 'network' }
  /** 503 store down, a 500, or a body the page cannot read. */
  | { kind: 'unavailable' }

export type R3Result = { ok: true; view: R3RunView } | { ok: false; error: R3Error }
