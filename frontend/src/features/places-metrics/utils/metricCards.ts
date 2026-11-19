/**
 * View model for one category card in "Do nearby places really fit?": the three overview
 * bars (total / fit all / fit some) and one donut per need.
 */
import type { Category, PlaceFilter, RankedPlace, Status, Tier } from '@/features/places-metrics/types/placesMetrics'
import { isQuestionFilter, STATUS_LABEL, STATUSES } from '@/features/places-metrics/utils/fit'

export type OverviewRow = {
  /** t = total (neutral), y = fit all, l = fit some */
  kind: 't' | 'y' | 'l'
  label: string
  count: number
  width: string
  delay: string
  /** Filter this row applies; null for "Total places", which clears the filter. */
  tier: Tier | null
  active: boolean
  aria: string
}

export type DonutArc = { dash: string; offset: string; hidden: boolean }

export type NeedSegment = { status: Status; count: number; label: string; active: boolean; aria: string }

export type NeedSummary = {
  questionId: string
  short: string
  want: string
  fits: number
  /** The need the fewest places meet (ties: more misses). Tagged "lacks". */
  weak: boolean
  arcs: Record<Status, DonutArc>
  segments: NeedSegment[]
  donutAria: string
}

export type MetricCardView = {
  key: Category['key']
  name: string
  color: string
  icon: string
  total: number
  overview: OverviewRow[]
  needs: NeedSummary[]
}

const SEGMENT_WORDS: Record<Status, string> = {
  y: 'fit your need',
  l: 'have differing opinions',
  n: 'are missing',
  u: 'have no info',
}

/** Arcs on a 100-unit circle, each shortened to leave a soft gap between slices. */
function donutArcs(counts: Record<Status, number>, total: number): Record<Status, DonutArc> {
  let at = 0
  const arcs = {} as Record<Status, DonutArc>
  STATUSES.forEach((k) => {
    const len = total ? (counts[k] / total) * 100 : 0
    arcs[k] = { dash: `${Math.max(0.01, len - 7).toFixed(2)} 100`, offset: (-(at + 3.5)).toFixed(2), hidden: len <= 0 }
    at += len
  })
  return arcs
}

function tierFilterOn(filter: PlaceFilter | null, category: Category, tier: Tier): boolean {
  return !!filter && filter.category === category.key && !isQuestionFilter(filter) && filter.tier === tier
}

function overviewRows(category: Category, ranked: RankedPlace[], filter: PlaceFilter | null): OverviewRow[] {
  const total = ranked.length
  const inTier = (t: Tier) => ranked.filter((r) => r.tier === t)
  const pct = (n: number) => `${total ? (n / total) * 100 : 0}%`
  const rows: { kind: OverviewRow['kind']; label: string; tier: Tier | null; members: RankedPlace[] }[] = [
    { kind: 't', label: 'Total places', tier: null, members: ranked },
    { kind: 'y', label: 'Fit all needs', tier: 0, members: inTier(0) },
    { kind: 'l', label: 'Fit some needs', tier: 1, members: inTier(1) },
  ]
  return rows.map((row, i) => {
    const n = row.members.length
    const active = row.tier !== null && tierFilterOn(filter, category, row.tier)
    const names = row.members.map((r) => r.place.name).join(', ')
    const aria =
      row.tier === null
        ? `${category.name}: ${total} places in total. Tap to show every place.`
        : `${category.name}: ${n} of ${total} places ${row.tier === 0 ? 'meet all asks' : 'meet some asks, not all'}${n ? `: ${names}` : ''}. ${active ? 'Showing them, tap to show all.' : 'Tap to list them.'}`
    return { kind: row.kind, label: row.label, count: n, width: pct(n), delay: `${i * 110 + 160}ms`, tier: row.tier, active, aria }
  })
}

function needSummaries(category: Category, ranked: RankedPlace[], filter: PlaceFilter | null): NeedSummary[] {
  const total = ranked.length
  const needs = category.questions.map((q, qi) => {
    const counts: Record<Status, number> = { y: 0, l: 0, n: 0, u: 0 }
    const names: Record<Status, string[]> = { y: [], l: [], n: [], u: [] }
    ranked.forEach((r) => {
      counts[r.statuses[qi]]++
      names[r.statuses[qi]].push(r.place.name)
    })
    const segments = STATUSES.filter((k) => counts[k] > 0).map((k) => {
      const active =
        !!filter && filter.category === category.key && isQuestionFilter(filter) && filter.question === q.id && filter.status === k
      return {
        status: k,
        count: counts[k],
        label: STATUS_LABEL[k],
        active,
        aria: `${category.name}, ${q.short}: ${counts[k]} of ${total} ${SEGMENT_WORDS[k]}: ${names[k].join(', ')}. ${active ? 'Showing them, tap to show all.' : 'Tap to list them.'}`,
      }
    })
    return {
      questionId: q.id,
      short: q.short,
      want: q.want,
      fits: counts.y,
      misses: counts.n,
      weak: false,
      arcs: donutArcs(counts, total),
      segments,
      donutAria: `${category.name}, ${q.short}: ${counts.y} of ${total} fit your need, ${counts.l} have differing opinions, ${counts.n} missing, ${counts.u} no info`,
    }
  })
  // Mark the lagging need: fewest fits (only if not everyone fits), ties broken by more misses.
  let weakest: { id: string; fits: number; misses: number } | null = null
  for (const n of needs) {
    if (n.fits < total && (weakest === null || n.fits < weakest.fits || (n.fits === weakest.fits && n.misses > weakest.misses))) {
      weakest = { id: n.questionId, fits: n.fits, misses: n.misses }
    }
  }
  const weakId = weakest?.id ?? null
  return needs.map((n) => ({
    questionId: n.questionId,
    short: n.short,
    want: n.want,
    fits: n.fits,
    weak: n.questionId === weakId,
    arcs: n.arcs,
    segments: n.segments,
    donutAria: n.donutAria,
  }))
}

export function buildMetricCard(category: Category, ranked: RankedPlace[], filter: PlaceFilter | null): MetricCardView {
  return {
    key: category.key,
    name: category.name,
    color: category.color,
    icon: category.icon,
    total: ranked.length,
    overview: overviewRows(category, ranked, filter),
    needs: needSummaries(category, ranked, filter),
  }
}
