import type {
  CategoryResult,
  Leg,
  Place,
  PlaceRecordWire,
  R2RunStatus,
  R2RunView,
  R2RunWire,
  TravelMode,
} from '@/features/r2-proximity/types/r2'

const STATUSES: readonly R2RunStatus[] = ['running', 'finished', 'failed']

const NO_LEG: Leg = { minutes: null, km: null, estimated: false }

/**
 * Turns a run body into the view the page reads. Absent fields become null or empty, never
 * invented values. Returns null when the body is not a run at all (no id or an unknown status),
 * or when a finished run carries no result: the page then treats the call as unavailable.
 */
export function normalizeR2Run(wire: R2RunWire | null): R2RunView | null {
  if (!wire || typeof wire.run_id !== 'string') {
    return null
  }
  const status = STATUSES.find((s) => s === wire.status)
  if (!status) {
    return null
  }
  if (status === 'finished' && (wire.result === undefined || wire.result === null)) {
    return null
  }
  return {
    runId: wire.run_id,
    status,
    completedStep: wire.completed_step === 'discovery' ? 'discovery' : null,
    result: status === 'finished' ? normalizeResult(wire.result ?? {}) : null,
    retryable: status === 'failed' ? wire.retryable === true : null,
    // A missing parent never rejects the body: the run's status must still show.
    r1RunId: typeof wire.r1_run_id === 'string' && wire.r1_run_id ? wire.r1_run_id : null,
    origin: normalizeOrigin(wire.origin),
  }
}

function normalizeOrigin(o: R2RunWire['origin']): R2RunView['origin'] {
  const lat = o?.latitude
  const lng = o?.longitude
  return typeof lat === 'number' && Number.isFinite(lat) && typeof lng === 'number' && Number.isFinite(lng)
    ? { latitude: lat, longitude: lng }
    : null
}

function normalizeResult(raw: Record<string, Record<string, PlaceRecordWire>>): Map<number, CategoryResult> {
  const out = new Map<number, CategoryResult>()
  for (const [key, records] of Object.entries(raw)) {
    const categoryId = Number(key)
    if (!Number.isFinite(categoryId)) {
      continue
    }
    const places: Place[] = []
    let taxonomyNode = ''
    let depth = 'basic_profile'
    for (const [placeId, record] of Object.entries(records ?? {})) {
      taxonomyNode ||= record.taxonomy_node ?? ''
      depth = record.depth ?? depth
      places.push(normalizePlace(placeId, categoryId, record))
    }
    places.sort(byWalk)
    out.set(categoryId, { categoryId, taxonomyNode, depth, places })
  }
  return out
}

function normalizePlace(placeId: string, categoryId: number, r: PlaceRecordWire): Place {
  return {
    placeId: r.place_id ?? placeId,
    categoryId,
    // A place with no display name is still a real place: say so rather than drop it.
    name: r.name?.trim() || 'Unnamed place',
    address: r.address ?? null,
    mapsUrl: r.google_maps_uri ?? null,
    rating: typeof r.rating === 'number' ? r.rating : null,
    reviewCount: typeof r.review_volume === 'number' ? r.review_volume : null,
    // 0 is PRICE_LEVEL_UNSPECIFIED: no information, same as absent.
    priceLevel: typeof r.price_level === 'number' && r.price_level > 0 ? r.price_level : null,
    weekdayHours: weekdayLines(r.opening_hours),
    travel: {
      walk: leg(r.routing?.walk),
      cycle: leg(r.routing?.cycle),
      drive: leg(r.routing?.drive),
      transit: r.transit
        ? { ...leg(r.transit), estimated: r.transit.used_fallback === true }
        : NO_LEG,
    },
  }
}

function leg(raw: { distance_km?: number; duration_min?: number } | null | undefined): Leg {
  if (!raw || typeof raw.duration_min !== 'number') {
    return NO_LEG
  }
  return {
    minutes: Math.max(1, Math.round(raw.duration_min)),
    km: typeof raw.distance_km === 'number' ? raw.distance_km : null,
    estimated: false,
  }
}

/** Places `regular_opening_hours` from `Place.to_dict` (snake_case), camelCase tolerated. */
function weekdayLines(hours: Record<string, unknown> | undefined): string[] {
  const lines = hours?.weekday_descriptions ?? hours?.weekdayDescriptions
  return Array.isArray(lines) ? lines.filter((l): l is string => typeof l === 'string') : []
}

function byWalk(a: Place, b: Place): number {
  return minutesOr(a, 'walk') - minutesOr(b, 'walk') || a.name.localeCompare(b.name)
}

function minutesOr(p: Place, mode: TravelMode): number {
  return p.travel[mode].minutes ?? Number.POSITIVE_INFINITY
}
