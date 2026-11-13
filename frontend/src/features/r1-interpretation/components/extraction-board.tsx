import { useState, type CSSProperties, type ReactNode } from 'react'
import { CheckIcon, CircleHelpIcon, ListChecksIcon, QuoteIcon, type LucideIcon } from 'lucide-react'

import { PersonaPanel } from '@/features/r1-interpretation/components/persona-panel'
import { QuestionSection } from '@/features/r1-interpretation/components/question-section'
import type {
  AmbiguityFlag,
  ExtractionOutput,
  R1Phase,
} from '@/features/r1-interpretation/types/r1'
import { PlaceGrid } from '@/features/r1-interpretation/components/place-grid'
import { familyOf } from '@/features/r1-interpretation/utils/place-layout'
import { R1_TIMING } from '@/features/r1-interpretation/utils/timing'
import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'
import { cn } from '@/lib/utils'

import './r1.css'

type ExtractionBoardProps = {
  data: ExtractionOutput
  phase: R1Phase
  questions: ClarificationQuestion[]
  /** Changes each time the run asks, so a card that stuck on "sending" starts fresh. */
  asked: number
  answers: ClarificationAnswer[]
  onSubmitAnswers: (answers: ClarificationAnswer[]) => Promise<void> | void
}

/** Identity colours: used for the tile, the count and the live dot only. */
const COLOR = {
  asked: 'var(--color-Step-4)',
  unsure: 'var(--color-Step-2)',
} as const

/**
 * The three readings of the brief, side by side: who the renter is, what they asked for,
 * and what R1 could not pin down. They share one glass language and differ only in the
 * identity colour of their tile, so the eye compares them instead of decoding them.
 */
export function ExtractionBoard({
  data,
  phase,
  questions,
  asked,
  answers,
  onSubmitAnswers,
}: ExtractionBoardProps) {
  // Hovering or focusing a flagged phrase lights up the category it belongs to.
  const [linkedId, setLinkedId] = useState<number | null>(null)
  const streaming = phase === 'extracting'
  const asking = phase === 'asking'
  const answerFor = (id: number | null) => answers.find((a) => a.category_id === id)

  const personaDelay = 0
  const askedDelay = 140
  const unsureDelay = 280
  const rowDelay = (base: number, i: number) => base + 260 + i * R1_TIMING.rowStagger

  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-4">
      <PersonaPanel
        facts={data.persona_facts}
        delay={personaDelay}
        rowDelay={(i) => rowDelay(personaDelay, i)}
      />

      {/* Not sure yet, and the question it leads to */}
      <div className="flex flex-col">
        <Panel
          icon={CircleHelpIcon}
          color={COLOR.unsure}
          title="Not sure yet"
          hint="Things I couldn't pin down"
          count={data.ambiguity_flags.length}
          delay={unsureDelay}
          live={asking}
        >
          {data.ambiguity_flags.length === 0 ? (
            <p
              className="r1-pull m-0 flex items-center gap-2 text-sm leading-6 text-foreground"
              style={{ '--d': `${rowDelay(unsureDelay, 0)}ms` } as CSSProperties}
            >
              <span
                aria-hidden="true"
                className="grid size-5 shrink-0 place-items-center rounded-full border-[1.5px] border-Status-Success text-Status-Success"
              >
                <CheckIcon className="size-3" strokeWidth={3} />
              </span>
              Everything you wrote was clear.
            </p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {data.ambiguity_flags.map((flag, i) => (
                <FlagRow
                  key={`${i}-${flag.category_id}-${flag.phrase}`}
                  flag={flag}
                  meaning={answerFor(flag.category_id)?.description}
                  asking={asking}
                  delay={rowDelay(unsureDelay, i)}
                  onLink={setLinkedId}
                />
              ))}
            </ul>
          )}
        </Panel>

        {questions.length > 0 && (phase === 'asking' || phase === 'planning' || phase === 'done') ? (
          <QuestionSection
            key={asked}
            open={asking}
            questions={questions}
            onSubmit={onSubmitAnswers}
          />
        ) : null}
      </div>

      </div>

      {/* What you asked for */}
      <Panel
        icon={ListChecksIcon}
        color={COLOR.asked}
        title="What you asked for"
        hint="Places and features you named"
        count={data.explicit_categories.length}
        delay={askedDelay}
        popCount
      >
        <PlaceGrid
          emptyText="I didn't find a place or feature in your brief."
          places={data.explicit_categories.map((category) => {
            const meaning = answerFor(category.category_id)?.description
            const flagged = data.ambiguity_flags.some((f) => f.category_id === category.category_id)
            const title = meaning ?? category.name
            return {
              id: category.category_id,
              title,
              note: meaning !== undefined ? `you wrote “${category.name}”` : undefined,
              family: familyOf(title),
              features: category.characteristics,
              status: flagged && meaning === undefined ? 'needs a closer look' : undefined,
              linked: linkedId === category.category_id,
            }
          })}
          baseDelay={askedDelay + 260}
          stagger={R1_TIMING.rowStagger * 0.67}
        />
      </Panel>

      <span className="sr-only" aria-live="polite">
        {streaming ? 'Reading your brief' : ''}
      </span>
    </div>
  )
}

