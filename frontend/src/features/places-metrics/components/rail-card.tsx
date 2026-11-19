import type { CSSProperties } from 'react'

import { CHEVRON_DOWN } from '@/features/places-metrics/components/icons'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import type { RailGroup } from '@/features/places-metrics/utils/rail'

type RailCardProps = {
  group: RailGroup
  onToggle: () => void
  onPickPlace: (placeKey: string) => void
}

/** A collapsible category card in the rail; each place shows a bead per need on one thread. */
export function RailCard({ group, onToggle, onPickPlace }: RailCardProps) {
  return (
    <div className={`rcard${group.open ? ' open' : ''}`} style={{ '--c': group.color } as CSSProperties}>
      <button type="button" className="ghead" aria-expanded={group.open} onClick={onToggle}>
        <span className="rbadge" aria-hidden="true">
          <PathIcon d={group.icon} />
        </span>
        <span className="ghead-name">{group.name}</span>
        <span className="gcount num">{group.rows.length}</span>
        <PathIcon d={CHEVRON_DOWN} strokeWidth={2} className={`chev${group.open ? ' open' : ''}`} />
      </button>
      {group.open
        ? group.rows.map((row) => (
            <button
              key={row.key}
              type="button"
              className={`railrow r1${row.fitsAll ? ' fitok' : ''}${row.selected ? ' on' : ''}`}
              aria-pressed={row.selected}
              aria-label={`${row.name}, ${row.fitText}, ${row.walk} walk`}
              onClick={() => onPickPlace(row.key)}
            >
              <span className="r1name">{row.name}</span>
              <span className="walk num">{row.walk}</span>
              <span className="r1line">
                <span className="beads" aria-hidden="true">
                  {row.beads.map((b, i) => (
                    <span key={i} className={`bl ${b.status}`} title={b.tip} />
                  ))}
                </span>
                <span className={`rfit num${row.fitsAll ? ' fitok' : ''}`}>{row.fitText}</span>
              </span>
            </button>
          ))
        : null}
    </div>
  )
}
