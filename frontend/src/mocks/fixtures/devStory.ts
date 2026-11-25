/**
 * The dev mock's one coherent story: the Munich apartment brief of the R1 fixtures, the places R2
 * finds for its plan (a station and a supermarket category), and the R3 answers to that plan's two
 * specific questions. Every body takes its run id (and parent id) as an argument, so the mock can
 * stamp a scenario's fixed ids on it. Used by the dev mock and the fixture-contract test.
 *
 * Data path: devStory → mocks/mockRunStore → mocks/mockFetch → r1Api / r2Api / r3Api → pages.
 */
import { BODY } from '@/mocks/fixtures/r1Bodies'
import { record } from '@/mocks/fixtures/r2Bodies'
import { kept, phase1, row } from '@/mocks/fixtures/r3Bodies'

export const DEV_ORIGIN = { latitude: 48.1374, longitude: 11.5755 }
export const DEV_RADIUS_KM = 2

const leg = (min: number, km: number) => ({ duration_min: min, distance_km: km })

const WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map(
  (d) => `${d}: 7:00 AM – 9:00 PM`,
)

/** R2 places for the plan's categories: 2 transit_station, 3 supermarket. */
export const DEV_R2_RESULT = {
  '2': {
    'st-1': record(2, 'transit_station', 'st-1', { name: 'München Hauptbahnhof' }),
    'st-2': record(2, 'transit_station', 'st-2', {
      name: 'Ostbahnhof',
      routing: { walk: leg(14, 1.1), cycle: leg(5, 1.2), drive: leg(5, 1.4) },
      transit: { duration_min: 12, distance_km: 1.3, used_fallback: true },
    }),
  },
  '3': {
    'sm-1': record(3, 'supermarket', 'sm-1', {
      name: 'Viktualien Markthalle',
      opening_hours: { weekday_descriptions: [...WEEK, 'Sunday: Closed'] },
    }),
    // Sparse on purpose: no rating and no walking route, so the page must say so.
    'sm-2': record(3, 'supermarket', 'sm-2', {
      name: 'Frischmarkt Haidhausen',
      rating: undefined,
      routing: { cycle: leg(7, 1.7), drive: leg(6, 1.9) },
    }),
  },
}

const RAIL = 'Rail service type'
const PRODUCE = 'Fresh produce quality'

/** R3 rows answering the plan's two questions: two confirmed, one mixed, one unresolved. */
export const DEV_R3_ROWS = [
  row(2, 'st-1', 'https://www.mvg.de/', {
    kept: {
      [RAIL]: kept(RAIL, {
        value: 'both',
        web: 'U-Bahn U1, U2, U4, U5 and the S-Bahn trunk line',
        evidence: [{ source: 'web', url: 'https://www.mvg.de/hbf', quote: 'Served by U1, U2, U4, U5 and all S-Bahn lines.' }],
      }),
    },
    phase1: phase1([{ url: 'https://www.mvg.de/hbf', labels: [RAIL] }]),
  }),
  row(2, 'st-2', null, {
    kept: {
      [RAIL]: kept(RAIL, {
        value: 'S-Bahn',
        web: 'S-Bahn trunk line and regional trains',
        evidence: [{ source: 'web', url: 'https://www.s-bahn-muenchen.de/ostbahnhof', quote: 'All S-Bahn lines stop at Ostbahnhof.' }],
      }),
    },
  }),
  row(3, 'sm-1', 'https://viktualien-markthalle.de', {
    kept: {
      [PRODUCE]: kept(PRODUCE, {
        value: 'good',
        mixed: true,
        basis: 'web_and_reviews',
        web: 'praised for its fruit and vegetable stalls',
        reviews: 'good (4 reviews), mixed (2)',
        evidence: [{ source: 'google_reviews', url: null, quote: 'Best tomatoes in the area, though pricey.' }],
      }),
    },
  }),
  row(3, 'sm-2', null, {
    unresolved: { [PRODUCE]: 'verification_unmet' },
    phase1: phase1([{ url: null, kind: 'google_reviews', labels: [PRODUCE] }], { [PRODUCE]: 'ok' }),
  }),
]

export type R1Kind = 'running' | 'needs_answers' | 'finished' | 'failed'
export type R2Kind = 'running' | 'progress' | 'finished' | 'finished_empty' | 'failed'
export type R3Kind = R2Kind

/** An R1 run body as the endpoints send it, under the given id. */
export function r1Body(kind: R1Kind, runId: string, retryable = true) {
  const body =
    kind === 'running'
      ? BODY.running
      : kind === 'needs_answers'
        ? BODY.paused
        : kind === 'finished'
          ? BODY.finished
          : BODY.failed(retryable)
  return { ...body, run_id: runId }
}

/** An R2 run body under the given id, naming its R1 run, origin and radius. */
export function r2Body(kind: R2Kind, runId: string, r1RunId: string, retryable = true) {
  const base = { run_id: runId, r1_run_id: r1RunId, origin: DEV_ORIGIN, radius_km: DEV_RADIUS_KM }
  switch (kind) {
    case 'running':
      return { ...base, status: 'running' }
    case 'progress':
      return { ...base, status: 'running', completed_step: 'discovery' }
    case 'finished':
      return { ...base, status: 'finished', result: DEV_R2_RESULT }
    case 'finished_empty':
      return { ...base, status: 'finished', result: {} }
    case 'failed':
      return { ...base, status: 'failed', retryable }
  }
}

/** An R3 run body under the given id, naming its R2 run. */
export function r3Body(kind: R3Kind, runId: string, r2RunId: string, retryable = true) {
  const base = { run_id: runId, r2_run_id: r2RunId }
  switch (kind) {
    case 'running':
      return { ...base, status: 'running' }
    case 'progress':
      return { ...base, status: 'running', completed_step: 'discovery_batch' }
    case 'finished':
      return { ...base, status: 'finished', result: DEV_R3_ROWS }
    case 'finished_empty':
      return { ...base, status: 'finished', result: [] }
    case 'failed':
      return { ...base, status: 'failed', retryable }
  }
}
