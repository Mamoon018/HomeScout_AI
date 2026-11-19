import type { CSSProperties } from 'react'

import { NeedDonut } from '@/features/places-metrics/components/need-donut'
import { Pager } from '@/features/places-metrics/components/pager'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import type { PlaceFilter } from '@/features/places-metrics/types/placesMetrics'
import type { MetricCardView, NeedSummary } from '@/features/places-metrics/utils/metricCards'
import type { PageWindow } from '@/features/places-metrics/utils/paging'

type MetricCardProps = {
  card: MetricCardView
  index: number
  needsWindow: PageWindow
  shownNeeds: NeedSummary[]
  onFilter: (filter: PlaceFilter | null) => void
  onPageNeeds: (start: number) => void
}

/** One category: total / fit-all / fit-some bars, then a donut per need (two at a time). */
export function MetricCard({ card, index, needsWindow, shownNeeds, onFilter, onPageNeeds }: MetricCardProps) {
  return (
    <article className="mc" aria-label={card.name} style={{ '--c': card.color, '--i': index } as CSSProperties}>
      <div className="mhd">
        <span className="tile mc-tile">
          <PathIcon d={card.icon} size={21} strokeWidth={1.7} />
        </span>
        <h3 className="mtitle">{card.name}</h3>
      </div>

      <div
        className="fun"
        role="group"
        aria-label={`${card.name}: total places, and how many meet all or some asks`}
        style={{ '--m': card.total } as CSSProperties}
      >
        {card.overview.map((row) => (
          <button
            key={row.kind}
            type="button"
            className={`frow ${row.kind}${row.active ? ' on' : ''}`}
            aria-pressed={row.active}
            aria-label={row.aria}
            onClick={() => onFilter(row.tier === null ? null : { category: card.key, tier: row.tier })}
          >
            <span className="flab">
              <span className={`fdot ${row.kind}`} aria-hidden="true" />
              {row.label}
            </span>
            <span className="fval num">{row.count}</span>
            <span className="ftrack" aria-hidden="true">
              <span className={`fbar ${row.kind}`} style={{ width: row.width, '--d': row.delay } as CSSProperties} />
            </span>
          </button>
        ))}
      </div>

      {/* The pager row is reserved even when unused, so every card lines up. */}
      {needsWindow.paged ? (
        <Pager window={needsWindow} onPage={onPageNeeds} />
      ) : (
        <div className="pgr-ph" aria-hidden="true" />
      )}

      <div className="drows">
        {shownNeeds.map((need) => (
          <NeedDonut
            key={need.questionId}
            need={need}
            categoryKey={card.key}
            categoryName={card.name}
            total={card.total}
            onFilter={onFilter}
          />
        ))}
      </div>
    </article>
  )
}
