/**
 * R3 run bodies exactly as `/api/specific-metric-resolution/runs` sends them, plus the R1 and R2
 * bodies the page joins them with. Built from the design's dummy places (gyms and museums), cut
 * down to the cases the page must handle: a full fit, a "No", a mixed opinion, every unresolved
 * reason, a currency value, a missing walk route, and a category with no questions.
 */
import { record } from '@/test/fixtures/r2Bodies'

export const R3_RUN_ID = '5b1e7c3d-0000-4000-8000-000000000000'
export const R2_RUN_ID = '7c4d9e2a-0000-4000-8000-000000000000'
export const R1_RUN_ID = '3f2b8c1e-0000-4000-8000-000000000000'

/** A second, newer chain (run B) the same tab may also have run: its data must never show under A. */
export const R3_RUN_ID_B = '5b1e7c3d-0000-4000-8000-0000000000bb'
export const R2_RUN_ID_B = '7c4d9e2a-0000-4000-8000-0000000000bb'
export const R1_RUN_ID_B = '3f2b8c1e-0000-4000-8000-0000000000bb'

/* ---------- R1: the plan gives question wording, unit and type; extraction says what was asked ---------- */

const metric = (label: string, question: string, value_type: string, over: Record<string, unknown> = {}) => ({
  label,
  question,
  value_type,
  enum_values: [],
  evidence_class: 'factual',
  resolution_source: { web_target: 'x' },
  verification: 'stated by the place or 3 listings',
  null_policy: 'unknown',
  band: 'specific_attributes',
  ...over,
})

export const R1_FINISHED = {
  run_id: R1_RUN_ID,
  status: 'finished',
  user_requirements_structured: {
    persona_facts: [],
    ambiguity_flags: [],
    // Only the gym was asked for; the museum was inferred.
    explicit_categories: [{ name: 'a gym with a lifting platform', category_id: 1, characteristics: [] }],
  },
  result: [
    {
      category_id: 1,
      taxonomy_node: 'gym',
      depth: 'specific_attributes',
      predefined_metrics: [],
      specific_metrics: [
        metric('Powerlifting platform', 'Is there a powerlifting platform?', 'boolean'),
        metric('evening_crowding', 'Is it crowded on weekday evenings?', 'enum', {
          enum_values: ['quiet', 'moderate', 'busy'],
          evidence_class: 'experiential',
        }),
      ],
    },
    // A category R2 searched but with nothing specific to check: never shown on this page.
    { category_id: 2, taxonomy_node: 'transit_station', depth: 'basic_profile', predefined_metrics: [], specific_metrics: [] },
    {
      category_id: 4,
      taxonomy_node: 'museum',
      depth: 'specific_attributes',
      predefined_metrics: [],
      specific_metrics: [
        metric('museumkaart_free_entry', 'Is entry free with a Museumkaart?', 'boolean'),
        metric('adult_ticket_price', 'What does an adult ticket cost?', 'number_with_unit', { unit: 'EUR' }),
      ],
    },
  ],
}

/* ---------- R2: names, ratings and travel for each place ---------- */

const leg = (min: number, km: number) => ({ duration_min: min, distance_km: km })

export const R2_FINISHED = {
  run_id: R2_RUN_ID,
  r1_run_id: R1_RUN_ID,
  origin: { latitude: 52.3676, longitude: 4.9041 },
  radius_km: 2,
  status: 'finished',
  result: {
    '1': {
      iron: record(1, 'gym', 'iron', { name: 'Iron Yard Strength', routing: { walk: leg(4, 0.3), cycle: leg(2, 0.4), drive: leg(3, 0.5) } }),
      canal: record(1, 'gym', 'canal', { name: 'Canal Fitness', routing: { walk: leg(6, 0.5), cycle: leg(2, 0.5), drive: leg(4, 0.6) } }),
      // No walking route and no rating: the page must say so, not invent them.
      plant: record(1, 'gym', 'plant', { name: 'Plantage Fit', rating: undefined, routing: { cycle: leg(6, 1.4), drive: leg(7, 1.6) } }),
    },
    '2': { 'st-1': record(2, 'transit_station', 'st-1', { name: 'Hauptbahnhof' }) },
    '4': {
      canh: record(4, 'museum', 'canh', { name: 'Canal History Museum', routing: { walk: leg(12, 0.9), cycle: leg(4, 1), drive: leg(6, 1.2) } }),
      here: record(4, 'museum', 'here', { name: 'Herengracht Print Museum', routing: { walk: leg(16, 1.2), cycle: leg(6, 1.3), drive: leg(7, 1.5) } }),
    },
  },
}

