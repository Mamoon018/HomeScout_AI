import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { CheckIcon, Loader2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  AnswersRejectedError,
  OTHER_MAX_LENGTH,
  type ClarificationAnswer,
  type ClarificationQuestion,
} from '@/features/search-progress/types/clarification'
import { cn } from '@/lib/utils'

const FAILED_COPY = "Couldn't send your answers. Check your connection and try again."

type ClarificationCardProps = {
  questions: ClarificationQuestion[]
  /** Resolves when the answers are saved; a rejection shows the retry message. */
  onSubmit: (answers: ClarificationAnswer[]) => Promise<void> | void
}

/**
 * One question at a time. Every question is mounted in the same grid cell so the card
 * is as tall as its tallest question and Next never jumps; only the active one is
 * visible, reachable and announced.
 */
export function ClarificationCard({ questions, onSubmit }: ClarificationCardProps) {
  const baseId = useId()
  const [index, setIndex] = useState(0)
  const [picked, setPicked] = useState<Record<number, number>>({})
  const [otherText, setOtherText] = useState<Record<number, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [failed, setFailed] = useState<string | false>(false)
  const panelRefs = useRef<(HTMLDivElement | null)[]>([])
  const otherRef = useRef<HTMLInputElement>(null)

  const total = questions.length
  const current = questions[index]
  const isLast = index === total - 1
  const pickedIndex = picked[current.category_id]
  const otherIndex = current.options.length - 1
  const otherOpen = pickedIndex === otherIndex
  const canAdvance =
    pickedIndex !== undefined && (!otherOpen || (otherText[current.category_id] ?? '').trim() !== '')

  // Move focus into the question that just appeared so the keyboard stays in the flow.
  useEffect(() => {
    const panel = panelRefs.current[index]
    const target =
      panel?.querySelector<HTMLInputElement>('input[type="radio"]:checked') ??
      panel?.querySelector<HTMLInputElement>('input[type="radio"]')
    target?.focus({ preventScroll: true })
  }, [index])

  // "Other" opens a text field: focus it and keep it in view (matters above a phone keyboard).
  useEffect(() => {
    if (otherOpen) {
      otherRef.current?.focus({ preventScroll: true })
      otherRef.current?.scrollIntoView?.({ block: 'nearest' })
    }
  }, [otherOpen, index])

  function choose(optionIndex: number) {
    if (submitting) {
      return
    }
    setFailed(false)
    setPicked((prev) => ({ ...prev, [current.category_id]: optionIndex }))
  }

  function buildAnswers(): ClarificationAnswer[] {
    return questions.map((q) => {
      const chosen = picked[q.category_id]
      const isOther = chosen === q.options.length - 1
      return {
        category_id: q.category_id,
        option: chosen + 1,
        description: isOther ? (otherText[q.category_id] ?? '').trim() : q.options[chosen],
      }
    })
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canAdvance || submitting) {
      return
    }
    if (!isLast) {
      setIndex((i) => i + 1)
      return
    }
    setSubmitting(true)
    setFailed(false)
    try {
      await onSubmit(buildAnswers())
    } catch (error) {
      // Only a refusal of the answers carries its own sentence; any other failure is a connection problem.
      setFailed(error instanceof AnswersRejectedError ? error.message : FAILED_COPY)
      setSubmitting(false)
    }
  }

  // Number keys pick the matching option, except while typing in the "other" field.
  function handleKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    const target = event.target as HTMLInputElement
    if (target.tagName === 'INPUT' && target.type === 'text') {
      return
    }
    if (event.ctrlKey || event.metaKey || event.altKey) {
      return
    }
    const n = Number(event.key)
    if (Number.isInteger(n) && n >= 1 && n <= current.options.length) {
      event.preventDefault()
      choose(n - 1)
    }
  }

  return (
    <form
      aria-label="Clarification questions"
      onSubmit={handleSubmit}
      onKeyDown={handleKeyDown}
      noValidate
    >
      <div className="grid">
        {questions.map((q, qi) => {
          const active = qi === index
          const chosen = picked[q.category_id]
          const titleId = `${baseId}-title-${q.category_id}`
          return (
            <div
              key={q.category_id}
              ref={(el) => {
                panelRefs.current[qi] = el
              }}
              aria-hidden={active ? undefined : true}
              inert={!active}
              className={cn(
                'col-start-1 row-start-1 transition-[opacity,transform] duration-200 ease-Easing-Out motion-reduce:transition-none',
                active
                  ? 'translate-x-0 opacity-100'
                  : cn(
                      'pointer-events-none invisible opacity-0',
                      qi < index ? '-translate-x-2' : 'translate-x-2',
                    ),
              )}
            >
              <h3
                id={titleId}
                className="m-0 mb-3 text-base leading-snug font-semibold tracking-normal text-balance text-Brand-500"
              >
                {q.question}
              </h3>
              <div role="radiogroup" aria-labelledby={titleId} className="flex flex-col gap-2">
                {q.options.map((label, oi) => {
                  const selected = chosen === oi
                  const isOther = oi === q.options.length - 1
                  return (
                    <div key={label}>
                      <label
                        className={cn(
                          'flex min-h-11 cursor-pointer items-center gap-3 rounded-[10px] border px-3 py-2 text-sm leading-snug text-foreground transition-colors duration-200 ease-Easing-Out',
                          'has-[input:focus-visible]:ring-2 has-[input:focus-visible]:ring-Brand-500/60',
                          selected
                            ? 'border-(--fs-accent) bg-(--fs-option-selected) font-medium'
                            : 'border-(--fs-option-border) bg-(--fs-option) hover:border-(--fs-accent)',
                        )}
                      >
                        <input
                          type="radio"
                          name={`${baseId}-q-${q.category_id}`}
                          value={oi}
                          checked={selected}
                          onChange={() => choose(oi)}
                          disabled={submitting}
                          className="sr-only"
                        />
                        <span
                          aria-hidden="true"
                          className={cn(
                            'grid size-5 shrink-0 place-items-center rounded-full border text-[11px] font-semibold tabular-nums transition-colors duration-200',
                            selected
                              ? 'border-Brand-500 bg-Brand-500 text-primary-foreground'
                              : 'border-(--fs-option-border) text-muted-foreground',
                          )}
                        >
                          {selected ? <CheckIcon className="size-3" strokeWidth={3} /> : oi + 1}
                        </span>
                        <span className="min-w-0">{isOther ? 'Other' : label}</span>
                      </label>
                      {active && isOther && selected ? (
                        <input
                          ref={otherRef}
                          type="text"
                          value={otherText[q.category_id] ?? ''}
                          onChange={(e) =>
                            setOtherText((prev) => ({ ...prev, [q.category_id]: e.target.value }))
                          }
                          maxLength={OTHER_MAX_LENGTH}
                          disabled={submitting}
                          autoComplete="off"
                          aria-label={`Say what you meant by "${q.category}"`}
                          placeholder="Say it in your own words"
                          className="mt-2 h-11 w-full animate-in rounded-[10px] border border-(--fs-option-border) bg-(--fs-input) px-3 text-base text-foreground outline-none fade-in-0 slide-in-from-top-1 placeholder:text-muted-foreground/80 focus:border-Brand-500 motion-reduce:animate-none sm:text-sm"
                        />
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {failed ? (
        <p role="alert" className="mt-3 mb-0 text-sm text-red-400">
          {failed}
        </p>
      ) : null}

      <div className="mt-4 flex items-center justify-between gap-3">
        {total > 1 ? <ProgressWire total={total} current={index} /> : <span />}
        <div className="flex items-center gap-2">
          {index > 0 ? (
            <Button
              type="button"
              variant="ghost"
              disabled={submitting}
              onClick={() => setIndex((i) => i - 1)}
              className="h-10 rounded-xl px-3 text-sm text-foreground"
            >
              Back
            </Button>
          ) : null}
          <Button
            type="submit"
            disabled={!canAdvance || submitting}
            className="h-10 min-w-24 rounded-xl px-5 text-sm font-bold"
          >
            {submitting ? <Loader2Icon aria-hidden="true" className="animate-spin" /> : null}
            {isLast ? 'Submit' : 'Next'}
          </Button>
        </div>
      </div>
    </form>
  )
}

/** Mini wire: nodes joined by a 1.6px wheat line that fills as the renter moves on. */
function ProgressWire({ total, current }: { total: number; current: number }) {
  return (
    <div className="flex items-center gap-3">
      <ol aria-hidden="true" className="m-0 flex list-none items-center p-0">
        {Array.from({ length: total }, (_, i) => (
          <li key={i} className="flex items-center">
            {i > 0 ? (
              <span className="relative h-[1.6px] w-6 overflow-hidden rounded-full bg-[rgba(74,90,42,0.18)]">
                <span
                  className={cn(
                    'absolute inset-0 origin-left bg-Brand-500/80 transition-transform duration-300 ease-Easing-Out motion-reduce:transition-none',
                    i <= current ? 'scale-x-100' : 'scale-x-0',
                  )}
                />
              </span>
            ) : null}
            <span
              className={cn(
                'rounded-full transition-all duration-300 ease-Easing-Out motion-reduce:transition-none',
                i < current && 'size-2 bg-Brand-500/80',
                i === current && 'size-2.5 bg-Brand-500 shadow-[0_0_0_3px_rgba(74,90,42,0.18)]',
                i > current && 'size-2 border border-(--fs-option-border)',
              )}
            />
          </li>
        ))}
      </ol>
      <span className="text-xs font-medium whitespace-nowrap text-muted-foreground tabular-nums">
        <span className="sr-only">Question </span>
        {current + 1} of {total}
      </span>
    </div>
  )
}
