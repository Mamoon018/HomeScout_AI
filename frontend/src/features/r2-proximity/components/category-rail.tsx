import type { CSSProperties } from 'react'

import { TaxonomyIcon } from '@/features/r1-interpretation/components/glyphs'
import { nearest, type PageCategory } from '@/features/r2-proximity/utils/present'

type CategoryRailProps = {
  categories: PageCategory[]
  selected: number | null
  onSelect: (categoryId: number) => void
}

/** Every category in the plan's order, with its count and nearest walk. Empty ones stay. */
export function CategoryRail({ categories, selected, onSelect }: CategoryRailProps) {
  return (
    <nav
      aria-label="Categories"
      className="r2-glass r2-enter flex max-w-full flex-[0_0_280px] flex-col gap-0.5 self-start rounded-[22px] p-2 lg:sticky lg:top-4"
      style={{ '--d': '280ms' } as CSSProperties}
    >
      {categories.map((c) => {
        const n = c.places.length
        const walk = nearest(c, 'walk')?.travel.walk.minutes ?? null
        return (
          <button
            key={c.id}
            type="button"
            className="r2-rr"
            aria-pressed={c.id === selected}
            data-none={n === 0}
            onClick={() => onSelect(c.id)}
          >
            <span className="r2-tile size-9" data-fam={c.family} aria-hidden="true">
              <TaxonomyIcon node={c.node} className="size-[19px]" strokeWidth={1.7} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm leading-[19px] font-semibold">
                {n > 0 ? <i className="r2-dot" style={{ '--mc': c.color } as CSSProperties} /> : null}
                {c.label}
              </span>
              <span className="block text-xs leading-4 text-(--fs-muted)">
                {n === 0 ? 'None found' : `${n} ${n === 1 ? 'place' : 'places'}${c.capped ? ' (nearest 10)' : ''}`}
              </span>
            </span>
            {walk !== null ? (
              <span className="flex-none text-right">
                <span className="block text-[15px] leading-[18px] font-bold tabular-nums">{walk} min</span>
                <span className="block text-[11px] leading-[14px] text-(--fs-muted)">on foot</span>
              </span>
            ) : null}
          </button>
        )
      })}
    </nav>
  )
}
