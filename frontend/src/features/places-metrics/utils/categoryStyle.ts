/**
 * Icon and colour for a category on this page, from its taxonomy node.
 *
 * Icons are mapped by taxonomy group (the backend's full node set, `TAXONOMY_GROUPS`), with a
 * few nodes overridden; anything outside the taxonomy falls back to a map pin. Colours follow
 * the page's category order, so neighbouring cards never share one.
 */
import { TAXONOMY_GROUPS, type TaxonomyGroup } from '@/features/r1-interpretation/utils/taxonomyGroups'

/** 24×24 stroke paths in the page's icon style. */
const ICON = {
  dumbbell: 'M6 7v10M18 7v10M3 9v6M21 9v6M6 12h12',
  cup: 'M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM17 10h2a2 2 0 0 1 0 4h-2M8 3v3M12 3v3',
  cart: 'M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h8.2a2 2 0 0 0 2-1.6L21 8H6M8 21a1 1 0 1 0 2 0a1 1 0 1 0 -2 0M17 21a1 1 0 1 0 2 0a1 1 0 1 0 -2 0',
  tree: 'M12 21v-5M7 16h10l-5-12zM9 21h6',
  museum: 'M3 21h18M5 21V10M19 21V10M9 21V10M15 21V10M2 10l10-6 10 6z',
  car: 'M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9L18 10l-2.7-3.6A2 2 0 0 0 13.7 6H7.3a2 2 0 0 0-1.6.8L3 10l-.5.1C1.7 10.3 1 11.1 1 12v4c0 .6.4 1 1 1h2M7 17h8M5 17a2 2 0 1 0 4 0a2 2 0 1 0 -4 0M15 17a2 2 0 1 0 4 0a2 2 0 1 0 -4 0',
  briefcase: 'M3 7h18v13H3zM8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18',
  cap: 'M22 10 12 5 2 10l10 5 10-5zM6 12v5c3 3 9 3 12 0v-5',
  ticket: 'M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4zM13 6v2M13 11v2M13 16v2',
  banknote: 'M2 6h20v12H2zM9 12a3 3 0 1 0 6 0a3 3 0 1 0 -6 0M6 12h.01M18 12h.01',
  utensils: 'M4 3v7a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2V3M7 3v18M20 15V3a4 4 0 0 0-4 4v6a2 2 0 0 0 2 2h2zm0 0v6',
  map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14',
  building: 'M4 21V3h10v18M14 9h6v12M2 21h20M8 7h2M8 11h2M8 15h2',
  heart: 'M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7zM3.5 12h4l1.5-3 2 6 1.5-3h4',
  house: 'M3 10.5 12 3l9 7.5V21H3zM9 21v-6h6v6',
  bed: 'M2 20V8M2 16h20v4M22 16v-4a3 3 0 0 0-3-3h-8v7M5 11.5a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0 -3 0',
  mountain: 'M3 20 9.5 8l4 7 2.5-4 5 9z',
  church: 'M12 2v4M10 4h4M6 21V11l6-5 6 5v10M3 21h18M10 21v-4a2 2 0 0 1 4 0v4',
  wrench: 'M14.5 6.5a4 4 0 0 0 5 5L12 19a2.1 2.1 0 0 1-3-3zM14.5 6.5 17 4a4 4 0 0 1 3 3l-2.5 2.5',
  train: 'M8 3.1V7a4 4 0 0 0 8 0V3.1M9 15l-1-1M15 15l1-1M9 19c-2.8 0-5-2.2-5-5v-4a8 8 0 0 1 16 0v4c0 2.8-2.2 5-5 5zM8 19l-2 3M16 19l2 3',
  waves: 'M2 12c2 0 2-1.5 4-1.5S8 12 10 12s2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5M2 17c2 0 2-1.5 4-1.5S8 17 10 17s2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5',
  pin: 'M20 10c0 5-5.5 10.2-7.4 11.8a1 1 0 0 1-1.2 0C9.5 20.2 4 15 4 10a8 8 0 0 1 16 0M9 10a3 3 0 1 0 6 0a3 3 0 1 0 -6 0',
} as const

const GROUP_ICON: Record<TaxonomyGroup, string> = {
  Automotive: ICON.car,
  Business: ICON.briefcase,
  Culture: ICON.museum,
  Education: ICON.cap,
  'Entertainment and recreation': ICON.ticket,
  Finance: ICON.banknote,
  'Food and drink': ICON.utensils,
  'Geographic areas': ICON.map,
  Government: ICON.building,
  'Health and wellness': ICON.heart,
  Housing: ICON.house,
  Lodging: ICON.bed,
  'Natural features': ICON.mountain,
  'Places of worship': ICON.church,
  Services: ICON.wrench,
  Shopping: ICON.cart,
  Sports: ICON.dumbbell,
  Transport: ICON.train,
}

/** Nodes that read better with their own icon than with their group's. */
const NODE_ICON: Record<string, string> = {
  cafe: ICON.cup,
  coffee_shop: ICON.cup,
  cat_cafe: ICON.cup,
  dog_cafe: ICON.cup,
  tea_house: ICON.cup,
  park: ICON.tree,
  city_park: ICON.tree,
  dog_park: ICON.tree,
  national_park: ICON.tree,
  playground: ICON.tree,
  garden: ICON.tree,
  swimming_pool: ICON.waves,
  supermarket: ICON.cart,
  grocery_store: ICON.cart,
}

const GROUP_OF_NODE: ReadonlyMap<string, TaxonomyGroup> = new Map(
  (Object.keys(TAXONOMY_GROUPS) as TaxonomyGroup[]).flatMap((group) =>
    (TAXONOMY_GROUPS[group] as readonly string[]).map((node): [string, TaxonomyGroup] => [node, group]),
  ),
)

/** The design's category colours, then a few more of the same weight; cycled by page order. */
export const CATEGORY_COLORS = ['#5b8def', '#26b5a9', '#8f7ae6', '#d2699a', '#f08a5d', '#4f9a5c', '#c2902b', '#6b7fd7'] as const

/** The icon path for a taxonomy node: node override, then its group's, then a map pin. */
export function categoryIcon(node: string): string {
  if (NODE_ICON[node]) return NODE_ICON[node]
  const group = GROUP_OF_NODE.get(node)
  return group ? GROUP_ICON[group] : ICON.pin
}

export function categoryColor(index: number): string {
  return CATEGORY_COLORS[index % CATEGORY_COLORS.length]
}
