import {
  ArrowUpDownIcon,
  BriefcaseIcon,
  Building2Icon,
  CookingPotIcon,
  DumbbellIcon,
  FlowerIcon,
  FootprintsIcon,
  HeartHandshakeIcon,
  PlaneIcon,
  RouteIcon,
  ShoppingBasketIcon,
  TrainFrontIcon,
  TreesIcon,
  Volume1Icon,
  type LucideIcon,
} from 'lucide-react'

import type { MetricDepth, PredefinedMetric } from '@/features/r1-interpretation/types/r1'

type IconRule = [pattern: RegExp, icon: LucideIcon]

export const FACT_ICONS: IconRule[] = [
  [/relocat|move|moving/i, PlaneIcon],
  [/partner|wife|husband|kids|child|family|dog|cat/i, HeartHandshakeIcon],
  [/job|office|work|commute/i, BriefcaseIcon],
  [/cook|kitchen|meal|bake/i, CookingPotIcon],
  [/gym|workout|run|yoga|sport/i, DumbbellIcon],
  [/walk|hike|stroll/i, FootprintsIcon],
]

export const PLACE_ICONS: IconRule[] = [
  [/apartment|flat|rent|bedroom/i, Building2Icon],
  [/commute|route/i, RouteIcon],
  [/station|u-bahn|s-bahn|metro|subway|train|transit/i, TrainFrontIcon],
  [/supermarket|grocery|market/i, ShoppingBasketIcon],
  [/kitchen/i, CookingPotIcon],
  [/gym|fitness/i, DumbbellIcon],
  [/street|quiet/i, Volume1Icon],
  [/balcony|garden|terrace/i, FlowerIcon],
  [/elevator|lift/i, ArrowUpDownIcon],
  [/park|green/i, TreesIcon],
]

export function pick(rules: IconRule[], text: string, fallback: LucideIcon): LucideIcon {
  return rules.find(([pattern]) => pattern.test(text))?.[1] ?? fallback
}

/** `transit_station` → `Transit station`. */
export function taxonomyLabel(node: string): string {
  const spaced = node.replaceAll('_', ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export const DEPTH_LEVELS: readonly { id: MetricDepth; label: string; hint: string }[] = [
  { id: 'basic_profile', label: 'Essentials', hint: 'Who and where the place is' },
  { id: 'operating_details', label: 'Operating details', hint: 'How the place runs day to day' },
  { id: 'specific_attributes', label: 'Deep dive', hint: 'Facts picked out for your brief' },
]

/** 1-based rung of a depth on the three-step ladder. */
export function depthRung(depth: MetricDepth): number {
  return DEPTH_LEVELS.findIndex((level) => level.id === depth) + 1
}

const LABEL_OVERRIDES: Record<string, string> = {
  place_id: 'Place ID',
  google_maps_uri: 'Google Maps link',
  coordinates: 'Map position',
  'travel distance per mode (walk, drive, cycle)': 'Walk, drive and cycle distance',
  'travel duration per mode (walk, drive, cycle)': 'Walk, drive and cycle time',
  'transit travel distance': 'Public transport distance',
  'transit travel duration': 'Public transport time',
  'review volume': 'Number of reviews',
}

/** Standard fact labels as a renter would say them. */
export function factLabel(metric: PredefinedMetric): string {
  const label = LABEL_OVERRIDES[metric.label] ?? metric.label
  return label.charAt(0).toUpperCase() + label.slice(1)
}

/**
 * R1 writes each question as "<why we ask>: <what we find out>". Splits on the first colon
 * so the two halves can sit under their own captions; a question without one stays whole.
 */
export function splitQuestion(question: string): { why: string | null; ask: string } {
  const at = question.indexOf(': ')
  if (at === -1) {
    return { why: null, ask: question }
  }
  const why = question.slice(0, at).trim()
  const ask = question.slice(at + 2).trim()
  return { why: addressRenter(why), ask: ask.charAt(0).toUpperCase() + ask.slice(1) }
}

/** R1 writes about "the customer"; the renter is reading, so speak to them. */
function addressRenter(text: string): string {
  return text
    .replace(/^the customer explicitly wants /i, 'You asked for ')
    .replace(/^the customer explicitly says they /i, 'You said you ')
    .replace(/ and wants /g, ' and want ')
    .replace(/^the customer /i, 'You ')
}

export const NULL_POLICY_COPY: Record<string, string> = {
  unknown: 'If it cannot be found it stays marked unknown, never guessed.',
}
