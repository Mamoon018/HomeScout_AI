import { CHEVRON_LEFT, CHEVRON_RIGHT } from '@/features/places-metrics/components/icons'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import type { PageWindow } from '@/features/places-metrics/utils/paging'

type PagerProps = {
  window: PageWindow
  onPage: (start: number) => void
  className?: string
}

/** "Needs 1–2 of 4" with ‹ › buttons; an unavailable direction is dimmed and inert. */
export function Pager({ window: w, onPage, className = '' }: PagerProps) {
  return (
    <div className={`pgr ${className}`}>
      <span className="num" aria-live="polite">
        {w.label}
      </span>
      <span className="pgbtns">
        <button
          type="button"
          className={`pgb${w.hasPrev ? '' : ' off'}`}
          aria-disabled={!w.hasPrev}
          aria-label={w.prevLabel}
          onClick={() => w.hasPrev && onPage(w.prevStart)}
        >
          <PathIcon d={CHEVRON_LEFT} strokeWidth={2.2} />
        </button>
        <button
          type="button"
          className={`pgb${w.hasNext ? '' : ' off'}`}
          aria-disabled={!w.hasNext}
          aria-label={w.nextLabel}
          onClick={() => w.hasNext && onPage(w.nextStart)}
        >
          <PathIcon d={CHEVRON_RIGHT} strokeWidth={2.2} />
        </button>
      </span>
    </div>
  )
}
