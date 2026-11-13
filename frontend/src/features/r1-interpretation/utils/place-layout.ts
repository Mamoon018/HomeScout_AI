export type Family = 'home' | 'go' | 'daily' | 'calm'
export type Tier = 'none' | 'compact' | 'expanded'

/** Features needed for the full-width card. The only place the boundary lives. */
export const EXPANDED_MIN = 3
/** Chips shown before "+N more". */
export const MAX_VISIBLE_CHIPS = 8
const COLUMNS = 6
const RANK: Record<Tier, number> = { expanded: 0, compact: 1, none: 2 }

/** A family is a category of place, never a state. First match wins; `home` is the fallback. */
const FAMILY_RULES: [RegExp, Family][] = [
  [/commute|route|station|u-bahn|s-bahn|metro|subway|train|transit|\bbus\b|tram/i, 'go'],
  [/supermarket|grocery|market|gym|fitness|bakery|pharmacy|caf[eé]|restaurant/i, 'daily'],
  [/street|quiet|park|green|forest|lake|river/i, 'calm'],
]

export function familyOf(text: string): Family {
  return FAMILY_RULES.find(([pattern]) => pattern.test(text))?.[1] ?? 'home'
}

/** Spans by the preference card's own width, so it behaves the same in a sidebar or a page. */
export function spansFor(width: number): Record<Tier, number> {
  if (width >= 520) return { none: 2, compact: 3, expanded: 6 }
  if (width >= 360) return { none: 3, compact: 6, expanded: 6 }
  return { none: 6, compact: 6, expanded: 6 }
}

/** Trim, drop empties and case-insensitive duplicates, so the count is honest. */
export function cleanFeatures(list: readonly string[] = []): string[] {
  const seen = new Set<string>()
  return list
    .map((s) => s.trim())
    .filter((s) => {
      const key = s.toLowerCase()
      if (!s || seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function tierOf(count: number): Tier {
  if (count === 0) return 'none'
  return count < EXPANDED_MIN ? 'compact' : 'expanded'
}

export type PlaceInput = { features?: readonly string[] }
export type LaidOut<T extends PlaceInput> = T & {
  features: string[]
  tier: Tier
  /** Position in the sorted grid; drives the entrance stagger. */
  index: number
  span: number
}

/**
 * Most detailed places first, original order kept inside each tier (stable sort), then
 * rows filled exactly: a short last row hands its spare columns to the last card.
 */
export function layoutPlaces<T extends PlaceInput>(places: readonly T[], width: number): LaidOut<T>[] {
  const spans = spansFor(width)
  const items = places
    .map((p, order) => {
      const features = cleanFeatures(p.features)
      return { ...p, features, tier: tierOf(features.length), order }
    })
    .sort((a, b) => RANK[a.tier] - RANK[b.tier] || a.order - b.order)
    .map((p, index) => ({ ...p, index, span: spans[p.tier] })) as LaidOut<T>[]

  let used = 0
  for (const item of items) {
    if (item.span > COLUMNS - used) used = 0
    used = (used + item.span) % COLUMNS
  }
  if (used !== 0 && items.length) items[items.length - 1].span += COLUMNS - used
  return items
}
