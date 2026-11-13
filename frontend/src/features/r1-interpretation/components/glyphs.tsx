import { createElement, type ComponentProps } from 'react'
import { MapPinIcon, SparklesIcon, type LucideIcon } from 'lucide-react'

import { FACT_ICONS, PLACE_ICONS, pick } from '@/features/r1-interpretation/utils/present'
import { taxonomyStyle } from '@/features/r1-interpretation/utils/taxonomyStyle'

type IconProps = Omit<ComponentProps<LucideIcon>, 'ref'>

/** Icon for a fact about the renter. */
export function FactIcon({ text, ...props }: IconProps & { text: string }) {
  return createElement(pick(FACT_ICONS, text, SparklesIcon), props)
}

/** Icon for a kind of place (a renter phrase or a taxonomy node). */
export function PlaceIcon({ text, ...props }: IconProps & { text: string }) {
  return createElement(pick(PLACE_ICONS, text.replaceAll('_', ' '), MapPinIcon), props)
}

/** Icon for a node of the backend's amenity taxonomy. */
export function TaxonomyIcon({ node, ...props }: IconProps & { node: string }) {
  return createElement(taxonomyStyle(node).icon, props)
}
