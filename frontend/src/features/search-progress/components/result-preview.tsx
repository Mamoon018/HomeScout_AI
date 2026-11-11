import { ArrowRightIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type ResultPreviewProps = {
  /** Fades out before a re-run removes it. */
  leaving?: boolean
  className?: string
}

/** R0 — Result Preview card shown after the last step. Dummy content for now. */
export function ResultPreview({ leaving = false, className }: ResultPreviewProps) {
  return (
    <section
      aria-label="Result"
      className={cn(
        'flex w-full flex-col gap-2 rounded-[22px] border border-Border-Subtle bg-Surface-Primary p-5 shadow-[0_8px_24px_rgba(0,0,0,0.18)] backdrop-blur-xl',
        'animate-in fade-in-0 slide-in-from-bottom-2 animation-duration-300 ease-Easing-Out',
        'transition-opacity duration-200',
        leaving && 'opacity-0',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-foreground">Neighborhood Match</h2>
        <span className="shrink-0 rounded-full border border-Status-Success/40 bg-Status-Success/10 px-2.5 py-0.5 text-xs font-semibold text-Status-Success tabular-nums">
          82 / 100
        </span>
      </div>
      <p className="line-clamp-2 text-sm text-muted-foreground">
        This area matches 4 of your 5 priorities. Strong on parks and quiet streets; weaker on
        public transport access.
      </p>
      <Button
        type="button"
        variant="link"
        className="h-auto w-fit gap-1 px-0 text-Brand-500"
      >
        See full report
        <ArrowRightIcon data-icon="inline-end" />
      </Button>
    </section>
  )
}
