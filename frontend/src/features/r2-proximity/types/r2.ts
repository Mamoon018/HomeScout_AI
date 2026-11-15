/**
 * R2 (Amenity Search) as the backend sends it, and as the page works with it.
 *
 * The backend serialises with `exclude_none` at every level, so any field that can be None in
 * `PredefinedMetricsRecord` is optional here, and a travel mode with no route may be missing from
 * `routing` entirely. `normalizeR2Run` turns this into `R2RunView`.
 */

/** Travel modes in the fixed order the page always shows them. */
export type TravelMode = 'walk' | 'cycle' | 'drive' | 'transit'
export const TRAVEL_MODES: readonly TravelMode[] = ['walk', 'cycle', 'drive', 'transit']

export type R2RunStatus = 'running' | 'finished' | 'failed'

/** One place record exactly as `GET /api/amenity-search/runs/{id}` returns it. */
export type PlaceRecordWire = {
  category_id?: number
  taxonomy_node?: string
  depth?: string
  place_id?: string
  name?: string
  category?: string
  address?: string
  website?: string
  google_maps_uri?: string
  coordinates?: { latitude?: number; longitude?: number }
  opening_hours?: Record<string, unknown>
  contact_phone?: string
  rating?: number
  review_volume?: number
  price_level?: number
  reviews?: unknown[]
  routing?: Partial<Record<'walk' | 'drive' | 'cycle', { distance_km?: number; duration_min?: number } | null>>
  transit?: { distance_km?: number; duration_min?: number; used_fallback?: boolean } | null
}

export type R2RunWire = {
  run_id?: string
  status?: string
  completed_step?: string
  /** Keyed category_id (a JSON string key) then place_id. */
  result?: Record<string, Record<string, PlaceRecordWire>>
  retryable?: boolean
}

/** One mode's travel to a place. `minutes` and `km` are null when the mode has no route. */
export type Leg = {
  minutes: number | null
  km: number | null
  /** Transit only: the route was estimated (Routes `fallbackInfo`), not looked up. */
  estimated: boolean
}

/** One place, every field present: null when the backend had nothing for it. */
export type Place = {
  placeId: string
  categoryId: number
  name: string
  address: string | null
  mapsUrl: string | null
  rating: number | null
  reviewCount: number | null
  /** Google's PriceLevel enum (1 free … 5 very expensive); null when unknown or unspecified. */
  priceLevel: number | null
  /** Google's localised line per weekday, Monday first; empty when hours were not fetched. */
  weekdayHours: string[]
  travel: Record<TravelMode, Leg>
}

/** One category's places, nearest walk first (no walk route sorts last). */
export type CategoryResult = {
  categoryId: number
  taxonomyNode: string
  depth: string
  places: Place[]
}

export type R2RunView = {
  runId: string
  status: R2RunStatus
  /** `discovery` once places were found; a retry resumes after it. */
  completedStep: 'discovery' | null
  /** Category id → its places. Null unless `status` is `finished`. */
  result: Map<number, CategoryResult> | null
  /** Set when `status` is `failed`: Retry when true, Start again when false. */
  retryable: boolean | null
}

/** Why a call did not give a run, by what the page can do about it. */
export type R2Error =
  /** 422: origin or radius refused. */
  | { kind: 'rejected'; message: string }
  /** 409 on retry: the run is not retryable now. `status` is the run's current status. */
  | { kind: 'conflict'; status: R2RunStatus | null; retryable: boolean | null }
  /** 404: no such run (or no finished R1 run, on start). */
  | { kind: 'not_found' }
  | { kind: 'unauthenticated' }
  | { kind: 'timeout' }
  | { kind: 'network' }
  /** 503 store down, or a body the page cannot read. */
  | { kind: 'unavailable' }

export type R2Result = { ok: true; view: R2RunView } | { ok: false; error: R2Error }

/** What a start needs. Coordinates because no geocoding step exists yet. */
export type StartInput = {
  r1RunId: string
  latitude: number
  longitude: number
  radiusKm: number
}
