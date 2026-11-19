import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { PlaceIcon } from '@/features/r1-interpretation/components/glyphs'
import {
  MAX_VISIBLE_CHIPS,
  layoutPlaces,
  type Family,
  type Tier,
} from '@/features/r1-interpretation/utils/place-layout'
import { cn } from '@/lib/utils'

export type Place = {
  id: string | number
  /** What the person asked for, as shown. */
  title: string
  /** A smaller line under the title, e.g. what the renter originally wrote. */
  note?: string
  /** Text the icon is picked from. Defaults to the title. */
  iconText?: string
  family: Family
  features?: readonly string[]
  /** Short state label ("needs a closer look"). Never counted as a feature. */
  status?: string
  /** Lit while its flagged phrase is hovered. */
  linked?: boolean
}

/** Width the panel's padding and border take off the card, so spans follow the card's own width. */
const CARD_CHROME = 42

type PlaceGridProps = {
  places: readonly Place[]
  /** Entrance delay of the first card, in ms. */
  baseDelay: number
  /** Gap between two cards' entrances, in ms. */
  stagger?: number
  emptyText?: string
}

/**
 * Six-column grid of place cards. Each card picks its shape (none / compact / expanded)
 * from its own feature count, so no caller chooses a variant by hand.
 */
export function PlaceGrid({ places, baseDelay, stagger = 60, emptyText = 'No places named yet.' }: PlaceGridProps) {
  const ref = useRef<HTMLUListElement>(null)
  const [width, setWidth] = useState(600)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setWidth(el.clientWidth + CARD_CHROME)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [places.length])

  if (places.length === 0) {
    return <p className="m-0 text-sm leading-6 text-muted-foreground">{emptyText}</p>
  }

  const items = layoutPlaces(places, width)
  return (
    <ul ref={ref} className="place-grid">
      {items.map((place) => (
        <li key={place.id} style={{ '--span': place.span } as CSSProperties}>
          <PlaceCard
            place={place}
            tier={place.tier}
            delay={baseDelay + Math.min(place.index * stagger, 600)}
          />
        </li>
      ))}
    </ul>
  )
}

type PlaceCardProps = {
  place: Place & { features: string[] }
  tier: Tier
  delay: number
}

function PlaceCard({ place, tier, delay }: PlaceCardProps) {
  const { title, note, family, features, status, linked } = place
  const [showAll, setShowAll] = useState(false)
  const overflow = features.length > MAX_VISIBLE_CHIPS
  const shown = overflow && !showAll ? features.slice(0, MAX_VISIBLE_CHIPS) : features

  const tile = (
    <span aria-hidden="true" className="place__tile">
      <PlaceIcon text={place.iconText ?? title} />
    </span>
  )
  const heading = (
    <div className="place__heading">
      <h4 className="place__title">{title}</h4>
      {note ? <p className="place__note">{note}</p> : null}
    </div>
  )
  const statusChip = status ? <li className="chip chip--status">{status}</li> : null

  const chips = (
    <ul className="chips" aria-label={`Features for ${title}`}>
      {shown.map((feature, i) => (
        <li key={feature} className="chip" style={{ '--i': i } as CSSProperties}>
          {feature}
        </li>
      ))}
      {overflow ? (
        <li>
          <button
            type="button"
            className="chip chip--more"
            aria-expanded={showAll}
            onClick={() => setShowAll((v) => !v)}
          >
            {showAll ? 'Show less' : `+${features.length - MAX_VISIBLE_CHIPS} more`}
          </button>
        </li>
      ) : null}
      {statusChip}
    </ul>
  )

  let body: ReactNode
  if (tier === 'none') {
    body = (
      <>
        <div className="place__row place__row--split">
          {tile}
          {status ? <span className="chip chip--status">{status}</span> : null}
        </div>
        {heading}
      </>
    )
  } else if (tier === 'compact') {
    body = (
      <>
        <div className="place__row">
          {tile}
          {heading}
        </div>
        {chips}
      </>
    )
  } else {
    body = (
      <>
        <div className="place__row">
          {tile}
          {heading}
          <span className="place__count">{features.length} features</span>
        </div>
        {chips}
      </>
    )
  }

  return (
    <div
      className={cn('place', `place--${tier}`)}
      data-family={family}
      data-status={status ? '' : undefined}
      data-linked={linked ? '' : undefined}
      style={{ '--delay': `${delay}ms` } as CSSProperties}
    >
      {body}
    </div>
  )
}
