/**
 * How well a place fits the renter's needs: per-question statuses, tier, ranking, filters and
 * travel-time ordering. Pure functions shared by every section of the page.
 */
import type {
  Category,
  Place,
  PlaceFilter,
  RankedPlace,
  SortMode,
  Status,
  Tier,
  TravelMode,
} from '@/features/places-metrics/types/placesMetrics'

export const STATUSES: Status[] = ['y', 'l', 'n', 'u']

/** What each status means to the renter, in the page's own words. */
export const STATUS_LABEL: Record<Status, string> = {
  y: 'Fits your need',
  l: 'Opinion differs',
  n: 'Missing',
  u: 'No info',
}

export function countStatuses(statuses: Status[]): Record<Status, number> {
  const counts: Record<Status, number> = { y: 0, l: 0, n: 0, u: 0 }
  statuses.forEach((s) => counts[s]++)
  return counts
}

/** Meets every need → 0, some → 1, nothing confirmed → 3, otherwise none → 2. */
export function tierOf(statuses: Status[]): Tier {
  const c = countStatuses(statuses)
  if (c.y === statuses.length) return 0
  if (c.y > 0) return 1
  if (c.u === statuses.length) return 3
  return 2
}

/** Tie-breaker inside a tier: fits first, then differing opinions, then open questions. */
function scoreOf(statuses: Status[]): number {
  const c = countStatuses(statuses)
  return c.y * 100 + c.l * 10 + c.u
}

/** A category's places with their statuses, best fit first, then nearest on foot. */
export function rankPlaces(places: Place[], category: Category): RankedPlace[] {
  return places
    .filter((p) => p.category === category.key)
    .map((place) => {
      const statuses = category.questions.map((q) => place.answers[q.id].status)
      return { place, statuses, tier: tierOf(statuses), score: scoreOf(statuses) }
    })
    .sort((a, b) => a.tier - b.tier || b.score - a.score || sortMinutes(a.place, 'walk') - sortMinutes(b.place, 'walk'))
}

/** Minutes by a mode; null when there is no route that way. */
export function travelMinutes(place: Place, mode: TravelMode): number | null {
  return place.travel[mode]
}

/** For ordering: a place with no route sorts after every place with one. */
function sortMinutes(place: Place, mode: TravelMode): number {
  return place.travel[mode] ?? Number.POSITIVE_INFINITY
}

/** The travel mode a sort implies; "Best fit" shows walking times. */
export function modeOf(sort: SortMode): TravelMode {
  return sort === 'fit' ? 'walk' : sort
}

/** Order for the table: ranked order for "Best fit", otherwise quickest by the mode. */
export function orderForSort(ranked: RankedPlace[], sort: SortMode): RankedPlace[] {
  if (sort === 'fit') return ranked
  return ranked
    .slice()
    .sort((a, b) => sortMinutes(a.place, sort) - sortMinutes(b.place, sort) || a.tier - b.tier || b.score - a.score)
}

/** Rail summary: "2 of 4 met · 1 leaning · 1 open". */
export function railFitText(statuses: Status[]): string {
  const c = countStatuses(statuses)
  const parts = [`${c.y} of ${statuses.length} met`]
  if (c.l) parts.push(`${c.l} leaning`)
  if (c.u) parts.push(`${c.u} open`)
  return parts.join(' · ')
}

/** Fit pill text; `long` adds "Fits" before the partial count (used in the receipt). */
export function fitPillText(rp: RankedPlace, long = false): string {
  if (rp.tier === 0) return 'Fits all'
  if (rp.tier === 2) return 'Fits none'
  if (rp.tier === 3) return 'No info'
  const fits = countStatuses(rp.statuses).y
  return `${long ? 'Fits ' : ''}${fits} of ${rp.statuses.length}`
}

export function isQuestionFilter(f: PlaceFilter): f is Extract<PlaceFilter, { question: string }> {
  return 'question' in f
}

/** Whether a ranked place belongs to the active filter. */
export function matchesFilter(rp: RankedPlace, category: Category, filter: PlaceFilter): boolean {
  if (filter.category !== category.key) return false
  if (isQuestionFilter(filter)) {
    const qi = category.questions.findIndex((q) => q.id === filter.question)
    return rp.statuses[qi] === filter.status
  }
  return rp.tier === filter.tier
}

/** True when a filter is on and this place is outside it. */
export function isDimmed(rp: RankedPlace, category: Category, filter: PlaceFilter | null): boolean {
  return filter !== null && !matchesFilter(rp, category, filter)
}

export function sameFilter(a: PlaceFilter | null, b: PlaceFilter): boolean {
  if (a === null || a.category !== b.category) return false
  if (isQuestionFilter(a) && isQuestionFilter(b)) return a.question === b.question && a.status === b.status
  if (!isQuestionFilter(a) && !isQuestionFilter(b)) return a.tier === b.tier
  return false
}

const QUESTION_FILTER_WORD: Record<Status, string> = { y: 'fits your need', l: 'opinion differs', n: 'missing', u: 'no info' }
const TIER_FILTER_WORD = ['Meet all', 'Meet some', 'Meet none', 'Couldn’t confirm']

/** Rail heading for a filter: "Gyms · Platform: missing" or "Cafés · Meet all". */
export function filterLabel(filter: PlaceFilter, categories: Category[]): string {
  const category = categories.find((c) => c.key === filter.category)
  if (!category) return ''
  if (isQuestionFilter(filter)) {
    const q = category.questions.find((x) => x.id === filter.question)
    return `${category.name} · ${q?.short ?? ''}: ${QUESTION_FILTER_WORD[filter.status]}`
  }
  return `${category.name} · ${TIER_FILTER_WORD[filter.tier]}`
}

/** Places sharing the category's shortest walk are tagged "Nearest" (never one with no walk route). */
export function isNearest(rp: RankedPlace, ranked: RankedPlace[]): boolean {
  const walks = ranked.map((r) => r.place.travel.walk).filter((m): m is number => m !== null)
  return rp.place.travel.walk !== null && rp.place.travel.walk === Math.min(...walks)
}
