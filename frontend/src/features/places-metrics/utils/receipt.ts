/**
 * View model for the in-line receipt: the open place's details, getting-there ribbon,
 * one tab per need, and the verdict with its evidence grouped by source.
 */
import type { Category, Quote, RankedPlace, SortMode, SourceKind, Status, TravelMode } from '@/features/places-metrics/types/placesMetrics'
import { fitPillText, modeOf, STATUS_LABEL } from '@/features/places-metrics/utils/fit'

export type ReceiptMode = { mode: TravelMode; label: string; minutes: string; sub: string; width: string; lead: boolean }

export type ReceiptTab = { questionId: string; short: string; value: string; status: Status; label: string; active: boolean }

/** search = the reason an answer couldn't be confirmed; otherwise a source kind. */
export type EvidenceGroup = {
  kind: 'search' | SourceKind
  title: string
  plain: boolean
  items: { text: string; source: string; url: string | null }[]
}

export type ReceiptView = {
  key: string
  name: string
  nearest: boolean
  tier: RankedPlace['tier']
  fitText: string
  beads: Status[]
  /** Null when R2 had no rating; the stars and count are then left out. */
  rating: string | null
  starWidth: string
  reviewCount: string | null
  price: string | null
  hours: string | null
  site: string | null
  websiteUrl: string | null
  mapsUrl: string | null
  modes: ReceiptMode[]
  tabs: ReceiptTab[]
  question: string
  want: string
  value: string
  status: Status
  statusLine: string
  evidenceTitle: string
  groups: EvidenceGroup[]
  searched: string
}

const MODE_LABEL: Record<TravelMode, string> = { walk: 'Walk', cycle: 'Cycle', drive: 'Drive', transit: 'Transit' }

/** Getting there by every mode; the bar is out of 30 minutes, and the sorted mode leads. */
function modesFor(rp: RankedPlace, sort: SortMode): ReceiptMode[] {
  const t = rp.place.travel
  const lead = modeOf(sort)
  return (['walk', 'cycle', 'drive', 'transit'] as TravelMode[]).map((mode) => {
    const estimate = mode === 'transit' && t.transitEstimate
    const min = t[mode]
    const sub = min === null ? '' : mode === 'walk' ? (t.distance ?? '') : estimate ? 'estimate' : ''
    return {
      mode,
      label: MODE_LABEL[mode],
      minutes: min === null ? 'No route' : `${estimate ? '~' : ''}${min} min`,
      sub,
      width: min === null ? '0%' : `${Math.min(100, (min / 30) * 100)}%`,
      lead: mode === lead,
    }
  })
}

function group(kind: SourceKind, title: string, quotes: Quote[]): EvidenceGroup {
  return { kind, title, plain: false, items: quotes.map((q) => ({ text: q.text, source: q.source, url: q.url })) }
}

export function buildReceipt(rp: RankedPlace, category: Category, questionId: string, sort: SortMode, nearest: boolean): ReceiptView {
  const p = rp.place
  const q = category.questions.find((x) => x.id === questionId) ?? category.questions[0]
  const a = p.answers[q.id]
  const unconfirmed = a.status === 'u'

  // Evidence: the search's reason when unconfirmed; otherwise web, official site, then reviews.
  const groups: EvidenceGroup[] = []
  if (unconfirmed) {
    groups.push({ kind: 'search', title: 'What the search turned up', plain: true, items: [{ text: a.reasonText ?? '', source: '', url: null }] })
  } else {
    const of = (k: SourceKind) => a.quotes.filter((x) => x.kind === k)
    if (of('w').length) groups.push(group('w', 'Web sources', of('w')))
    if (of('s').length) groups.push(group('s', 'Official site', of('s')))
    if (of('r').length) groups.push(group('r', `Google reviews · ${of('r').length}`, of('r')))
  }

  const statusLine =
    a.status === 'l' ? `Opinion differs, leans toward ${a.value.replace(/^Leans /, '').toLowerCase()}` : STATUS_LABEL[a.status]

  return {
    key: p.key,
    name: p.name,
    nearest,
    tier: rp.tier,
    fitText: fitPillText(rp, true),
    beads: rp.statuses,
    rating: p.rating === null ? null : p.rating.toFixed(1),
    starWidth: `${((p.rating ?? 0) / 5) * 100}%`,
    reviewCount: p.reviewCount,
    price: p.price,
    hours: p.hours,
    site: p.site,
    websiteUrl: p.websiteUrl,
    mapsUrl: p.mapsUrl,
    modes: modesFor(rp, sort),
    tabs: category.questions.map((x) => {
      const ax = p.answers[x.id]
      return { questionId: x.id, short: x.short, value: ax.status === 'u' ? 'No info' : ax.value, status: ax.status, label: STATUS_LABEL[ax.status], active: x.id === q.id }
    }),
    question: q.text,
    want: q.want,
    value: unconfirmed ? 'No info' : a.value,
    status: a.status,
    statusLine,
    evidenceTitle: unconfirmed ? 'What I found' : a.status === 'l' ? 'What each source says' : 'What the sources say',
    groups,
    searched: `${a.sourceCount} sources found`,
  }
}
