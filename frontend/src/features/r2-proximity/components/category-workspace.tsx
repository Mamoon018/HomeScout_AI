import type { CSSProperties } from 'react'
import { ArrowUpRightIcon, InfoIcon, MapPinIcon, ScrollTextIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { TaxonomyIcon } from '@/features/r1-interpretation/components/glyphs'
import { TravelCells } from '@/features/r2-proximity/components/travel-cells'
import { TRAVEL_MODES, type Leg, type Place, type TravelMode } from '@/features/r2-proximity/types/r2'
import { modeNote, nearest, priceLabel, todayHours, type PageCategory } from '@/features/r2-proximity/utils/present'

type CategoryWorkspaceProps = {
  category: PageCategory
  radiusLabel: string
}

/** One category: the closest place by each mode, then every place found, nearest walk first. */
export function CategoryWorkspace({ category, radiusLabel }: CategoryWorkspaceProps) {
  const n = category.places.length
  const closest = closestByMode(category)
  const anyEstimate = category.places.some((p) => p.travel.transit.estimated)

  return (
    <section
      aria-labelledby={`cat-${category.id}`}
      data-fam={category.family}
      className="r2-glass r2-enter flex min-w-0 flex-[999_1_560px] flex-col gap-[18px] rounded-[28px] p-5 md:p-6"
      style={{ '--d': '360ms' } as CSSProperties}
    >
      <div key={`h-${category.id}`} className="r2-swap flex flex-wrap items-center gap-3.5">
        <span className="r2-tile size-12 rounded-[14px]" aria-hidden="true">
          <TaxonomyIcon node={category.node} className="size-[22px]" strokeWidth={1.7} />
        </span>
        <div className="min-w-0 flex-[1_1_240px]">
          <h2 id={`cat-${category.id}`} className="m-0 text-xl leading-[26px] font-semibold">
            {category.label}
          </h2>
          {category.note ? (
            <p className="m-0 mt-0.5 text-[13px] leading-[18px] text-(--fs-muted)">{category.note}</p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span className="r2-nearest">{n === 0 ? 'None found' : `${n} ${n === 1 ? 'place' : 'places'}`}</span>
          <Link className="r2-why" to="/home" title="Opens the plan on Home that this search was run from">
            <ScrollTextIcon aria-hidden="true" className="size-3.5" />
            Why is this category included?
            <ArrowUpRightIcon aria-hidden="true" className="size-3.5" />
          </Link>
        </div>
      </div>

      {n === 0 ? (
        <div key={`none-${category.id}`} className="r2-swap r2-inset px-6 py-7">
          <p className="m-0 text-base font-semibold">Nothing found within {radiusLabel}</p>
          <p className="m-0 max-w-[56ch] text-sm leading-[21px] text-(--fs-muted)">
            The search looked for this kind of place in the whole circle and found none. It hasn&apos;t been
            checked beyond {radiusLabel}.
          </p>
        </div>
      ) : (
        <>
          <div key={`m-${category.id}`} className="r2-swap r2-inset gap-3 p-4">
            <p className="r2-h m-0 text-[13px]">The closest one, by how you&apos;d get there</p>
            <TravelCells travel={closest} big />
            <p className="m-0 flex items-start gap-2 text-[13.5px] leading-5">
              <InfoIcon aria-hidden="true" className="mt-0.5 size-[15px] flex-none text-[#1f7a80]" />
              <span>{modeNote(closest)}</span>
            </p>
          </div>

          <ul className="r2-cards m-0 list-none p-0">
            {category.places.map((p, i) => (
              <PlaceCard key={`${category.id}-${p.placeId}`} place={p} first={i === 0} delay={Math.min(i * 60, 540)} />
            ))}
          </ul>

          <div className="flex flex-col gap-1 text-[12.5px] leading-[18px] text-(--fs-muted)">
            {category.capped ? <span>Showing the nearest 10 places, sorted by distance, not by quality.</span> : null}
            {anyEstimate ? <span>est. means the route was estimated rather than looked up.</span> : null}
            <span>All bars use one scale, 0 to 30 minutes, so you can compare modes and places.</span>
          </div>
        </>
      )}
    </section>
  )
}

function PlaceCard({ place, first, delay }: { place: Place; first: boolean; delay: number }) {
  const price = priceLabel(place.priceLevel)
  const hours = todayHours(place.weekdayHours)
  return (
    <li className="r2-pc" style={{ '--d': `${delay}ms` } as CSSProperties}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="r2-pc-name">{place.name}</h3>
        <div className="flex flex-none items-center gap-1.5">
          {first ? <span className="r2-nearest">Nearest</span> : null}
          {place.mapsUrl ? (
            <a
              className="r2-maps"
              href={place.mapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Open ${place.name} in Google Maps`}
            >
              <MapPinIcon aria-hidden="true" className="size-3" strokeWidth={2} />
              Maps
            </a>
          ) : null}
        </div>
      </div>
      {place.rating !== null || price || hours ? (
        <div className="r2-meta">
          {place.rating !== null ? (
            <span className="inline-flex items-center gap-1.5">
              <Stars rating={place.rating} />
              <span>
                <b className="font-bold text-(--fs-ink)">{place.rating.toFixed(1)}</b>
                {place.reviewCount !== null ? ` (${place.reviewCount.toLocaleString('en-US')})` : ''}
              </span>
            </span>
          ) : null}
          {price ? <span>{price}</span> : null}
          {hours ? <span>{hours}</span> : null}
        </div>
      ) : null}
      <TravelCells travel={place.travel} delay={delay} />
    </li>
  )
}

const STAR = 'M12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2Z'

/** Five stars filled to the rating; the number beside it carries the value for screen readers. */
function Stars({ rating }: { rating: number }) {
  const row = (fill: string) =>
    Array.from({ length: 5 }, (_, i) => (
      <svg key={i} viewBox="0 0 24 24" fill={fill} stroke={fill} strokeLinejoin="round" aria-hidden="true">
        <path d={STAR} />
      </svg>
    ))
  return (
    <span className="r2-stars" aria-hidden="true">
      <span>{row('#d3d7c3')}</span>
      <span style={{ width: Math.round((Math.max(0, Math.min(5, rating)) / 5) * 69) }}>{row('#a8690c')}</span>
    </span>
  )
}

/** For each mode, the leg of the category's nearest place by that mode. */
function closestByMode(category: PageCategory): Record<TravelMode, Leg> {
  const out = {} as Record<TravelMode, Leg>
  for (const mode of TRAVEL_MODES) {
    out[mode] = nearest(category, mode)?.travel[mode] ?? { minutes: null, km: null, estimated: false }
  }
  return out
}
