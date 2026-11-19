/**
 * View model for the requirement table (Matrix C): one column per visible need with its
 * fit tally, one row per place with each answer, its basis, and a fit pill.
 */
import type {
  Answer,
  Category,
  PlaceFilter,
  Question,
  RankedPlace,
  SortMode,
  Status,
  TravelMode,
} from '@/features/places-metrics/types/placesMetrics'
import { countStatuses, fitPillText, isDimmed, modeOf, STATUS_LABEL, STATUSES } from '@/features/places-metrics/utils/fit'

export type ColumnHead = {
  number: number
  short: string
  want: string
  bar: { status: Status; count: number }[]
  tally: string
}

export type TableCell = { status: Status; value: string; basis: string; label: string }

export type TableRow = {
  key: string
  name: string
  time: string
  /** Walk distance; null when R2 had no walk route. */
  distance: string | null
  selected: boolean
  dimmed: boolean
  tier: RankedPlace['tier']
  fitText: string
  beads: Status[]
  cells: TableCell[]
}

/** Short word for each mode in table copy: "14 min walk", "time by bike". */
export const MODE_WORD: Record<TravelMode, string> = { walk: 'walk', cycle: 'bike', drive: 'drive', transit: 'transit' }

/** Each visible need's header: number, wording, what the renter wants and a stacked tally bar. */
export function buildColumnHeads(questions: Question[], firstNumber: number, category: Category, ranked: RankedPlace[]): ColumnHead[] {
  return questions.map((q, i) => {
    const qi = category.questions.findIndex((x) => x.id === q.id)
    const counts = countStatuses(ranked.map((r) => r.statuses[qi]))
    return {
      number: firstNumber + i + 1,
      short: q.short,
      want: q.want,
      bar: STATUSES.filter((k) => counts[k] > 0).map((k) => ({ status: k, count: counts[k] })),
      tally: `${counts.y} of ${ranked.length} fit`,
    }
  })
}

/** What an answer rests on, in mono under the value: "web + moderate (2 reviews)", "nothing online". */
export function answerBasis(a: Answer): string {
  if (a.status === 'u') {
    if (a.reason === 'thin') return 'mentions only · not enough'
    if (a.reason === 'failed') return 'check failed'
    if (a.reason === 'search_failed') return 'search failed'
    return 'nothing online'
  }
  return a.voices.map((v) => (v.kind === 'w' ? 'web' : v.kind === 's' ? 'official site' : v.text)).join(' + ')
}

export function buildTableRows(
  ordered: RankedPlace[],
  category: Category,
  questions: Question[],
  sort: SortMode,
  selectedPlace: string | null,
  filter: PlaceFilter | null,
): TableRow[] {
  const mode = modeOf(sort)
  return ordered.map((rp) => {
    const p = rp.place
    const estimate = mode === 'transit' && p.travel.transitEstimate
    const min = p.travel[mode]
    return {
      key: p.key,
      name: p.name,
      time: min === null ? `no ${MODE_WORD[mode]} route` : `${estimate ? '~' : ''}${min} min ${MODE_WORD[mode]}${estimate ? ' est.' : ''}`,
      distance: p.travel.distance,
      selected: p.key === selectedPlace,
      dimmed: isDimmed(rp, category, filter),
      tier: rp.tier,
      fitText: fitPillText(rp),
      beads: rp.statuses,
      cells: questions.map((q) => {
        const a = p.answers[q.id]
        return { status: a.status, value: a.status === 'u' ? 'No info' : a.value, basis: answerBasis(a), label: STATUS_LABEL[a.status] }
      }),
    }
  })
}
