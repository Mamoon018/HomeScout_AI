import type {
  AmbiguityFlag,
  CategoryMetricPlan,
  ExtractionOutput,
  SpecificMetric,
} from '@/features/r1-interpretation/types/r1'
import type { RunStatus, RunView, RunWire } from '@/features/r1-interpretation/types/run'

const STATUSES: readonly RunStatus[] = ['running', 'needs_answers', 'finished', 'failed']

/**
 * Turns a run body into the shape the page reads. The backend leaves out every null field
 * (even inside lists), so absent becomes null or empty here, once, and no component has to
 * check for `undefined`. Nothing is invented: a missing value stays null or empty.
 *
 * Returns null for a body the page cannot use (no id, an unknown status, or a status whose
 * required parts are missing), so the caller shows "could not read" instead of half a run.
 */
export function normalizeRun(wire: RunWire | null | undefined): RunView | null {
  if (!wire || typeof wire.run_id !== 'string' || !isStatus(wire.status)) {
    return null
  }
  const status = wire.status
  const extraction = wire.user_requirements_structured
    ? normalizeExtraction(wire.user_requirements_structured)
    : null
  const questions = wire.questions ?? []
  const plan = wire.result ? wire.result.map(normalizePlanEntry) : null

  // A paused run is useless without its questions, and a finished one without its plan.
  if (status === 'needs_answers' && (questions.length === 0 || extraction === null)) {
    return null
  }
  if (status === 'finished' && (plan === null || extraction === null)) {
    return null
  }

  return {
    runId: wire.run_id,
    status,
    extraction,
    questions: status === 'needs_answers' ? questions : [],
    plan: status === 'finished' ? plan : null,
    retryable: status === 'failed' ? wire.retryable === true : null,
  }
}

function isStatus(value: unknown): value is RunStatus {
  return typeof value === 'string' && (STATUSES as readonly string[]).includes(value)
}

function normalizeExtraction(
  raw: NonNullable<RunWire['user_requirements_structured']>,
): ExtractionOutput {
  return {
    persona_facts: raw.persona_facts ?? [],
    ambiguity_flags: (raw.ambiguity_flags ?? []).map(
      (flag): AmbiguityFlag => ({
        phrase: flag.phrase,
        // Kept as sent: a value this page does not know still renders its phrase.
        target: flag.target as AmbiguityFlag['target'],
        category: flag.category ?? null,
        category_id: flag.category_id ?? null,
        characteristic: flag.characteristic ?? null,
      }),
    ),
    // The backend numbers categories by list position, so position is the fallback id.
    explicit_categories: (raw.explicit_categories ?? []).map((category, index) => ({
      name: category.name,
      category_id: category.category_id ?? index,
      characteristics: category.characteristics ?? [],
    })),
  }
}

function normalizePlanEntry(entry: NonNullable<RunWire['result']>[number]): CategoryMetricPlan {
  return {
    category_id: entry.category_id,
    taxonomy_node: entry.taxonomy_node,
    depth: entry.depth as CategoryMetricPlan['depth'],
    predefined_metrics: entry.predefined_metrics ?? [],
    specific_metrics: (entry.specific_metrics ?? []).map(
      (metric): SpecificMetric => ({
        label: metric.label,
        question: metric.question,
        value_type: metric.value_type,
        unit: metric.unit ?? null,
        enum_values: metric.enum_values ?? [],
        evidence_class: metric.evidence_class as SpecificMetric['evidence_class'],
        resolution_source: {
          web_target: metric.resolution_source?.web_target ?? null,
          scrape_target: metric.resolution_source?.scrape_target ?? null,
          review_target: metric.resolution_source?.review_target ?? null,
        },
        verification: metric.verification,
        null_policy: metric.null_policy,
        band: metric.band as SpecificMetric['band'],
      }),
    ),
  }
}