/* ---------- R3: one row per amenity; `value` is the resolution record as JSON ---------- */

const CHECKED = '2026-11-14T10:20:00+00:00'

/** Phase-1 evidence items: what the search found per label (source counts, the check date). */
function phase1(items: { url: string | null; kind?: string; labels: string[] }[], outcomes: Record<string, string> = {}) {
  return {
    messages: [],
    metrics_source_content: {
      items: items.map((i, n) => ({
        evidence_id: `e${n}`,
        source_kind: i.kind ?? 'web',
        url: i.url,
        shaped_text: 'text',
        retrieved_at: CHECKED,
        metric_labels: i.labels,
      })),
      _index: {},
    },
    metric_outcomes: Object.fromEntries(Object.entries(outcomes).map(([l, s]) => [l, { label: l, status: s, attempts_used: 1, failure_kind: null }])),
    uncovered_labels: [],
    turns_run: 2,
  }
}

type Kept = {
  value: string | number | boolean | null
  basis?: string
  mixed?: boolean
  verified?: boolean
  web?: string | null
  reviews?: string | null
  scrape?: string | null
  evidence?: { source: string; url: string | null; quote: string }[]
}

function kept(label: string, k: Kept) {
  return {
    metric_label: label,
    web_value: k.web ?? null,
    scrape_value: k.scrape ?? null,
    reviews_value: k.reviews ?? null,
    relation: k.reviews && k.web ? (k.mixed ? 'conflict' : 'agree') : 'none',
    verification_met: k.verified ?? true,
    final_value: k.value,
    opinion_mixed: k.mixed ?? false,
    basis: k.basis ?? 'web',
    evidence: k.evidence ?? [],
  }
}

function row(categoryId: number, placeId: string, website: string | null, value: Record<string, unknown>) {
  return {
    category_id: categoryId,
    place_id: placeId,
    website: { url: website, origin: website ? 'google' : 'none' },
    value: {
      category_id: categoryId,
      place_id: placeId,
      outcome: 'completed',
      kept: {},
      unresolved: {},
      phase1: null,
      resolution_calls: 1,
      failed_stage: null,
      failed_cause: null,
      ...value,
    },
  }
}

const PLATFORM = 'Powerlifting platform'
const CROWD = 'evening_crowding'
const CARD = 'museumkaart_free_entry'
const PRICE = 'adult_ticket_price'

