import { RailCard } from '@/features/places-metrics/components/rail-card'
import type { CategoryKey } from '@/features/places-metrics/types/placesMetrics'
import type { RailGroup } from '@/features/places-metrics/utils/rail'

type PlacesRailProps = {
  title: string
  sub: string
  filtered: boolean
  groups: RailGroup[]
  onClearFilter: () => void
  onToggleGroup: (category: CategoryKey, openNow: boolean) => void
  onPickPlace: (placeKey: string) => void
}

/** "All places": every place by category, or only the ones a metric-panel filter picked. */
export function PlacesRail({ title, sub, filtered, groups, onClearFilter, onToggleGroup, onPickPlace }: PlacesRailProps) {
  return (
    <nav className="panel rail" aria-label="All places">
      <div className="rail-head">
        <div className="rail-titlerow">
          <h2 className="rail-title">{title}</h2>
          {filtered ? (
            <button type="button" className="txtbtn" onClick={onClearFilter}>
              Show all
            </button>
          ) : null}
        </div>
        <span className="rail-sub">{sub}</span>
      </div>
      {groups.map((g) => (
        <RailCard key={g.key} group={g} onToggle={() => onToggleGroup(g.key, g.open)} onPickPlace={onPickPlace} />
      ))}
    </nav>
  )
}
