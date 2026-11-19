import { useEffect, useId, useState } from 'react'
import { CheckIcon, ChevronDownIcon, TriangleAlertIcon } from 'lucide-react'

import { ExtractionBoard } from '@/features/r1-interpretation/components/extraction-board'
import { ExtractionSkeleton } from '@/features/r1-interpretation/components/extraction-skeleton'
import { PlanResult } from '@/features/r1-interpretation/components/plan-result'
import { RunNotice } from '@/features/r1-interpretation/components/run-notice'
import type { R1Notice, R1Waiting } from '@/features/r1-interpretation/hooks/useR1Run'
import type {
  CategoryMetricPlan,
  ExtractionOutput,
  R1Phase,
} from '@/features/r1-interpretation/types/r1'
import { taxonomyLabel } from '@/features/r1-interpretation/utils/present'
import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'
import { cn } from '@/lib/utils'

import './r1.css'

/** After the plan lands, the breakdown folds up so the plan has the page. */
const FOLD_DELAY = 1200
/** After this long the wait says it is still going, so it never looks frozen. */
const SLOW_AFTER_MS = 12_000

type R1StageProps = {
  phase: R1Phase
  /** Null until the run has saved the extraction step. */
  extraction: ExtractionOutput | null
  plan: CategoryMetricPlan[] | null
  questions: ClarificationQuestion[]
  /** Changes each time the run asks, so a card that stuck on "sending" starts fresh. */
  asked: number
  answers: ClarificationAnswer[]
  onSubmitAnswers: (answers: ClarificationAnswer[]) => Promise<void> | void
  /** Set while the run is stopped and the renter has to choose what to do. */
  notice: R1Notice | null
  /** Which call the stage is waiting on. */
  waiting: R1Waiting | null
  /** The last brief is still known, so Start again can send it. */
  hasBrief: boolean
  onRetry: () => void
  onStartAgain: () => void
  onReload: () => void
  /** Fades out before a re-run removes it. */
  leaving?: boolean
}

/**
 * Everything R1 shows after the brief is sent, top to bottom: how it read the brief, the
 * question it needs answered (inside the breakdown), then the plan of what it will look for.
 * When the run stops, the notice takes the place of whatever was still to come.
 */
export function R1Stage({
  phase,
  extraction,
  plan,
  questions,
  asked,
  answers,
  onSubmitAnswers,
  notice,
  waiting,
  hasBrief,
  onRetry,
  onStartAgain,
  onReload,
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

  if (phase === 'idle' && notice === null) {
    return null
  }

  const reading = extraction === null && notice === null
  const showPlan = extraction !== null && (phase === 'planning' || done)
  // A restored run has no local answers; its plan still says what each flagged phrase became.
  const shownAnswers =
    answers.length > 0 || !done || extraction === null ? answers : meaningsFromPlan(extraction, plan)
  const cleared = shownAnswers.length
  const notice_ = (stage: 'reading' | 'planning') =>
    notice === null ? null : (
      <RunNotice
        notice={notice}
        stage={stage}
        hasBrief={hasBrief}
        onRetry={onRetry}
        onStartAgain={onStartAgain}
        onReload={onReload}
      />
    )

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
            {notice !== null && extraction === null ? (
              <StoppedMark />
            ) : reading ? (
              <ReadingDots />
            ) : phase === 'asking' ? (
              <span className="rounded-full border border-Step-2/40 bg-Step-2/10 px-2.5 py-0.5 text-xs font-semibold text-Step-2">
                Needs one answer from you
              </span>
            ) : (
              <DoneMark />
            )}
          </div>
          {done && extraction ? (
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

        {reading ? <WaitNote waiting={waiting ?? 'start'} /> : null}

        {extraction !== null && !boardOpen ? (
          <p className="m-0 px-1 text-sm text-muted-foreground">
            {extraction.persona_facts.length}{' '}
            {extraction.persona_facts.length === 1 ? 'thing' : 'things'} about you ·{' '}
            {extraction.explicit_categories.length}{' '}
            {extraction.explicit_categories.length === 1 ? 'thing' : 'things'} you asked for
            {cleared > 0 ? ` · ${cleared} cleared up` : ''}
          </p>
        ) : null}

        {extraction !== null ? (
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
                asked={asked}
                answers={shownAnswers}
                onSubmitAnswers={onSubmitAnswers}
              />
            </div>
          </div>
        ) : notice === null ? (
          <ExtractionSkeleton />
        ) : (
          notice_('reading')
        )}
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
              {done ? <DoneMark /> : notice !== null ? <StoppedMark /> : <ReadingDots />}
            </div>
            {done || notice === null ? (
              <p className="m-0 text-sm text-muted-foreground">
                {done
                  ? 'This is the plan, not the findings: nothing below has been looked up yet.'
                  : 'Deciding which places matter and how deep to go for each.'}
              </p>
            ) : null}
            {!done && notice === null ? <WaitNote waiting={waiting ?? 'answers'} planning /> : null}
          </div>
          {done ? (
            <PlanResult plan={plan ?? []} extraction={extraction} />
          ) : notice !== null ? (
            notice_('planning')
          ) : (
            <PlanPlaceholder />
          )}
        </section>
      ) : null}
    </div>
  )
}

/** What each flagged phrase became, read from the plan's categories, for a run restored after a refresh. */
function meaningsFromPlan(
  extraction: ExtractionOutput,
  plan: CategoryMetricPlan[] | null,
): ClarificationAnswer[] {
  const flagged = new Set(
    extraction.ambiguity_flags.filter((f) => f.target === 'category').map((f) => f.category_id),
  )
  return (plan ?? [])
    .filter((entry) => flagged.has(entry.category_id))
    .map((entry) => ({
      category_id: entry.category_id,
      option: 0,
      description: taxonomyLabel(entry.taxonomy_node),
    }))
}

const WAIT_COPY: Record<R1Waiting, { quick: string; slow: string }> = {
  start: {
    quick: 'Reading your brief.',
    slow: 'Still reading. A detailed brief can take about a minute.',
  },
  answers: {
    quick: 'Deciding what to look for.',
    slow: 'Still deciding. This can take about a minute.',
  },
  retry: {
    quick: 'Picking up where it stopped.',
    slow: 'Still working. This can take about a minute.',
  },
  resume: {
    quick: 'Picking up where you left off.',
    slow: 'Still working. This can take about a minute.',
  },
}

/** One line under the heading that says what the wait is, and says so again if it drags on. */
function WaitNote({ waiting, planning = false }: { waiting: R1Waiting; planning?: boolean }) {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const id = window.setTimeout(() => setSlow(true), SLOW_AFTER_MS)
    return () => window.clearTimeout(id)
  }, [])
  const copy = WAIT_COPY[waiting]
  // While planning, the section already explains itself: only the slow notice adds anything.
  if (planning && !slow) {
    return null
  }
  return (
    <p role="status" className="m-0 px-1 text-sm text-muted-foreground">
      {slow ? copy.slow : copy.quick}
    </p>
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

function StoppedMark() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-(--fs-error)">
      <TriangleAlertIcon aria-hidden="true" className="size-3.5" />
      Stopped
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
