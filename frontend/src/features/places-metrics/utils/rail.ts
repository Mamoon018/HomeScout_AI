/**
 * View model for the "All places" rail: one card per category, each listing its places with
 * a bead per need and a fit tag. A filter narrows it to one category and its matching places.
 */
import type { Category, CategoryKey, PlaceFilter, RankedPlace, Status } from '@/features/places-metrics/types/placesMetrics'
import { matchesFilter, railFitText } from '@/features/places-metrics/utils/fit'

export type RailRow = {
  key: string
  name: string
  walk: string
  beads: { status: Status; tip: string }[]
  fitText: string
  fitsAll: boolean
  selected: boolean
}

export type RailGroup = {
  key: CategoryKey
  name: string
  color: string
  icon: string
  open: boolean
  rows: RailRow[]
}

export function buildRailGroups(
  categories: Category[],
  rankedBy: Record<CategoryKey, RankedPlace[]>,
  filter: PlaceFilter | null,
  openMap: Partial<Record<CategoryKey, boolean>>,
  selectedPlace: string | null,
): RailGroup[] {
  return categories
    .filter((c) => filter === null || c.key === filter.category)
    .map((c) => ({
      key: c.key,
      name: c.name,
      color: c.color,
      icon: c.icon,
      // A filter always opens its category so the matching places are visible.
      open: filter !== null || !!openMap[c.key],
      rows: rankedBy[c.key]
        .filter((rp) => filter === null || matchesFilter(rp, c, filter))
        .map((rp) => ({
          key: rp.place.key,
          name: rp.place.name,
          walk: rp.place.travel.walk === null ? 'no route' : `${rp.place.travel.walk} min`,
          beads: c.questions.map((q, i) => ({ status: rp.statuses[i], tip: `${q.short}: ${rp.place.answers[q.id].value}` })),
          fitText: railFitText(rp.statuses),
          fitsAll: rp.tier === 0,
          selected: rp.place.key === selectedPlace,
        })),
    }))
}
