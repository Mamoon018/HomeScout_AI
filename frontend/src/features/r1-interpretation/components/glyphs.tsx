import { createElement, type ComponentProps } from 'react'
import { MapPinIcon, SparklesIcon, type LucideIcon } from 'lucide-react'

import { FACT_ICONS, PLACE_ICONS, pick } from '@/features/r1-interpretation/utils/present'

type IconProps = Omit<ComponentProps<LucideIcon>, 'ref'>

/** Icon for a fact about the renter. */
export function FactIcon({ text, ...props }: IconProps & { text: string }) {
  return createElement(pick(FACT_ICONS, text, SparklesIcon), props)
}

/** Icon for a kind of place (a renter phrase or a taxonomy node). */
export function PlaceIcon({ text, ...props }: IconProps & { text: string }) {
  return createElement(pick(PLACE_ICONS, text.replaceAll('_', ' '), MapPinIcon), props)
}
