/**
 * Interaction state of the finished places metrics page.
 *
 * Data path: useR3Run (live run + R1/R2 context) → buildPlacesMetrics() → this hook →
 * rankPlaces() per category (once) → this hook's state (selection, filter, sort, pages, open
 * rail cards) → view-model builders in utils → MetricPanel / PlacesRail / CategoryWorkspace.
 * Mounted only once a run has finished, with at least one category.
 */
import { useCallback, useMemo, useState } from 'react'

import type {
  CategoryKey,
  PlaceFilter,
  PlacesMetricsResult,
  RankedPlace,
  Selection,
  SortMode,
} from '@/features/places-metrics/types/placesMetrics'
import { filterLabel, isNearest, modeOf, orderForSort, rankPlaces, sameFilter } from '@/features/places-metrics/utils/fit'
import { buildMetricCard } from '@/features/places-metrics/utils/metricCards'
import { pageWindow } from '@/features/places-metrics/utils/paging'
import { buildRailGroups } from '@/features/places-metrics/utils/rail'
import { buildReceipt } from '@/features/places-metrics/utils/receipt'
import { buildColumnHeads, buildTableRows, MODE_WORD } from '@/features/places-metrics/utils/requirementTable'

const CARDS_PER_PAGE = 3
const NEEDS_PER_PAGE = 2

type PageMap = Partial<Record<CategoryKey, number>>

export function usePlacesMetrics(result: PlacesMetricsResult) {
  // Ranking never changes with UI state, so it is computed once.
  const rankedBy = useMemo(() => {
    const map: Record<CategoryKey, RankedPlace[]> = {}
    result.categories.forEach((c) => (map[c.key] = rankPlaces(result.places, c)))
    return map
  }, [result])

  // Open on the first category's best-fitting place, so a proof is visible at once.
  const [selection, setSelection] = useState<Selection>(() => {
    const first = result.categories[0]
    const top = first ? rankedBy[first.key]?.[0] : undefined
    return first && top ? { place: top.place.key, question: first.questions[0].id } : null
  })
  const [lastCategory, setLastCategory] = useState<CategoryKey>(() => result.categories[0]?.key ?? '')
  const [filter, setFilter] = useState<PlaceFilter | null>(null)
  const [sort, setSort] = useState<SortMode>('fit')
  const [cardPage, setCardPage] = useState(0)
  const [needsPages, setNeedsPages] = useState<PageMap>({})
  const [columnPages, setColumnPages] = useState<PageMap>({})
  // null until the renter toggles a rail card: then the active category is the open one.
  const [railOpen, setRailOpen] = useState<Partial<Record<CategoryKey, boolean>> | null>(null)

  const placeCategory = useCallback(
    (placeKey: string) => result.places.find((p) => p.key === placeKey)?.category ?? null,
    [result],
  )

  const activeKey: CategoryKey = (selection && placeCategory(selection.place)) || lastCategory
  const activeCategory = result.categories.find((c) => c.key === activeKey) ?? result.categories[0]
  const openMap = useMemo(() => railOpen ?? { [activeKey]: true }, [railOpen, activeKey])

  /* ---------- Actions ---------- */

  /** Open a place's proof (first need), or close it when it is already open. */
  const togglePlace = useCallback(
    (placeKey: string) => {
      const ck = placeCategory(placeKey)
      const cat = result.categories.find((c) => c.key === ck)
      if (!ck || !cat) return
      setSelection((cur) => (cur?.place === placeKey ? null : { place: placeKey, question: cat.questions[0].id }))
      setLastCategory(ck)
    },
    [placeCategory, result],
  )

  const pickQuestion = useCallback((placeKey: string, questionId: string) => {
    setSelection({ place: placeKey, question: questionId })
  }, [])

  const closeReceipt = useCallback(() => {
    setLastCategory(activeKey)
    setSelection(null)
  }, [activeKey])

  /** Apply a filter, or clear it when the same one is tapped again (null always clears). */
  const toggleFilter = useCallback((next: PlaceFilter | null) => {
    setFilter((cur) => (next === null || sameFilter(cur, next) ? null : next))
  }, [])

  const clearFilter = useCallback(() => setFilter(null), [])

  const pageNeeds = useCallback((ck: CategoryKey, start: number) => setNeedsPages((m) => ({ ...m, [ck]: start })), [])
  const pageColumns = useCallback((ck: CategoryKey, start: number) => setColumnPages((m) => ({ ...m, [ck]: start })), [])

  const toggleRailCard = useCallback(
    (ck: CategoryKey, openNow: boolean) => setRailOpen((cur) => ({ ...(cur ?? { [activeKey]: true }), [ck]: !openNow })),
    [activeKey],
  )

  /* ---------- Metric panel ---------- */

  const cards = useMemo(
    () => result.categories.map((c) => buildMetricCard(c, rankedBy[c.key], filter)),
    [result, rankedBy, filter],
  )
  const cardWindow = pageWindow(cardPage, cards.length, CARDS_PER_PAGE, 'Categories')
  const shownCards = cards.slice(cardWindow.start, cardWindow.end).map((card) => {
    const needs = pageWindow(needsPages[card.key] ?? 0, card.needs.length, NEEDS_PER_PAGE, 'Needs')
    return { card, needsWindow: needs, shownNeeds: card.needs.slice(needs.start, needs.end) }
  })

  /* ---------- Rail ---------- */

  const rail = useMemo(
    () => buildRailGroups(result.categories, rankedBy, filter, openMap, selection?.place ?? null),
    [result, rankedBy, filter, openMap, selection],
  )
  const railTitle = filter === null ? `All ${result.places.length} places` : filterLabel(filter, result.categories)
  const railSub = filter === null ? 'Sorted by fit, then nearest.' : 'Only these places are listed. Pick one to see its answers and proof.'
  const filterHint =
    filter === null
      ? 'Tap a count or a segment to list those places in the rail below.'
      : `Listing ${filterLabel(filter, result.categories)} in the rail below. Tap it again to show everything.`

  /* ---------- Workspace: the active category's table and receipt ---------- */

  const ranked = rankedBy[activeCategory.key] ?? []
  const columns = pageWindow(columnPages[activeCategory.key] ?? 0, activeCategory.questions.length, NEEDS_PER_PAGE, 'Needs')
  const visibleQuestions = activeCategory.questions.slice(columns.start, columns.end)
  const openPlace = selection ? ranked.find((r) => r.place.key === selection.place) ?? null : null

  const workspace = {
    category: activeCategory,
    timeLabel: `by ${MODE_WORD[modeOf(sort)]}`,
    columns,
    heads: buildColumnHeads(visibleQuestions, columns.start, activeCategory, ranked),
    rows: buildTableRows(orderForSort(ranked, sort), activeCategory, visibleQuestions, sort, selection?.place ?? null, filter),
    receipt:
      openPlace && selection
        ? buildReceipt(openPlace, activeCategory, selection.question, sort, isNearest(openPlace, ranked))
        : null,
  }

  return {
    address: result.address,
    checkedOn: result.checkedOn,
    panel: { cardWindow, shownCards, filterHint },
    rail: { groups: rail, title: railTitle, sub: railSub, filtered: filter !== null },
    workspace,
    sort,
    actions: {
      togglePlace,
      pickQuestion,
      closeReceipt,
      toggleFilter,
      clearFilter,
      setSort,
      setCardPage,
      pageNeeds,
      pageColumns,
      toggleRailCard,
    },
  }
}

export type PlacesMetricsState = ReturnType<typeof usePlacesMetrics>
