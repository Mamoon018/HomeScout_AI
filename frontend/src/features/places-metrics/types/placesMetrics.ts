/**
 * Shapes for the places metrics page (/places_metrics): R3's answers to the renter's own
 * questions about each nearby place, plus the evidence behind every answer.
 */

/** One answer's verdict: fits the need, opinions differ, missing, or no info (couldn't confirm). */
export type Status = 'y' | 'l' | 'n' | 'u'

/** Where a piece of evidence came from: a web page, the place's official site, or a Google review. */
export type SourceKind = 'w' | 's' | 'r'

/**
 * Why an answer couldn't be confirmed: thin evidence, nothing online, the search call failed,
 * or the check itself failed on our side.
 */
export type UnconfirmedReason = 'thin' | 'none' | 'search_failed' | 'failed'

/** A category's key: R3's `category_id` as a string. */
export type CategoryKey = string

export type TravelMode = 'walk' | 'cycle' | 'drive' | 'transit'

export type SortMode = 'fit' | TravelMode

/** 0 meets every need, 1 meets some, 2 meets none, 3 nothing could be confirmed. */
export type Tier = 0 | 1 | 2 | 3

export type Question = {
  id: string
  short: string
  text: string
  want: string
}

export type Category = {
  key: CategoryKey
  name: string
  color: string
  /** SVG path data for the category's icon (24×24 stroke icon). */
  icon: string
  /** false: added because it usually matters, not part of the renter's brief. */
  asked: boolean
  questions: Question[]
}

/** A short summary of what one kind of source said. */
export type Voice = { kind: SourceKind; text: string }

/** A quotation behind an answer; `source` is the domain, empty for a review; `url` links it. */
export type Quote = { kind: SourceKind; source: string; text: string; url: string | null }

export type Answer = {
  status: Status
  value: string
  voices: Voice[]
  quotes: Quote[]
  sourceCount: number
  /** Only for status 'u'. */
  reason?: UnconfirmedReason
  reasonText?: string
}

/** Minutes per mode; null when R2 found no route for that mode. `distance` is the walk distance. */
export type Travel = {
  walk: number | null
  distance: string | null
  cycle: number | null
  drive: number | null
  transit: number | null
  transitEstimate: boolean
}

export type Place = {
  key: string
  category: CategoryKey
  name: string
  /** The official site's host for display, and its full URL; null when none was confirmed. */
  site: string | null
  websiteUrl: string | null
  mapsUrl: string | null
  rating: number | null
  reviewCount: string | null
  price: string | null
  hours: string | null
  travel: Travel
  answers: Record<string, Answer>
}

export type PlacesMetricsResult = {
  /** Where the search was centred, as shown in the heading. */
  address: string
  /** "14 Nov": the latest date any evidence was retrieved; null when there was none. */
  checkedOn: string | null
  categories: Category[]
  places: Place[]
}

/** A place with its per-question statuses and fit, computed once. */
export type RankedPlace = {
  place: Place
  statuses: Status[]
  tier: Tier
  score: number
}

/** Narrows the rail (and dims the table) to places in one tier, or with one answer to one question. */
export type PlaceFilter =
  | { category: CategoryKey; tier: Tier }
  | { category: CategoryKey; question: string; status: Status }

/** The place whose proof is open, and which of its questions is showing. */
export type Selection = { place: string; question: string } | null
