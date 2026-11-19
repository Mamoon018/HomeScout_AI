import { Fragment } from 'react'

import { SORT_ICON } from '@/features/places-metrics/components/icons'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import type { CategoryKey, SortMode } from '@/features/places-metrics/types/placesMetrics'

const OPTIONS: { mode: SortMode; label: string }[] = [
  { mode: 'fit', label: 'Best fit' },
  { mode: 'walk', label: 'Walk' },
  { mode: 'cycle', label: 'Cycle' },
  { mode: 'drive', label: 'Drive' },
  { mode: 'transit', label: 'Transit' },
]

type SortBarProps = {
  categoryKey: CategoryKey
  sort: SortMode
  onSort: (mode: SortMode) => void
}

/** "Sort places by": best fit, or quickest by one travel mode (also sets the time column). */
export function SortBar({ categoryKey, sort, onSort }: SortBarProps) {
  const labelId = `sortlab-${categoryKey}`
  return (
    <div className="sortbar">
      <div className="sortbar-in">
        <span className="sortlab" id={labelId}>
          Sort places by
        </span>
        <div className="sorttrack" role="radiogroup" aria-labelledby={labelId}>
          {OPTIONS.map((o) => (
            <Fragment key={o.mode}>
              <button
                type="button"
                role="radio"
                className={`segb${sort === o.mode ? ' on' : ''}`}
                aria-checked={sort === o.mode}
                onClick={() => onSort(o.mode)}
              >
                <PathIcon d={SORT_ICON[o.mode]} size={14} />
                {o.label}
              </button>
              {o.mode === 'fit' ? <span className="segdiv" aria-hidden="true" /> : null}
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}
