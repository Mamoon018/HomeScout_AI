import type { CategoryMetricPlan, ExtractionOutput } from '@/features/r1-interpretation/types/r1'
import { taxonomyLabel } from '@/features/r1-interpretation/utils/present'
import { taxonomyStyle } from '@/features/r1-interpretation/utils/taxonomyStyle'
import type { Family } from '@/features/r1-interpretation/utils/place-layout'
import type { CategoryResult, Leg, Place, TravelMode } from '@/features/r2-proximity/types/r2'

/** Discovery's cap per category (`DISCOVERY_MAX_RESULTS`). A full category may have more. */
export const DISCOVERY_CAP = 10

/** One colour per category, in the page's category order. Deep tones that hold up on glass. */
export const CATEGORY_COLORS = [
  '#b35a12',
  '#1d6fa3',
  '#55761f',
  '#1f7a80',
  '#8b4a7a',
  '#9a6b00',
  '#3d5f8f',
  '#7a5230',
] as const

/** A category as the page shows it: the R1 plan's order and words joined to R2's places. */
export type PageCategory = {
  id: number
  node: string
  label: string
  /** The renter's words ("You asked for …") or why it was added. Empty when R1 is unknown. */
  note: string
  inferred: boolean
  color: string
  family: Family
  places: Place[]
  capped: boolean
}

/** The parts of R1's plan the page reads: order and kind of place. */
export type PlanEntry = Pick<CategoryMetricPlan, 'category_id' | 'taxonomy_node'>
/** The parts of R1's extraction the page reads: what the renter asked for, in their words. */
export type AskedCategories = {
  explicit_categories: Pick<ExtractionOutput['explicit_categories'][number], 'category_id' | 'name'>[]
}

/**
 * Category order and wording come from the R1 run (its plan lists every category, including
 * those R2 found nothing for). Without it, the R2 result alone is used, in id order.
 */
export function pageCategories(
  result: Map<number, CategoryResult>,
  plan: PlanEntry[] | null,
  extraction: AskedCategories | null,
): PageCategory[] {
  const order: { id: number; node: string }[] = plan
    ? plan.map((p) => ({ id: p.category_id, node: p.taxonomy_node }))
    : [...result.values()]
        .sort((a, b) => a.categoryId - b.categoryId)
        .map((c) => ({ id: c.categoryId, node: c.taxonomyNode }))
  // A category R2 returned that the plan does not list still shows, after the planned ones.
  for (const c of result.values()) {
    if (!order.some((o) => o.id === c.categoryId)) {
      order.push({ id: c.categoryId, node: c.taxonomyNode })
    }
  }
  return order.map(({ id, node }, i) => {
    const places = result.get(id)?.places ?? []
    const asked = extraction?.explicit_categories.find((c) => c.category_id === id)
    const inferred = extraction !== null && asked === undefined
    return {
      id,
      node,
      label: taxonomyLabel(node),
      note: asked
        ? `You asked for “${asked.name}”`
        : inferred
          ? 'Not in your brief. Added because it usually matters.'
          : '',
      inferred,
      color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
      family: taxonomyStyle(node).family,
      places,
      capped: places.length >= DISCOVERY_CAP,
    }
  })
}

export const MODE_LABEL: Record<TravelMode, string> = {
  walk: 'Walk',
  cycle: 'Cycle',
  drive: 'Drive',
  transit: 'Transit',
}

/** "on foot", "by bike": how a mode reads after a time or a count. */
export const MODE_BY: Record<TravelMode, string> = {
  walk: 'on foot',
  cycle: 'by bike',
  drive: 'by car',
  transit: 'by transit',
}

/** "6 min walk", "6 min by bike". */
export function minutesPhrase(minutes: number, mode: TravelMode): string {
  return mode === 'walk' ? `${minutes} min walk` : `${minutes} min ${MODE_BY[mode]}`
}

/** Google PriceLevel: 1 free, 2 inexpensive … 5 very expensive. */
export function priceLabel(level: number | null): string | null {
  if (level === null) {
    return null
  }
  if (level === 1) {
    return 'Free'
  }
  return level >= 2 && level <= 5 ? '€'.repeat(level - 1) : null
}

/**
 * Today's line from Google's weekday descriptions (Monday first), without the day name:
 * "Monday: 7:00 AM – 10:00 PM" → "Today 7:00 AM – 10:00 PM".
 */
export function todayHours(lines: string[], now: Date = new Date()): string | null {
  if (lines.length !== 7) {
    return null
  }
  const line = lines[(now.getDay() + 6) % 7]
  const colon = line.indexOf(':')
  const hours = (colon >= 0 ? line.slice(colon + 1) : line).trim()
  if (!hours) {
    return null
  }
  return /open 24 hours/i.test(hours) ? 'Open 24 hours' : /closed/i.test(hours) ? 'Closed today' : `Today ${hours}`
}

export function nearest(c: PageCategory, mode: TravelMode): Place | null {
  let best: Place | null = null
  for (const p of c.places) {
    const m = p.travel[mode].minutes
    if (m !== null && (best === null || m < (best.travel[mode].minutes ?? Infinity))) {
      best = p
    }
  }
  return best
}

/** "2 km", "1.5 km". */
export function formatKm(km: number): string {
  return `${Number.isInteger(km) ? km : km.toFixed(1)} km`
}

/** One plain sentence comparing transit and cycling with walking. Facts, not a verdict. */
export function modeNote(closest: Record<TravelMode, Leg>): string {
  const w = closest.walk.minutes
  const c = closest.cycle.minutes
  const t = closest.transit.minutes
  if (w === null) {
    return t === null ? 'No walking or transit route was found to any of these.' : `No walking route was found; the nearest is ${t} min by transit.`
  }
  let note =
    t === null
      ? 'No transit route was found to any of these.'
      : t >= w
        ? `Transit is no quicker than walking here (${t} vs ${w} min).`
        : `Transit saves ${w - t} min over walking.`
  if (c !== null && w / c >= 2) {
    note += ` Cycling is about ${Math.round(w / c)}× quicker than walking.`
  }
  return note
}
