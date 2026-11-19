import type {
  CategoryMetricPlan,
  ExtractionOutput,
} from '@/features/r1-interpretation/types/r1'
import type { ClarificationQuestion } from '@/features/search-progress/types/clarification'

/** The one status a run reports. `running` while a request is still working on it. */
export type RunStatus = 'running' | 'needs_answers' | 'finished' | 'failed'

/**
 * A run body exactly as the backend sends it. The backend drops null fields everywhere (not
 * just at the top level), so every field it can leave out is optional here. `normalizeRun`
 * turns this into `RunView`, which is what the page works with.
 */
export type RunWire = {
  run_id?: string
  status?: string
  user_requirements_structured?: {
    explicit_categories?: {
      name: string
      category_id?: number
      characteristics?: string[]
    }[]
    ambiguity_flags?: {
      phrase: string
      target: string
      category?: string
      category_id?: number
      characteristic?: string
    }[]
    persona_facts?: string[]
  }
  questions?: ClarificationQuestion[]
  result?: {
    category_id: number
    taxonomy_node: string
    depth: string
    predefined_metrics?: CategoryMetricPlan['predefined_metrics']
    specific_metrics?: {
      label: string
      question: string
      value_type: string
      unit?: string
      enum_values?: string[]
      evidence_class: string
      resolution_source?: {
        web_target?: string
        scrape_target?: string
        review_target?: string
      }
      verification: string
      null_policy: string
      band: string
    }[]
  }[]
  retryable?: boolean
}

/** What the page works with: every field present, null or empty when the run has nothing. */
export type RunView = {
  runId: string
  status: RunStatus
  /** The extraction output. Null until the run has saved that step. */
  extraction: ExtractionOutput | null
  /** The questions R1 waits on; empty unless `status` is `needs_answers`. */
  questions: ClarificationQuestion[]
  /** The finished plan; null unless `status` is `finished`. */
  plan: CategoryMetricPlan[] | null
  /** Set when `status` is `failed`: whether Retry is still allowed. */
  retryable: boolean | null
}

/** Why a call to a run endpoint did not give a run, by what the page can do about it. */
export type R1Error =
  /** 422: the brief or the answers were refused. `message` is the server's reason. */
  | { kind: 'rejected'; message: string }
  /** 409: the run is not in the state this call needed. The page re-reads it. */
  | { kind: 'conflict'; runId: string | null }
  /** 404: there is no such run for this user. */
  | { kind: 'not_found' }
  /** 500/502/503 about a known run: the run is saved as failed. */
  | { kind: 'run_failed'; runId: string; retryable: boolean }
  /** 401 that a token refresh did not fix. */
  | { kind: 'unauthenticated' }
  /** The call timed out. The server may still be working on the run. */
  | { kind: 'timeout' }
  /** Could not reach the server. */
  | { kind: 'network' }
  /** Anything else: storage down, service off, a body the page cannot read. */
  | { kind: 'unavailable' }

export type R1Result = { ok: true; view: RunView } | { ok: false; error: R1Error }
