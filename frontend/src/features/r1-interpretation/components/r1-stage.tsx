import { useEffect, useId, useState } from 'react'
import { CheckIcon, ChevronDownIcon } from 'lucide-react'

import { ExtractionBoard } from '@/features/r1-interpretation/components/extraction-board'
import { PlanResult } from '@/features/r1-interpretation/components/plan-result'
import type {
  CategoryMetricPlan,
  ExtractionOutput,
  R1Phase,
} from '@/features/r1-interpretation/types/r1'
import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'
import { cn } from '@/lib/utils'

import './r1.css'

/** After the plan lands, the breakdown folds up so the plan has the page. */
const FOLD_DELAY = 1200

type R1StageProps = {
  phase: R1Phase
  extraction: ExtractionOutput
  plan: CategoryMetricPlan[]
  questions: ClarificationQuestion[]
  answers: ClarificationAnswer[]
  onSubmitAnswers: (answers: ClarificationAnswer[]) => Promise<void> | void
  /** Fades out before a re-run removes it. */
  leaving?: boolean
}

/**
 * Everything R1 shows after the brief is sent, top to bottom: how it read the brief, the
 * question it needs answered (inside the breakdown), then the plan of what it will look for.
 */
export function R1Stage({
  phase,
  extraction,
  plan,
  questions,
  answers,
  onSubmitAnswers,
  leaving = false,
}: R1StageProps) {
  const readId = useId()
  const [folded, setFolded] = useState(false)
  const done = phase === 'done'
  const boardOpen = !done || !folded

  // Fold the breakdown away once the plan has landed; a re-run opens it again.
  useEffect(() => {
    if (!done) {
      return
    }
    const id = window.setTimeout(() => setFolded(true), FOLD_DELAY)
    return () => {
      window.clearTimeout(id)
      setFolded(false)
    }
  }, [done])

  if (phase === 'idle') {
    return null
  }

  const reading = phase === 'extracting'
  const showPlan = phase === 'planning' || done
  const cleared = answers.length

  return (
    <div
      className={cn(
        'flex w-full max-w-[1120px] flex-col transition-opacity duration-200 ease-Easing-Out',
        leaving ? 'opacity-0' : 'opacity-100',
      )}
    >
      {/* How I read your brief */}
      <section aria-labelledby={readId} className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3 px-1">
          <div className="flex min-w-0 items-center gap-3">
            <h2
              id={readId}
              className="m-0 text-2xl leading-8 font-semibold tracking-[-0.02em] text-(--tracker-heading)"
            >
              Instructions{' '}
              <em className="font-[Fraunces,Georgia,serif] font-medium text-[#1F7A80] italic">decoded</em>
            </h2>
            {reading ? (
              <ReadingDots />
            ) : phase === 'asking' ? (
              <span className="rounded-full border border-Step-2/40 bg-Step-2/10 px-2.5 py-0.5 text-xs font-semibold text-Step-2">
                Needs one answer from you
              </span>
            ) : (
              <DoneMark />
            )}
          </div>
          {done ? (
            <button
              type="button"
              aria-expanded={boardOpen}
              onClick={() => setFolded(boardOpen)}
              className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-(--fs-option-border) bg-(--fs-option) px-3 py-1.5 text-xs font-semibold text-foreground outline-none transition-colors duration-200 hover:border-(--fs-accent) focus-visible:ring-2 focus-visible:ring-Brand-500/60"
            >
              {boardOpen ? 'Hide breakdown' : 'Show breakdown'}
              <ChevronDownIcon
                aria-hidden="true"
                className={cn(
                  'size-3.5 transition-transform duration-300 ease-Easing-Out motion-reduce:transition-none',
                  boardOpen && 'rotate-180',
                )}
              />
            </button>
          ) : null}
        </div>

        {!boardOpen ? (
          <p className="m-0 px-1 text-sm text-muted-foreground">
            {extraction.persona_facts.length} things about you ·{' '}
            {extraction.explicit_categories.length} things you asked for
            {cleared > 0 ? ` · ${cleared} cleared up` : ''}
          </p>
        ) : null}

        <div
          inert={!boardOpen}
          className={cn(
            'grid transition-[grid-template-rows,opacity] duration-500 ease-Easing-Out motion-reduce:transition-none',
            boardOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
          )}
        >
          {/* Generous padding keeps the panels' shadows and blur inside the clip. */}
          <div className="-mx-8 -mb-8 min-h-0 overflow-hidden px-8 pb-14">
            <ExtractionBoard
              data={extraction}
              phase={phase}
              questions={questions}
              answers={answers}
              onSubmitAnswers={onSubmitAnswers}
            />
          </div>
        </div>
      </section>

      {/* What I'll look for */}
      {showPlan ? (
        <section aria-labelledby={`${readId}-plan`} className="r1-pull mt-2 flex flex-col gap-3">
          <div className="px-1">
            <div className="flex items-center gap-3">
              <h2
                id={`${readId}-plan`}
                className="m-0 text-lg leading-7 font-semibold tracking-normal text-(--tracker-heading)"
              >
                What I&apos;ll look for
              </h2>
              {done ? <DoneMark /> : <ReadingDots />}
            </div>
            <p className="m-0 text-sm text-muted-foreground">
              {done
                ? 'This is the plan, not the findings: nothing below has been looked up yet.'
                : 'Deciding which places matter and how deep to go for each.'}
            </p>
          </div>
          {done ? <PlanResult plan={plan} extraction={extraction} /> : <PlanPlaceholder />}
        </section>
      ) : null}
    </div>
  )
}

function ReadingDots() {
  return (
    <span role="status" className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
      <span aria-hidden="true" className="flex items-center gap-1">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1 animate-typing-dot rounded-full bg-Brand-500 motion-reduce:animate-none"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      Working
    </span>
  )
}

function DoneMark() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-Status-Success">
      <span
        aria-hidden="true"
        className="grid size-4 place-items-center rounded-full border-[1.5px] border-Status-Success"
      >
        <CheckIcon className="size-2.5" strokeWidth={3.5} />
      </span>
      Done
    </span>
  )
}

/** Two quiet sheets stand in while the plan is decided. */
function PlanPlaceholder() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-3">
      {[0, 1].map((i) => (
        <div
          key={i}
          className="r1-sheen h-[76px] rounded-[22px] border border-Border-Subtle bg-Surface-Primary"
          style={{ animationDelay: `${i * 250}ms` }}
        />
      ))}
    </div>
  )
}
