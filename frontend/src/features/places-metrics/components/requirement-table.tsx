import type { CSSProperties } from 'react'

import { FitPill } from '@/features/places-metrics/components/fit-pill'
import { StatusMark } from '@/features/places-metrics/components/status-mark'
import type { ColumnHead, TableRow } from '@/features/places-metrics/utils/requirementTable'

type RequirementTableProps = {
  categoryName: string
  color: string
  timeLabel: string
  heads: ColumnHead[]
  rows: TableRow[]
  onPickPlace: (placeKey: string) => void
}

/**
 * Matrix C: places down, the visible needs across. Each cell gives the answer and what it
 * rests on; the last column is the place's overall fit. Place and Fits stay pinned while
 * the need columns page.
 */
export function RequirementTable({ categoryName, color, timeLabel, heads, rows, onPickPlace }: RequirementTableProps) {
  // Fits column sized to its widest pill ("Fits none" with four beads) so nothing clips.
  const grid = `186px repeat(${heads.length}, minmax(0, 1fr)) 176px`
  return (
    <div className="tc-scroll">
      <div className="tc" role="table" aria-label={`${categoryName}: your needs by place`} style={{ '--cat': color } as CSSProperties}>
        <div className="tc-tr tc-th" role="row" style={{ gridTemplateColumns: grid }}>
          <div className="tc-td" role="columnheader">
            <span className="tc-cap">Place</span>
            <span className="tc-hw">time {timeLabel}</span>
          </div>
          {heads.map((q) => (
            <div key={q.number} className="tc-td" role="columnheader">
              <span className="tc-cap">Need {q.number}</span>
              <span className="tc-hq">{q.short}</span>
              <span className="tc-hw">
                You want: <b>{q.want}</b>
              </span>
              <span className="tc-bar" aria-hidden="true">
                {q.bar.map((g) => (
                  <i key={g.status} className={g.status} style={{ flex: `${g.count} 1 0` }} />
                ))}
              </span>
              <span className="tc-ht num">{q.tally}</span>
            </div>
          ))}
          <div className="tc-td" role="columnheader">
            <span className="tc-cap">Fits your needs</span>
          </div>
        </div>

        <div className="tc-body" role="rowgroup">
          {rows.map((p) => (
            <div
              key={p.key}
              className={`tc-tr${p.selected ? ' sel' : ''}${p.dimmed ? ' dim' : ''}`}
              role="row"
              style={{ gridTemplateColumns: grid }}
            >
              <div className="tc-td" role="rowheader">
                <button
                  type="button"
                  className="tc-pl"
                  aria-pressed={p.selected}
                  aria-label={`${p.name}, open its proof`}
                  onClick={() => onPickPlace(p.key)}
                >
                  <span className="tc-pn">{p.name}</span>
                  <span className="tc-mono num">{p.distance ? `${p.time} · ${p.distance}` : p.time}</span>
                  <span className="tc-go">Open proof ›</span>
                </button>
              </div>
              {p.cells.map((c, i) => (
                <div key={i} className={`tc-td c-${c.status}`} role="cell">
                  <span className="tc-cv">
                    <StatusMark status={c.status} />
                    <span className="tc-sr">{c.label}:</span>
                    <span className={`tc-v ${c.status}`}>{c.value}</span>
                  </span>
                  <span className="tc-mono">{c.basis}</span>
                </div>
              ))}
              <div className="tc-td" role="cell">
                <FitPill tier={p.tier} beads={p.beads} text={p.fitText} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
