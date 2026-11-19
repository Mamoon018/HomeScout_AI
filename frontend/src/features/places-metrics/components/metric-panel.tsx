import { CHECK_ICON } from '@/features/places-metrics/components/icons'
import { MetricCard } from '@/features/places-metrics/components/metric-card'
import { Pager } from '@/features/places-metrics/components/pager'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import type { CategoryKey, PlaceFilter } from '@/features/places-metrics/types/placesMetrics'
import type { MetricCardView, NeedSummary } from '@/features/places-metrics/utils/metricCards'
import type { PageWindow } from '@/features/places-metrics/utils/paging'

type MetricPanelProps = {
  cardWindow: PageWindow
  shownCards: { card: MetricCardView; needsWindow: PageWindow; shownNeeds: NeedSummary[] }[]
  filterHint: string
  onFilter: (filter: PlaceFilter | null) => void
  onPageCards: (start: number) => void
  onPageNeeds: (category: CategoryKey, start: number) => void
}

/** "Do nearby places really fit?": every category's fit at a glance, three cards at a time. */
export function MetricPanel({ cardWindow, shownCards, filterHint, onFilter, onPageCards, onPageNeeds }: MetricPanelProps) {
  return (
    <section className="panel mp" aria-labelledby="mp-title">
      <div className="mp-head">
        <h2 id="mp-title" className="mp-title">
          Do nearby places <em className="mpem">really</em> fit?
        </h2>
        <p className="mpkeys">
          <span>Checked against your needs</span>
          <span className="mpdot" aria-hidden="true">
            ·
          </span>
          <span className="proof">
            <PathIcon d={CHECK_ICON} size={13} strokeWidth={2.2} />
            with proof
          </span>
        </p>
      </div>
      <div className="mpcard">
        {cardWindow.paged ? <Pager window={cardWindow} onPage={onPageCards} /> : null}
        <div className="mgrid">
          {shownCards.map(({ card, needsWindow, shownNeeds }, i) => (
            <MetricCard
              key={card.key}
              card={card}
              index={i}
              needsWindow={needsWindow}
              shownNeeds={shownNeeds}
              onFilter={onFilter}
              onPageNeeds={(start) => onPageNeeds(card.key, start)}
            />
          ))}
        </div>
      </div>
      <p className="mp-hint">{filterHint}</p>
    </section>
  )
}
