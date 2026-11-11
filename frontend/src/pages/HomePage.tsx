import { useLayoutEffect, useRef } from 'react'

import { NeighborhoodBriefComposer } from '@/features/composer/components/neighborhood-brief-composer'
import { ResultPreview } from '@/features/search-progress/components/result-preview'
import { SearchProgressTimeline } from '@/features/search-progress/components/search-progress-timeline'
import { useSearchRun } from '@/features/search-progress/hooks/useSearchRun'
import { progressAnnouncement, RUN_TIMING } from '@/features/search-progress/utils/searchSteps'
import { cn } from '@/lib/utils'
import { useDocumentClasses } from '@/lib/useDocumentClasses'

const HOME_THEME = ['theme-olive']

type HomePageProps = {
  message: string | null
}

/** Authenticated homepage. Greeting comes from the identity-scoped welcome API. */
export function HomePage({ message }: HomePageProps) {
  const run = useSearchRun()
  const composerRef = useRef<HTMLDivElement>(null)
  const composerStartTop = useRef<number | null>(null)

  // Olive Glass theme for the Home page.
  useDocumentClasses(HOME_THEME)

  // While the heading fades the layout hasn't changed yet: remember where the composer is.
  useLayoutEffect(() => {
    if (run.headingState === 'fading') {
      composerStartTop.current = composerRef.current?.getBoundingClientRect().top ?? null
    }
  }, [run.headingState])

  // After the layout jumps to the top, slide the composer from its old spot (FLIP).
  useLayoutEffect(() => {
    const el = composerRef.current
    const startTop = composerStartTop.current
    if (!run.movedUp || !el || startTop === null) {
      return
    }
    composerStartTop.current = null
    const delta = startTop - el.getBoundingClientRect().top
    if (delta !== 0 && typeof el.animate === 'function') {
      el.animate([{ transform: `translateY(${delta}px)` }, { transform: 'translateY(0)' }], {
        duration: RUN_TIMING.composerMove,
        easing: 'cubic-bezier(0, 0, 0.2, 1)',
      })
    }
  }, [run.movedUp])

  return (
    <main
      className={cn(
        // No background here: the themed <body> gradient shows through.
        'flex min-h-svh flex-col items-center gap-8 px-4 py-12 text-foreground',
        run.movedUp ? 'justify-start' : 'justify-center',
      )}
    >
      {/* P1 — welcome heading: fades on the first search, then leaves the layout */}
      <div
        hidden={run.headingState === 'hidden'}
        className={cn(
          // Same width as the composer column so the 44px heading stays on one line.
          'w-full max-w-[770px] text-center transition-opacity duration-200 ease-Easing-Out',
          run.headingState === 'fading' && 'opacity-0',
        )}
      >
        {/* Shown once the welcome API confirms the session; the copy itself is fixed. */}
        {message ? (
          <h1 className="m-0 text-[44px] leading-[normal] font-semibold tracking-normal text-(--home-heading)">
            Start your Homescout
          </h1>
        ) : null}
      </div>

      <div className="flex w-full max-w-[770px] flex-col gap-6">
        {/* P2 — composer */}
        <div ref={composerRef}>
          <NeighborhoodBriefComposer locked={run.locked} onSubmit={run.start} />
        </div>

        {run.timelineVisible ? (
          <SearchProgressTimeline activeStep={run.activeStep} resetting={run.resetting} />
        ) : null}

        {run.resultVisible ? <ResultPreview leaving={run.resetting} /> : null}
      </div>

      <p aria-live="polite" className="sr-only">
        {run.timelineVisible ? progressAnnouncement(run.activeStep) : ''}
      </p>
    </main>
  )
}
