import {
  BanknoteIcon,
  BedDoubleIcon,
  Building2Icon,
  BriefcaseIcon,
  CarIcon,
  ChurchIcon,
  DumbbellIcon,
  GraduationCapIcon,
  HeartPulseIcon,
  HouseIcon,
  LandmarkIcon,
  MapIcon,
  MapPinIcon,
  MountainIcon,
  ShoppingBagIcon,
  TicketIcon,
  TrainFrontIcon,
  TreesIcon,
  UtensilsIcon,
  WavesIcon,
  WrenchIcon,
  type LucideIcon,
} from 'lucide-react'

import {
  TAXONOMY_GROUPS,
  type TaxonomyGroup,
} from '@/features/r1-interpretation/utils/taxonomyGroups'
import { PLACE_ICONS, pick } from '@/features/r1-interpretation/utils/present'
import { familyOf, type Family } from '@/features/r1-interpretation/utils/place-layout'

export type TaxonomyStyle = {
  icon: LucideIcon
  /** One of the four place families the cards are tinted with (see r1.css). */
  family: Family
}

/**
 * One icon and one colour family per taxonomy group. The families are the ones the place
 * cards already use, so a kind of place looks the same wherever it appears:
 * home (where you live and learn), go (getting around), daily (errands and food), calm (outdoors, leisure, quiet).
 */
const GROUP_STYLE: Record<TaxonomyGroup, TaxonomyStyle> = {
  Automotive: { icon: CarIcon, family: 'go' },
  Business: { icon: BriefcaseIcon, family: 'daily' },
  Culture: { icon: LandmarkIcon, family: 'calm' },
  Education: { icon: GraduationCapIcon, family: 'home' },
  'Entertainment and recreation': { icon: TicketIcon, family: 'calm' },
  Finance: { icon: BanknoteIcon, family: 'daily' },
  'Food and drink': { icon: UtensilsIcon, family: 'daily' },
  'Geographic areas': { icon: MapIcon, family: 'go' },
  Government: { icon: Building2Icon, family: 'home' },
  'Health and wellness': { icon: HeartPulseIcon, family: 'home' },
  Housing: { icon: HouseIcon, family: 'home' },
  Lodging: { icon: BedDoubleIcon, family: 'home' },
  'Natural features': { icon: MountainIcon, family: 'calm' },
  'Places of worship': { icon: ChurchIcon, family: 'calm' },
  Services: { icon: WrenchIcon, family: 'daily' },
  Shopping: { icon: ShoppingBagIcon, family: 'daily' },
  Sports: { icon: DumbbellIcon, family: 'calm' },
  Transport: { icon: TrainFrontIcon, family: 'go' },
}

/** A few nodes read better with their own icon than with their group's. */
const NODE_ICON: Record<string, LucideIcon> = {
  park: TreesIcon,
  city_park: TreesIcon,
  playground: TreesIcon,
  swimming_pool: WavesIcon,
}

const GROUP_OF_NODE: ReadonlyMap<string, TaxonomyGroup> = new Map(
  (Object.keys(TAXONOMY_GROUPS) as TaxonomyGroup[]).flatMap((group) =>
    TAXONOMY_GROUPS[group].map((node): [string, TaxonomyGroup] => [node, group]),
  ),
)

/** True when the node is one the backend's taxonomy defines. */
export function isTaxonomyNode(node: string): boolean {
  return GROUP_OF_NODE.has(node)
}

/**
 * The icon and colour family for a taxonomy node. A node outside the taxonomy (a value the
 * backend added after this list was generated) falls back to reading its words, then to a pin.
 */
export function taxonomyStyle(node: string): TaxonomyStyle {
  const group = GROUP_OF_NODE.get(node)
  if (group === undefined) {
    const words = node.replaceAll('_', ' ')
    return { icon: pick(PLACE_ICONS, words, MapPinIcon), family: familyOf(words) }
  }
  const style = GROUP_STYLE[group]
  return { icon: NODE_ICON[node] ?? style.icon, family: style.family }
}
