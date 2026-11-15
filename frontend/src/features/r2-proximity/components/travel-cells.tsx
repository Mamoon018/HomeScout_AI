import { ModeIcon } from '@/features/r2-proximity/components/mode-icon'
import { TRAVEL_MODES, type Leg, type TravelMode } from '@/features/r2-proximity/types/r2'
import { MODE_LABEL } from '@/features/r2-proximity/utils/present'
import { cn } from '@/lib/utils'

/** Every bar on the page shares this scale, so modes and places compare by eye. */
export const BAR_SCALE_MIN = 30

type TravelCellsProps = {
  travel: Record<TravelMode, Leg>
  /** Shows the mode-strip size (category header) instead of the card size. */
  big?: boolean
  delay?: number
}

/** Walk, Cycle, Drive, Transit, always in that order. Walk leads. */
export function TravelCells({ travel, big = false, delay = 0 }: TravelCellsProps) {
  return (
    <div className={cn('r2-cells', big && 'r2-big')}>
      {TRAVEL_MODES.map((mode) => {
        const leg = travel[mode]
        const none = leg.minutes === null
        const clipped = !none && (leg.minutes as number) >= BAR_SCALE_MIN
        const label = none
          ? `${MODE_LABEL[mode]}: no route`
          : `${MODE_LABEL[mode]}: ${leg.minutes} minutes${leg.estimated ? ', estimated' : ''}`
        return (
          <div key={mode} className="r2-cell" data-lead={mode === 'walk'} data-none={none} role="group" aria-label={label}>
            <div className="r2-cl" aria-hidden="true">
              <ModeIcon mode={mode} className={big ? 'size-4' : 'size-3.5'} />
              <span>{MODE_LABEL[mode]}</span>
              {leg.estimated ? <span className="r2-est">est.</span> : null}
            </div>
            <div className="r2-cv" aria-hidden="true">
              <b>{none ? '–' : clipped ? '30+' : leg.minutes}</b>
              {none ? null : <span className="r2-cu">min</span>}
            </div>
            <div className="r2-bar" aria-hidden="true">
              <i
                style={{
                  width: `${none ? 0 : Math.min(100, ((leg.minutes as number) / BAR_SCALE_MIN) * 100)}%`,
                  animationDelay: `${delay}ms`,
                }}
              />
            </div>
            <div className="r2-ck" aria-hidden="true">
              {none ? 'No route' : mode === 'walk' && leg.km !== null ? `${leg.km.toFixed(1)} km` : ' '}
            </div>
          </div>
        )
      })}
    </div>
  )
}
