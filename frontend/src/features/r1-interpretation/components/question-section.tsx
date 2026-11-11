import { useEffect, useRef } from 'react'

import { ClarificationCard } from '@/features/search-progress/components/clarification-card'
import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'
import { cn } from '@/lib/utils'

import './r1.css'

type QuestionSectionProps = {
  /** True while R1 waits for the renter; false folds the section away once answered. */
  open: boolean
  questions: ClarificationQuestion[]
  onSubmit: (answers: ClarificationAnswer[]) => Promise<void> | void
}

/**
 * The follow-up questions as a section of their own, hanging off the "Not sure yet" panel
 * by a short wire. Answering folds it away: the panel above takes over the "cleared up" story.
 */
export function QuestionSection({ open, questions, onSubmit }: QuestionSectionProps) {
  const ref = useRef<HTMLElement>(null)

  // On a narrow screen the card sits below the fold: bring it into view when R1 starts waiting.
  useEffect(() => {
    if (open) {
      ref.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
    }
  }, [open])

  return (
    <div
      aria-hidden={open ? undefined : true}
      inert={!open}
      className={cn(
        'grid transition-[grid-template-rows,opacity] duration-300 ease-Easing-Out motion-reduce:transition-none',
        open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
      )}
    >
      <div className="min-h-0 overflow-hidden">
        <section
          ref={ref}
          aria-label="A question for you"
          className="r1-panel mt-4 [--d:700ms]"
        >
          <div className="rounded-[22px] border border-Step-2/60 bg-Surface-Primary p-5 shadow-[0_6px_22px_color-mix(in_srgb,var(--color-Step-2)_14%,transparent)] backdrop-blur-xl">
            <ClarificationCard questions={questions} onSubmit={onSubmit} />
          </div>
        </section>
      </div>
    </div>
  )
}
