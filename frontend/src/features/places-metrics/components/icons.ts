/** SVG path data for the page's 24×24 stroke icons, as drawn in the design. */
import type { SortMode, SourceKind, Status, TravelMode } from '@/features/places-metrics/types/placesMetrics'

export const STATUS_ICON: Record<Status, string> = {
  y: 'm5 12 5 5 9-10',
  l: 'M5 13c2.3-3 4.7-3 7 0s4.7 3 7 0',
  n: 'M7 7l10 10M17 7 7 17',
  u: 'M9.5 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.8-.9 1.4M12 17h.01',
}

export const MODE_ICON: Record<TravelMode, string> = {
  walk: 'M4 16v-2.4C4 11.5 3 10.5 3 8c0-2.7 1.5-6 4.5-6C9.4 2 10 3.8 10 5.5c0 3.1-2 5.7-2 8.7V16a2 2 0 1 1-4 0ZM20 20v-2.4c0-2.1 1-3.1 1-5.6 0-2.7-1.5-6-4.5-6C14.6 6 14 7.8 14 9.5c0 3.1 2 5.7 2 8.7V20a2 2 0 1 0 4 0ZM16 17h4M4 13h4',
  cycle: 'M2 15a3 3 0 1 0 6 0a3 3 0 1 0 -6 0M16 15a3 3 0 1 0 6 0a3 3 0 1 0 -6 0M12 17.5V14l-3-3 4-3 2 3h2M14 4.5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0',
  drive: 'M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9L18 10l-2.7-3.6A2 2 0 0 0 13.7 6H7.3a2 2 0 0 0-1.6.8L3 10l-.5.1C1.7 10.3 1 11.1 1 12v4c0 .6.4 1 1 1h2M7 17h8M5 17a2 2 0 1 0 4 0a2 2 0 1 0 -4 0M15 17a2 2 0 1 0 4 0a2 2 0 1 0 -4 0',
  transit: 'M8 3.1V7a4 4 0 0 0 8 0V3.1M9 15l-1-1M15 15l1-1M9 19c-2.8 0-5-2.2-5-5v-4a8 8 0 0 1 16 0v4c0 2.8-2.2 5-5 5ZM8 19l-2 3M16 19l2 3',
}

export const SORT_ICON: Record<SortMode, string> = {
  fit: 'M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0M8 12l3 3 5-6',
  ...MODE_ICON,
}

export const WEB_ICON = 'M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0'
export const REVIEW_ICON = 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'
export const SEARCH_ICON = 'M4 11a7 7 0 1 0 14 0a7 7 0 1 0 -14 0M20 20l-3.5-3.5'
export const PIN_ICON = 'M20 10c0 5-5.5 10.2-7.4 11.8a1 1 0 0 1-1.2 0C9.5 20.2 4 15 4 10a8 8 0 0 1 16 0M9 10a3 3 0 1 0 6 0a3 3 0 1 0 -6 0'
export const CLOCK_ICON = 'M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0M12 7v5l3 2'
export const CHECK_ICON = 'm5 12 5 5 9-10'
export const CHEVRON_DOWN = 'm6 9 6 6 6-6'
export const CHEVRON_LEFT = 'm15 6-6 6 6 6'
export const CHEVRON_RIGHT = 'm9 6 6 6-6 6'
export const CLOSE_ICON = 'M6 6l12 12M18 6 6 18'
export const STAR_PATH = 'M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z'

/** Evidence group icon by source kind. */
export const EVIDENCE_ICON: Record<'search' | SourceKind, string> = {
  search: SEARCH_ICON,
  w: WEB_ICON,
  s: WEB_ICON,
  r: REVIEW_ICON,
}
