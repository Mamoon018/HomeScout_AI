import { useLayoutEffect, useRef } from 'react'

import { OliveSiteHeader } from '@/components/olive-site-header'
import '@/features/auth/components/olive-hero.css'
import { NeighborhoodBriefComposer } from '@/features/composer/components/neighborhood-brief-composer'
import { R1Stage } from '@/features/r1-interpretation/components/r1-stage'
import { useR1Run } from '@/features/r1-interpretation/hooks/useR1Run'
import type { CategoryMetricPlan, ExtractionOutput } from '@/features/r1-interpretation/types/r1'
import { DUMMY_EXTRACTION } from '@/features/r1-interpretation/utils/dummyExtraction'
import { DUMMY_PLAN } from '@/features/r1-interpretation/utils/dummyPlan'
import { R1_TIMING } from '@/features/r1-interpretation/utils/timing'
import type { ClarificationQuestion } from '@/features/search-progress/types/clarification'
import { DUMMY_CLARIFICATION_QUESTIONS } from '@/features/search-progress/utils/dummyClarification'
import { cn } from '@/lib/utils'
import { useDocumentClasses } from '@/lib/useDocumentClasses'

const HOME_THEME = ['theme-olive']

const ANNOUNCEMENTS = {
  idle: '',
  extracting: 'Reading your brief.',
  asking: 'Reading done. One question needs your answer.',
  planning: 'Deciding what to look for.',
  done: 'Done. The plan of what to look for is ready.',
} as const

type HomePageProps = {
  message: string | null
  /** Questions R1 asks once the run reaches the clarity check. Empty = never pause. */
  clarificationQuestions?: ClarificationQuestion[]
  /** R1's extraction output and finished plan. Dummy data until the endpoints are wired. */
  extraction?: ExtractionOutput
  plan?: CategoryMetricPlan[]
}

/** Authenticated homepage. Greeting comes from the identity-scoped welcome API. */
export function HomePage({
  message,
  clarificationQuestions = DUMMY_CLARIFICATION_QUESTIONS,
  extraction = DUMMY_EXTRACTION,
  plan = DUMMY_PLAN,
}: HomePageProps) {
  const run = useR1Run(clarificationQuestions.length > 0)
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
        duration: R1_TIMING.composerMove,
        easing: 'cubic-bezier(0, 0, 0.2, 1)',
      })
    }
  }, [run.movedUp])

  const announcement = ANNOUNCEMENTS[run.phase]

  return (
    <div className="flex min-h-svh flex-col">
      <div className="mx-auto w-full max-w-[1440px] px-6 pt-10 md:px-10 xl:px-[30px]">
        <OliveSiteHeader />
      </div>
      <main
        className={cn(
          // No background here: the themed <body> gradient shows through.
          'flex flex-1 flex-col items-center gap-8 px-4 py-12 text-foreground',
          run.movedUp ? 'justify-start' : 'justify-center',
        )}
      >
        {/* P1 — welcome heading: fades on the first search, then leaves the layout */}
        <div
          hidden={run.headingState === 'hidden'}
          className={cn(
            // Same width as the composer column so the heading stays on one line.
            'w-full max-w-[770px] text-center transition-opacity duration-200 ease-Easing-Out',
            run.headingState === 'fading' && 'opacity-0',
          )}
        >
          {/* Shown once the welcome API confirms the session; the copy itself is fixed. */}
          {message ? (
            // Same voice as the sign-in hero: Manrope line, Fraunces italic keyword in the accent.
            <h1 className="oh-primary m-0 text-(--fs-ink)">
              Start your <em className="oh-keyword">Homescout</em>
            </h1>
          ) : null}
        </div>

        {/* Once R1 starts, the composer widens to the breakdown's width so the two line up. */}
        <div
          className={cn(
            'flex w-full flex-col gap-6 transition-[max-width] duration-400 ease-Easing-Out motion-reduce:transition-none',
            run.movedUp ? 'max-w-[1120px]' : 'max-w-[770px]',
          )}
        >
          {/* P2 — composer */}
          <div ref={composerRef}>
            <NeighborhoodBriefComposer
              locked={run.locked}
              onSubmit={run.start}
              // The composer caps itself at 770px; lift that once R1 starts so it fills the wrapper.
              className={run.movedUp ? 'max-w-none' : undefined}
            />
          </div>
        </div>

        <R1Stage
          phase={run.phase}
          extraction={extraction}
          plan={plan}
          questions={clarificationQuestions}
          answers={run.answers}
          onSubmitAnswers={run.submitAnswers}
          leaving={run.resetting}
        />
        <p aria-live="polite" className="sr-only">
          {announcement}
        </p>
      </main>
    </div>
  )
}
