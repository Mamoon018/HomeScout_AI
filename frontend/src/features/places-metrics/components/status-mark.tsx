import { STATUS_ICON } from '@/features/places-metrics/components/icons'
import type { Status } from '@/features/places-metrics/types/placesMetrics'

type StatusMarkProps = {
  status: Status
  small?: boolean
}

/** The round verdict mark: filled tick, wave, cross, or a dashed question for no info. */
export function StatusMark({ status, small = false }: StatusMarkProps) {
  return (
    <span className={`tc-st ${status}${small ? ' sm' : ''}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={STATUS_ICON[status]} />
      </svg>
    </span>
  )
}
