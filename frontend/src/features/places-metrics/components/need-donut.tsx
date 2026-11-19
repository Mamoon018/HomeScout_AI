import type { CSSProperties } from 'react'

import type { PlaceFilter, Status } from '@/features/places-metrics/types/placesMetrics'
import type { NeedSummary } from '@/features/places-metrics/utils/metricCards'

type NeedDonutProps = {
  need: NeedSummary
  categoryKey: PlaceFilter['category']
  categoryName: string
  total: number
  onFilter: (filter: PlaceFilter) => void
}

const ARC_ORDER: Status[] = ['y', 'l', 'n', 'u']

/**
 * One need inside a category card: its name and what the renter requires, a donut of how
 * the places answered, and a legend whose chips list those places in the rail.
 */
export function NeedDonut({ need, categoryKey, categoryName, total, onFilter }: NeedDonutProps) {
  return (
    <div className="drow">
      <div className="alab3">
        <span className="aname">{need.short}</span>
        <div className="areq">
          <span className="awant">required: {need.want}</span>
          {need.weak ? <span className="wk">lacks</span> : null}
        </div>
      </div>
      <div className="dmid">
        <div className="dwrap">
          <svg className="dsvg" viewBox="0 0 100 100" role="img" aria-label={need.donutAria}>
            <circle className="dtrk" cx="50" cy="50" r="40" pathLength={100} />
            {ARC_ORDER.map((k) => (
              <circle
                key={k}
                className={`arc ${k}${need.arcs[k].hidden ? ' z' : ''}`}
                cx="50"
                cy="50"
                r="40"
                pathLength={100}
                strokeDasharray={need.arcs[k].dash}
                strokeDashoffset={need.arcs[k].offset}
              />
            ))}
          </svg>
          {/* Centre: fits count by default; a hovered legend chip swaps in its own count. */}
          <div className="dcen" aria-hidden="true">
            <b className="num">
              <span className="cnt" style={{ '--n': need.fits } as CSSProperties} />
            </b>
            <span>of {total}</span>
          </div>
          {need.segments.map((sg) => (
            <div key={sg.status} className={`dcs ${sg.status}`} aria-hidden="true">
              <b className="num">{sg.count}</b>
              <span>{sg.label}</span>
            </div>
          ))}
        </div>
        <div className="dleg" role="group" aria-label={`${categoryName}, ${need.short}: list places by answer`}>
          {need.segments.map((sg) => (
            <button
              key={sg.status}
              type="button"
              className={`dlegb ${sg.status}${sg.active ? ' on' : ''}`}
              aria-pressed={sg.active}
              aria-label={sg.aria}
              onClick={() => onFilter({ category: categoryKey, question: need.questionId, status: sg.status })}
            >
              <span className={`dsw ${sg.status}`} />
              <b className="num">{sg.count}</b>
              <span>{sg.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
