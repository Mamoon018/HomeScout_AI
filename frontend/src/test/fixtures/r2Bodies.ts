import { RUN_ID as R1_RUN_ID } from '@/test/fixtures/r1Bodies'

export { R1_RUN_ID }
export const R2_RUN_ID = '7c4d9e2a-0000-4000-8000-000000000000'

type Route = { distance_km: number; duration_min: number }
const route = (min: number, km: number): Route => ({ duration_min: min, distance_km: km })

/** One place record as the status endpoint sends it (`exclude_none`: unknown fields are absent). */
export function record(categoryId: number, node: string, placeId: string, over: Record<string, unknown> = {}) {
  return {
    category_id: categoryId,
    taxonomy_node: node,
    depth: 'operating_details',
    place_id: placeId,
    name: `Place ${placeId}`,
    google_maps_uri: `https://maps.google.com/?cid=${placeId}`,
    rating: 4.4,
    review_volume: 120,
    price_level: 2,
    routing: { walk: route(6, 0.4), cycle: route(2, 0.5), drive: route(2, 0.6) },
    transit: { duration_min: 8, distance_km: 0.6, used_fallback: false },
    ...over,
  }
}

const WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(
  (d) => `${d}: 7:00 AM – 10:00 PM`,
)

/** Plan categories in `r1Plan`: 2 transit_station, 3 supermarket. */
export const R2_BODY = {
  running: { run_id: R2_RUN_ID, status: 'running' },
  runningAfterDiscovery: { run_id: R2_RUN_ID, status: 'running', completed_step: 'discovery' },
  finished: {
    run_id: R2_RUN_ID,
    status: 'finished',
    result: {
      '2': {
        'st-1': record(2, 'transit_station', 'st-1', { name: 'Hauptbahnhof' }),
        'st-2': record(2, 'transit_station', 'st-2', {
          name: 'Ostend',
          routing: { walk: route(13, 1.0), cycle: route(5, 1.1), drive: route(4, 1.3) },
          transit: { duration_min: 15, distance_km: 1.2, used_fallback: true },
        }),
      },
      '3': {
        'sm-1': record(3, 'supermarket', 'sm-1', {
          name: 'Markthalle Nord',
          opening_hours: { weekday_descriptions: WEEK },
        }),
      },
    },
  },
  /** Nothing found for any category. */
  finishedEmpty: { run_id: R2_RUN_ID, status: 'finished', result: {} },
  /** A sparse record: only what Google always returns, no routes, no name. */
  finishedSparse: {
    run_id: R2_RUN_ID,
    status: 'finished',
    result: { '3': { 'sm-9': { category_id: 3, taxonomy_node: 'supermarket', depth: 'basic_profile', place_id: 'sm-9', routing: {} } } },
  },
  failed: (retryable: boolean, completedStep?: 'discovery') => ({
    run_id: R2_RUN_ID,
    status: 'failed',
    ...(completedStep ? { completed_step: completedStep } : {}),
    retryable,
  }),
}

export const R2_ERROR = {
  notFound: { error: 'Run not found' },
  r1NotFound: { error: 'Finished requirement interpretation run not found' },
  storeDown: { error: 'Run storage is unavailable' },
  rejected: { error: 'radius_km must be greater than 0' },
  conflict: (status: string, retryable?: boolean) => ({
    error: 'The run cannot be retried',
    run_id: R2_RUN_ID,
    status,
    ...(retryable === undefined ? {} : { retryable }),
  }),
}
