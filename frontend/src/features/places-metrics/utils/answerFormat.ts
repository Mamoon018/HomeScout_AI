/**
 * Turns one R3 metric record into the page's `Answer`: its verdict, the value in the renter's
 * terms, each source's note, the quotes, and (when unconfirmed) the plain reason.
 *
 * Verdict mapping (agreed for live data; R3 reports facts, not fit):
 *   opinion_mixed → 'l' (Opinion differs) · false → 'n' (Missing) · any other confirmed value →
 *   'y' (Fits your need) · not confirmed or unresolved → 'u' (No info).
 */
import type { SpecificMetric } from '@/features/r1-interpretation/types/r1'
import type { Answer, Quote, SourceKind, UnconfirmedReason, Voice } from '@/features/places-metrics/types/placesMetrics'
import type { MetricResolutionWire, ResolutionRecordWire } from '@/features/places-metrics/types/r3Run'

export const REASON_TEXT: Record<UnconfirmedReason, string> = {
  thin: 'I found mentions, but not enough to be sure.',
  none: 'Nothing about this turned up online.',
  search_failed: 'The search didn’t go through.',
  failed: 'Couldn’t check this one: something went wrong on my side.',
}

/** `museumkaart_free_entry` / `very_busy` → "Museumkaart free entry" / "Very busy". */
export function humanize(text: string): string {
  const spaced = text.replaceAll('_', ' ').replace(/\s+/g, ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

const CURRENCY: Record<string, string> = { EUR: '€', USD: '$', GBP: '£' }

/** A currency gets its symbol and cents ("€17.50"); any other unit trails ("2.6 km"). */
function formatNumber(n: number, unit: string | null): string {
  const plain = String(Number(n.toFixed(2)))
  if (!unit) return plain
  const symbol = CURRENCY[unit.toUpperCase()] ?? (['€', '$', '£'].includes(unit) ? unit : null)
  if (symbol) return `${symbol}${Number.isInteger(n) ? n : n.toFixed(2)}`
  return `${plain} ${unit}`
}

function formatDateTime(text: string): string {
  // A bare time ("06:00") is already readable; a full ISO timestamp becomes a local date and time.
  if (!/\d{4}-\d{2}-\d{2}/.test(text)) return text
  const d = new Date(text)
  if (Number.isNaN(d.getTime())) return text
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** The resolved value in the renter's terms: Yes/No, "€25", "Very busy", "6 Jan 2027, 06:00". */
export function formatValue(value: string | number | boolean, spec: SpecificMetric | null): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return formatNumber(value, spec?.unit ?? null)
  if (spec?.value_type === 'date_time') return formatDateTime(value)
  return humanize(value)
}

/** "Leans busy", "Leans €25": a chosen-between answer reads as leaning. */
function leaning(text: string): string {
  return `Leans ${/^[A-Z][a-z]/.test(text) ? text.charAt(0).toLowerCase() + text.slice(1) : text}`
}

const KIND: Record<string, SourceKind> = { web: 'w', scrape: 's', google_reviews: 'r' }

/** "www.example.com/a" → "example.com"; empty when there is no readable URL. */
export function hostOf(url: string | null | undefined): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

function voicesOf(m: MetricResolutionWire): Voice[] {
  const out: Voice[] = []
  if (m.web_value) out.push({ kind: 'w', text: m.web_value })
  if (m.scrape_value) out.push({ kind: 's', text: m.scrape_value })
  if (m.reviews_value) out.push({ kind: 'r', text: m.reviews_value })
  return out
}

function quotesOf(m: MetricResolutionWire): Quote[] {
  return (m.evidence ?? []).flatMap((e) => {
    const kind = KIND[e.source ?? '']
    if (!kind || !e.quote) return []
    const url = typeof e.url === 'string' && e.url ? e.url : null
    return [{ kind, source: kind === 'r' ? '' : hostOf(url), text: e.quote, url }]
  })
}

/** Why a label ended unresolved, in the page's four plain reasons. Unknown codes read as "none". */
function reasonOf(record: ResolutionRecordWire, label: string, code: string): UnconfirmedReason {
  switch (code) {
    case 'no_evidence':
      return record.phase1?.metric_outcomes?.[label]?.status === 'failed' ? 'search_failed' : 'none'
    case 'verification_unmet':
    case 'type_violation':
    case 'enum_violation':
    case 'quote_unverified':
    case 'basis_inconsistent':
      return 'thin'
    case 'resolution_call_failed':
    case 'resolution_body_invalid':
      return 'failed'
    default:
      return 'none'
  }
}

/** Distinct sources the search found for this question (phase-1 evidence items). */
function sourceCountOf(record: ResolutionRecordWire, label: string): number {
  const items = record.phase1?.metrics_source_content?.items ?? []
  const keys = new Set(
    items.filter((i) => i.metric_labels?.includes(label)).map((i) => `${i.source_kind}|${i.url ?? ''}`),
  )
  return keys.size
}

function unconfirmed(reason: UnconfirmedReason, sourceCount: number): Answer {
  return { status: 'u', value: 'Couldn’t confirm', voices: [], quotes: [], sourceCount, reason, reasonText: REASON_TEXT[reason] }
}

/** One question's answer for one place, from its resolution record. */
export function buildAnswer(record: ResolutionRecordWire, label: string, spec: SpecificMetric | null): Answer {
  const sourceCount = sourceCountOf(record, label)
  const kept = record.kept?.[label]
  if (kept) {
    const v = kept.final_value
    if (kept.verification_met === false || v === null || v === undefined) return unconfirmed('thin', sourceCount)
    const text = formatValue(v, spec)
    const status = kept.opinion_mixed ? 'l' : v === false ? 'n' : 'y'
    return {
      status,
      value: status === 'l' ? leaning(text) : text,
      voices: voicesOf(kept),
      quotes: quotesOf(kept),
      sourceCount,
    }
  }
  const code = record.unresolved?.[label]
  if (code) return unconfirmed(reasonOf(record, label, code), sourceCount)
  // Not in either list: the place's pipeline stopped before this question was judged.
  return unconfirmed(record.outcome && record.outcome !== 'completed' ? 'failed' : 'none', sourceCount)
}

/** The latest evidence date across every record, as "14 Nov"; null when none was retrieved. */
export function latestCheck(records: ResolutionRecordWire[]): string | null {
  let latest = 0
  for (const r of records) {
    for (const item of r.phase1?.metrics_source_content?.items ?? []) {
      const t = item.retrieved_at ? Date.parse(item.retrieved_at) : NaN
      if (!Number.isNaN(t) && t > latest) latest = t
    }
  }
  return latest ? new Date(latest).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : null
}
