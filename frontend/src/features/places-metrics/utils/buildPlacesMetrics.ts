/**
 * The normalizer: one finished R3 run, joined with R1's plan and R2's places, becomes the
 * `PlacesMetricsResult` the page's components already render.
 *
 * Joins (R3 holds only ids and labels):
 *   R1 plan, by category_id and label → question wording, unit, enum and value type.
 *   R1 extraction, by category_id      → whether the renter asked for the category.
 *   R2 result, by category_id+place_id → name, rating, price, hours, maps link, travel.
 * Missing context degrades, it never invents: no R1 plan → questions named from their labels;
 * no R2 place → "Unnamed place" with no travel or details.
 */
import type { CategoryMetricPlan, SpecificMetric } from '@/features/r1-interpretation/types/r1'
import { taxonomyLabel } from '@/features/r1-interpretation/utils/present'
import type { CategoryResult, Place as R2Place } from '@/features/r2-proximity/types/r2'
import { priceLabel, todayHours } from '@/features/r2-proximity/utils/present'
import type { Category, Place, PlacesMetricsResult, Question, Travel } from '@/features/places-metrics/types/placesMetrics'
import type { R3Row } from '@/features/places-metrics/types/r3Run'
import { buildAnswer, hostOf, humanize, latestCheck } from '@/features/places-metrics/utils/answerFormat'
import { categoryColor, categoryIcon } from '@/features/places-metrics/utils/categoryStyle'

export type PlacesMetricsContext = {
  plan: CategoryMetricPlan[] | null
  /** Category ids the renter asked for; null when R1's extraction is unknown. */
  askedIds: Set<number> | null
  r2: Map<number, CategoryResult> | null
  origin: { latitude: number; longitude: number } | null
}

/** A question's id is unique across the page: the same label can exist in two categories. */
export function questionId(categoryId: number, label: string): string {
  return `${categoryId}:${label}`
}

function wantOf(spec: SpecificMetric | null): string {
  // R1 has no target value; under the agreed mapping a yes/no needs "Yes", anything else counts
  // once it is confirmed.
  return spec?.value_type === 'boolean' ? 'Yes' : 'A confirmed answer'
}

function questionsFor(categoryId: number, rows: R3Row[], specs: SpecificMetric[] | null): { q: Question; label: string; spec: SpecificMetric | null }[] {
  if (specs && specs.length) {
    return specs.map((spec) => ({
      label: spec.label,
      spec,
      q: { id: questionId(categoryId, spec.label), short: humanize(spec.label), text: spec.question, want: wantOf(spec) },
    }))
  }
  // No plan: every label R3 judged in this category, in the order first seen.
  const labels: string[] = []
  for (const r of rows) {
    for (const l of [...Object.keys(r.record.kept ?? {}), ...Object.keys(r.record.unresolved ?? {})]) {
      if (!labels.includes(l)) labels.push(l)
    }
  }
  return labels.map((label) => ({
    label,
    spec: null,
    q: { id: questionId(categoryId, label), short: humanize(label), text: `${humanize(label)}?`, want: wantOf(null) },
  }))
}

function minutes(m: number | null): number | null {
  return m === null ? null : Math.max(1, Math.round(m))
}

function travelOf(p: R2Place | undefined): Travel {
  if (!p) return { walk: null, distance: null, cycle: null, drive: null, transit: null, transitEstimate: false }
  const km = p.travel.walk.km
  return {
    walk: minutes(p.travel.walk.minutes),
    distance: km === null ? null : `${km.toFixed(1)} km`,
    cycle: minutes(p.travel.cycle.minutes),
    drive: minutes(p.travel.drive.minutes),
    transit: minutes(p.travel.transit.minutes),
    transitEstimate: p.travel.transit.estimated,
  }
}

/** Category order: asked-for first, then inferred, each in the plan's order; unplanned last. */
function categoryOrder(rows: R3Row[], ctx: PlacesMetricsContext): number[] {
  const inRows = [...new Set(rows.map((r) => r.categoryId))]
  const planned = (ctx.plan ?? []).map((p) => p.category_id).filter((id) => inRows.includes(id))
  const isAsked = (id: number) => (ctx.askedIds ? ctx.askedIds.has(id) : true)
  const unplanned = inRows.filter((id) => !planned.includes(id)).sort((a, b) => a - b)
  return [...planned.filter(isAsked), ...planned.filter((id) => !isAsked(id)), ...unplanned]
}

export function buildPlacesMetrics(rows: R3Row[], ctx: PlacesMetricsContext): PlacesMetricsResult {
  const categories: Category[] = []
  const places: Place[] = []

  categoryOrder(rows, ctx).forEach((categoryId) => {
    const plan = ctx.plan?.find((p) => p.category_id === categoryId) ?? null
    const catRows = rows.filter((r) => r.categoryId === categoryId)
    const qs = questionsFor(categoryId, catRows, plan?.specific_metrics ?? null)
    if (!qs.length || !catRows.length) return // nothing to compare: not shown

    const key = String(categoryId)
    const r2Cat = ctx.r2?.get(categoryId)
    const node = plan?.taxonomy_node ?? r2Cat?.taxonomyNode ?? ''
    categories.push({
      key,
      name: node ? taxonomyLabel(node) : `Category ${categoryId}`,
      color: categoryColor(categories.length),
      icon: categoryIcon(node),
      asked: ctx.askedIds ? ctx.askedIds.has(categoryId) : true,
      questions: qs.map((x) => x.q),
    })

    for (const row of catRows) {
      const r2 = r2Cat?.places.find((p) => p.placeId === row.placeId)
      places.push({
        key: `${categoryId}:${row.placeId}`,
        category: key,
        name: r2?.name || 'Unnamed place',
        site: row.websiteUrl ? hostOf(row.websiteUrl) || row.websiteUrl : null,
        websiteUrl: row.websiteUrl,
        mapsUrl: r2?.mapsUrl ?? null,
        rating: r2?.rating ?? null,
        reviewCount: r2?.reviewCount != null ? r2.reviewCount.toLocaleString('en-GB') : null,
        price: r2 ? priceLabel(r2.priceLevel) : null,
        hours: r2 ? todayHours(r2.weekdayHours) : null,
        travel: travelOf(r2),
        answers: Object.fromEntries(qs.map((x) => [x.q.id, buildAnswer(row.record, x.label, x.spec)])),
      })
    }
  })

  const o = ctx.origin
  return {
    address: o && Number.isFinite(o.latitude) ? `Near ${o.latitude.toFixed(4)}, ${o.longitude.toFixed(4)}` : 'Near the apartment',
    checkedOn: latestCheck(rows.map((r) => r.record)),
    categories,
    places,
  }
}
