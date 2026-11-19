import type { CSSProperties } from 'react'

import { BallTip } from '@/features/r2-proximity/components/ball-tip'
import type { PageCategory } from '@/features/r2-proximity/utils/present'
import { RING, ringMarkers, shadeStart, type Marker } from '@/features/r2-proximity/utils/summary'

type ReachRingProps = {
  categories: PageCategory[]
  reach: number
  selected: number | null
  onSelect: (categoryId: number) => void
}

const RINGS = [5, 10, 15, 20]
/** Past this radius a label points back toward the centre so it never leaves the outer ring. */
const LABEL_FLIP_RADIUS = 104

/**
 * Walking only: one ball per category (its nearest place), distance from the centre in walking
 * minutes. A supplementary picture: the same numbers are in the strip, the rail and the cards,
 * so it is hidden from assistive tech and its balls are not in the tab order.
 */
export function ReachRing({ categories, reach, selected, onSelect }: ReachRingProps) {
  const markers = ringMarkers(categories)
  const shade = shadeStart(markers, reach)
  const scale = RING.radius / RING.maxMinutes
  const disc = reach * scale * 2

  return (
    <div aria-hidden="true" className="r2-ring-stage">
      {shade !== null ? (
        <div
          className="r2-shade"
          style={{
            background: `conic-gradient(from ${shade}deg, transparent 0deg, rgba(74,90,42,.2) 75deg, transparent 150deg, transparent 360deg)`,
          }}
        />
      ) : null}
      <div className="r2-disc" style={{ width: disc, height: disc }} />
      {RINGS.map((m, i) => (
        <div
          key={m}
          className="r2-ring"
          style={{ width: m * scale * 2, height: m * scale * 2, '--d': `${i * 80}ms` } as CSSProperties}
        />
      ))}
      {RINGS.map((m) => (
        <span key={m} className="r2-axl" style={{ left: RING.size / 2 + 5, top: RING.size / 2 - m * scale - 7 }}>
          {m} mins
        </span>
      ))}
      <div className="r2-apt" />
      {markers.map((m, i) => {
        const at = labelPlacement(m)
        return (
          <span
            key={`label-${m.category.id}`}
            className="r2-mk-name"
            data-side={at.side}
            data-sel={m.category.id === selected}
            data-out={m.minutes > reach}
            style={{ left: at.x, top: at.y, '--mc': m.category.color, '--d': `${700 + i * 90}ms` } as CSSProperties}
          >
            {m.category.label}
          </span>
        )
      })}
      {markers.map((m, i) => (
        <button
          key={m.category.id}
          type="button"
          tabIndex={-1}
          className="r2-ball r2-mk"
          data-sel={m.category.id === selected}
          data-out={m.minutes > reach}
          onClick={() => onSelect(m.category.id)}
          style={{ left: m.x, top: m.y, '--mc': m.category.color, '--d': `${520 + i * 90}ms` } as CSSProperties}
        >
          <BallTip category={m.category.label} time={`${m.minutes} min walk`} place={m.place.name} />
        </button>
      ))}
    </div>
  )
}

/**
 * Where a ball's name sits: just outside the ball, on the side facing away from the centre, so
 * names fan outward and never sit on top of the apartment. Balls near the outer ring point
 * their name back inward instead. Near the top or bottom the name is centred above or below.
 */
function labelPlacement(m: Marker): { side: 'top' | 'bottom' | 'left' | 'right'; x: number; y: number } {
  const centre = RING.size / 2
  const dx = m.x - centre
  const dy = m.y - centre
  const r = Math.hypot(dx, dy)
  const out = r <= LABEL_FLIP_RADIUS ? 1 : -1
  // Unit vector from the centre through the ball (pointing inward when flipped).
  const ux = r === 0 ? 1 : (dx / r) * out
  const uy = r === 0 ? 0 : (dy / r) * out
  const gap = 11
  const x = m.x + ux * gap
  const y = m.y + uy * gap
  if (Math.abs(ux) < 0.42) {
    return { side: uy < 0 ? 'top' : 'bottom', x, y }
  }
  return { side: ux > 0 ? 'right' : 'left', x, y }
}
