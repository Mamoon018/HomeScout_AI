import type { Place, TravelMode } from '@/features/r2-proximity/types/r2'
import { TRAVEL_MODES } from '@/features/r2-proximity/types/r2'
import {
  minutesPhrase,
  nearest,
  type PageCategory,
} from '@/features/r2-proximity/utils/present'

/** The time limits the renter can pick. */
export const REACH_OPTIONS = [5, 10, 15, 20] as const
export type Reach = (typeof REACH_OPTIONS)[number]

export type Bead = { categoryId: number; color: string; inReach: boolean; missing: boolean; title: string }
export type ModeFit = { mode: TravelMode; count: number; of: number; beads: Bead[] }

/** Per mode: how many categories have their nearest place within the limit, and which. */
export function modeFit(categories: PageCategory[], reach: number): ModeFit[] {
  return TRAVEL_MODES.map((mode) => {
    const beads = categories.map((c) => {
      const missing = c.places.length === 0
      const t = nearest(c, mode)?.travel[mode].minutes ?? null
      return {
        categoryId: c.id,
        color: c.color,
        inReach: t !== null && t <= reach,
        missing,
        title: `${c.label}: ${missing ? 'nothing found' : t === null ? 'no route' : `nearest ${t} min`}`,
      }
    })
    return { mode, count: beads.filter((b) => b.inReach).length, of: categories.length, beads }
  })
}

/** A place in the strip. `time` reads "6 min walk"; the tooltip shows category, time, place. */
export type Ball = { place: Place; categoryId: number; category: string; color: string; minutes: number; time: string }
export type Band = { label: string; count: number; lower: number; upper: number; rows: Ball[][] }

const EDGES = [5, 10, 15, 20, Number.POSITIVE_INFINITY]
const BAND_LABELS = ['up to 5 mins', '5 to 10 mins', '10 to 15 mins', '15 to 20 mins', 'over 20 mins']

/** Every place by the lens mode, in five fixed bands, each band piled widest row first. */
export function bands(categories: PageCategory[], mode: TravelMode): { bands: Band[]; noRoute: number } {
  const balls: Ball[] = []
  let noRoute = 0
  for (const c of categories) {
    for (const place of c.places) {
      const minutes = place.travel[mode].minutes
      if (minutes === null) {
        noRoute++
        continue
      }
      balls.push({ place, categoryId: c.id, category: c.label, color: c.color, minutes, time: minutesPhrase(minutes, mode) })
    }
  }
  balls.sort((a, b) => a.minutes - b.minutes)
  return {
    noRoute,
    bands: EDGES.map((upper, i) => {
      const lower = i === 0 ? 0 : EDGES[i - 1]
      const inBand = balls.filter((b) => b.minutes > lower && b.minutes <= upper)
      return { label: BAND_LABELS[i], count: inBand.length, lower, upper, rows: pile(inBand) }
    }),
  }
}

/**
 * A pile that reads ..^..: the widest row (the nearest places) at the bottom, each row above
 * one ball narrower. The bottom row is the smallest w with w(w+1)/2 >= n.
 */
export function pile<T>(items: T[]): T[][] {
  const n = items.length
  if (n === 0) {
    return []
  }
  let w = 1
  while ((w * (w + 1)) / 2 < n) {
    w++
  }
  const rows: T[][] = []
  for (let k = 0, size = w; k < n; size--) {
    const take = Math.max(1, size)
    rows.push(items.slice(k, k + take))
    k += take
  }
  return rows
}

export type Choice = { category: PageCategory; count: number; plus: boolean }

/** Options within the limit by the lens mode, thinnest category first. Empty categories left out. */
export function choices(categories: PageCategory[], mode: TravelMode, reach: number): Choice[] {
  return categories
    .filter((c) => c.places.length > 0)
    .map((c) => {
      const count = c.places.filter((p) => {
        const m = p.travel[mode].minutes
        return m !== null && m <= reach
      }).length
      return { category: c, count, plus: c.capped && count === c.places.length }
    })
    .sort((a, b) => a.count - b.count)
}

export function choiceText(c: Choice): string {
  if (c.count === 0) {
    return 'None in reach'
  }
  if (c.count === 1) {
    return '1 option only'
  }
  return `${c.count}${c.plus ? '+' : ''} options`
}

export type Marker = {
  category: PageCategory
  place: Place
  minutes: number
  deg: number
  x: number
  y: number
}

/** Ring geometry in px: 340 square, outer ring (20 min) at radius 150. */
export const RING = { size: 340, radius: 150, maxMinutes: 20 } as const

/**
 * One ball per category: its nearest place on foot. Categories run clockwise from the nearest;
 * the angle is rank order, never a bearing. A nearest walk over 20 minutes is not drawn.
 */
export function ringMarkers(categories: PageCategory[]): Marker[] {
  const withWalk = categories
    .map((c) => ({ c, p: nearest(c, 'walk') }))
    .filter((x): x is { c: PageCategory; p: Place } => x.p !== null)
    .sort((a, b) => (a.p.travel.walk.minutes ?? 0) - (b.p.travel.walk.minutes ?? 0))
  const step = 360 / Math.max(withWalk.length, 1)
  const centre = RING.size / 2
  return withWalk
    .map(({ c, p }, i) => {
      const minutes = p.travel.walk.minutes ?? 0
      const deg = -90 + step / 2 + i * step
      const r = Math.max(16, (minutes / RING.maxMinutes) * RING.radius)
      const a = (deg * Math.PI) / 180
      return { category: c, place: p, minutes, deg, x: centre + r * Math.cos(a), y: centre + r * Math.sin(a) }
    })
    .filter((m) => m.minutes <= RING.maxMinutes)
}

/**
 * The 150° side of the ring holding the most close places within the limit (each weighs more the
 * nearer it is). Returns the conic-gradient start angle, measured from 12 o'clock.
 */
export function shadeStart(markers: Marker[], reach: number): number | null {
  const weighted = markers.filter((m) => m.minutes <= reach)
  if (weighted.length === 0) {
    return null
  }
  let best = 0
  let bestScore = -1
  for (let c = 0; c < 360; c += 5) {
    let score = 0
    for (const m of weighted) {
      const d = Math.abs((((m.deg - c) % 360) + 540) % 360 - 180)
      if (d <= 75) {
        score += 1 - m.minutes / RING.maxMinutes
      }
    }
    if (score > bestScore) {
      bestScore = score
      best = c
    }
  }
  return best - 75 + 90
}