export type PanelProps = {
  icon: LucideIcon
  color: string
  title: string
  hint: string
  count: number | string
  delay: number
  /** Waiting on the renter: the border and a soft ping take the identity colour. */
  live?: boolean
  /** The count pops in after the cards have settled. */
  popCount?: boolean
  children: ReactNode
}

export function Panel({ icon: Icon, color, title, hint, count, delay, live = false, popCount = false, children }: PanelProps) {
  return (
    <section
      aria-label={title}
      className={cn(
        'r1-panel rounded-[22px] border bg-Surface-Primary p-5 backdrop-blur-xl transition-[border-color,box-shadow] duration-300 ease-Easing-Out',
        live
          ? 'border-(--c) shadow-[0_6px_22px_color-mix(in_srgb,var(--c)_22%,transparent)]'
          : 'border-Border-Subtle shadow-(--fs-panel-shadow)',
      )}
      style={{ '--c': color, '--d': `${delay}ms` } as CSSProperties}
    >
      <header className="mb-3 flex items-center gap-3">
        <span
          aria-hidden="true"
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-[10px] bg-[color-mix(in_srgb,var(--c)_10%,var(--color-Surface-Secondary))] text-(--c)',
            live && 'r1-ping',
          )}
          style={{ '--r1-accent': color } as CSSProperties}
        >
          <Icon className="size-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="m-0 text-[15px] leading-5 font-semibold tracking-normal text-(--tracker-heading)">
            {title}
          </h3>
          <p className="m-0 truncate text-xs leading-5 text-muted-foreground">{hint}</p>
        </div>
        <span className={cn('shrink-0 rounded-full bg-[color-mix(in_srgb,var(--c)_10%,transparent)] px-2 py-0.5 text-xs font-semibold text-(--c) tabular-nums', popCount && 'r1-badge-pop')}>
          {count}
        </span>
      </header>
      {children}
    </section>
  )
}

type FlagRowProps = {
  flag: AmbiguityFlag
  meaning: string | undefined
  asking: boolean
  delay: number
  onLink: (categoryId: number | null) => void
}

function FlagRow({ flag, meaning, asking, delay, onLink }: FlagRowProps) {
  const resolved = meaning !== undefined
  const why =
    flag.target === 'characteristic' && flag.category
      ? `Unclear what this means for ${flag.category}.`
      : flag.target === 'persona'
        ? 'This could mean different things about your situation.'
        : 'This could point to several kinds of places.'
  return (
    <li
      className="r1-pull"
      style={{ '--d': `${delay}ms` } as CSSProperties}
      onMouseEnter={() => onLink(flag.category_id)}
      onMouseLeave={() => onLink(null)}
    >
      <p className="m-0 flex items-start gap-2 text-sm leading-6 font-semibold text-foreground">
        {resolved ? (
          <span
            aria-hidden="true"
            className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-[1.5px] border-Status-Success text-Status-Success"
          >
            <CheckIcon className="size-3" strokeWidth={3} />
          </span>
        ) : (
          <QuoteIcon aria-hidden="true" className="mt-1 size-4 shrink-0 text-Step-2" />
        )}
        <span className="min-w-0">“{flag.phrase}”</span>
      </p>
      <p className="m-0 mt-0.5 pl-7 text-xs leading-5 text-muted-foreground">
        {resolved ? (
          <>
            Cleared up: <span className="font-medium text-foreground">{meaning}</span>
          </>
        ) : asking ? (
          `${why} Pick the closest one below.`
        ) : (
          why
        )}
      </p>
    </li>
  )
}