export const R3_ROWS = [
  // Fits both: a confirmed yes and a confirmed "moderate".
  row(1, 'iron', 'https://www.ironyard-strength.nl/', {
    kept: {
      [PLATFORM]: kept(PLATFORM, {
        value: true,
        web: 'two competition-grade platforms',
        evidence: [{ source: 'web', url: 'https://www.ironyard-strength.nl/floor', quote: 'Two competition-grade lifting platforms.' }],
      }),
      [CROWD]: kept(CROWD, {
        value: 'moderate',
        basis: 'web_and_reviews',
        web: 'steady after work, rarely full',
        reviews: 'moderate (2 reviews)',
        evidence: [
          { source: 'web', url: 'https://amsterdam-gym-guide.com/iron', quote: 'Steady after work, but you rarely wait.' },
          { source: 'google_reviews', url: null, quote: 'Busy-ish around 6, never packed.' },
        ],
      }),
    },
    phase1: phase1([
      { url: 'https://www.ironyard-strength.nl/floor', labels: [PLATFORM] },
      { url: 'https://amsterdam-gym-guide.com/iron', labels: [PLATFORM, CROWD] },
      { url: null, kind: 'google_reviews', labels: [CROWD] },
    ]),
  }),
  // A "No" (Missing) and a mixed opinion (Leans busy).
  row(1, 'canal', 'https://canalfitness.nl', {
    kept: {
      [PLATFORM]: kept(PLATFORM, {
        value: false,
        web: 'no lifting platform',
        evidence: [{ source: 'web', url: 'https://canalfitness.nl/faq', quote: 'Lifting platforms are not available.' }],
      }),
      [CROWD]: kept(CROWD, {
        value: 'busy',
        mixed: true,
        basis: 'web_and_reviews',
        web: 'packed after 6 pm on weekdays',
        reviews: 'busy (3 reviews), quiet (1)',
        evidence: [{ source: 'google_reviews', url: null, quote: 'After work it is hard to get a squat rack.' }],
      }),
    },
  }),
  // Neither confirmed: the search failed for one, the evidence was too thin for the other.
  row(1, 'plant', null, {
    unresolved: { [PLATFORM]: 'no_evidence', [CROWD]: 'verification_unmet' },
    phase1: phase1([{ url: 'https://amsterdam-gym-guide.com/plant', labels: [CROWD] }], { [PLATFORM]: 'failed', [CROWD]: 'ok' }),
  }),
  row(4, 'canh', 'https://canalhistorymuseum.nl', {
    kept: {
      [CARD]: kept(CARD, { value: true, web: 'free with a Museumkaart', evidence: [{ source: 'scrape', url: 'https://canalhistorymuseum.nl/tickets', quote: 'Museumkaart holders enter free.' }] }),
      [PRICE]: kept(PRICE, { value: 17.5, web: '€17.50 adult ticket', evidence: [{ source: 'web', url: 'https://canalhistorymuseum.nl/tickets', quote: 'Adult admission: €17.50.' }] }),
    },
  }),
  // A kept entry whose verification was not met reads as unconfirmed; a mixed currency value leans.
  row(4, 'here', 'https://herengrachtprintmuseum.nl', {
    kept: {
      [CARD]: kept(CARD, { value: null, verified: false }),
      [PRICE]: kept(PRICE, {
        value: 25,
        mixed: true,
        web: 'split: €25 (official pages), €22 (a listings site)',
        evidence: [
          { source: 'web', url: 'https://herengrachtprintmuseum.nl/visit', quote: 'Adult tickets are €25.' },
          { source: 'web', url: 'https://tickets-amsterdam.com/print', quote: 'Print Museum entry from €22.' },
        ],
      }),
    },
  }),
]

export const R3_BODY = {
  running: { run_id: R3_RUN_ID, r2_run_id: R2_RUN_ID, status: 'running' },
  researching: { run_id: R3_RUN_ID, r2_run_id: R2_RUN_ID, status: 'running', completed_step: 'discovery_batch' },
  finished: { run_id: R3_RUN_ID, r2_run_id: R2_RUN_ID, status: 'finished', result: R3_ROWS },
  finishedEmpty: { run_id: R3_RUN_ID, r2_run_id: R2_RUN_ID, status: 'finished', result: [] },
  failed: (retryable: boolean) => ({ run_id: R3_RUN_ID, r2_run_id: R2_RUN_ID, status: 'failed', retryable }),
}

/* ---------- Run B: another brief's chain, distinguishable on screen ---------- */

/** B's places are A's with "Bravo " in front of each name, searched from Munich, not Amsterdam. */
export const R2_FINISHED_B = {
  ...R2_FINISHED,
  run_id: R2_RUN_ID_B,
  r1_run_id: R1_RUN_ID_B,
  origin: { latitude: 48.1374, longitude: 11.5755 },
  result: Object.fromEntries(
    Object.entries(R2_FINISHED.result).map(([cat, places]) => [
      cat,
      Object.fromEntries(Object.entries(places).map(([id, rec]) => [id, { ...rec, name: `Bravo ${rec.name}` }])),
    ]),
  ),
}

/** B's brief asked for the museum, not the gym, so the museum would not read as "also worth knowing". */
export const R1_FINISHED_B = {
  ...R1_FINISHED,
  run_id: R1_RUN_ID_B,
  user_requirements_structured: {
    ...R1_FINISHED.user_requirements_structured,
    explicit_categories: [{ name: 'a museum on the canals', category_id: 4, characteristics: [] }],
  },
}

/** Error bodies the controller sends. */
export const R3_ERROR = {
  notFound: { error: 'Run not found' },
  r2NotFound: { error: 'Finished amenity search run not found' },
  conflict: (status: string, retryable?: boolean) => ({
    error: 'The run cannot be retried',
    run_id: R3_RUN_ID,
    status,
    ...(status === 'failed' ? { retryable: retryable === true } : {}),
  }),
  storeDown: { error: 'Run storage is unavailable' },
  unauthenticated: { error: 'Not signed in' },
}
