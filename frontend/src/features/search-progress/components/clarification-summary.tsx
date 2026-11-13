import { CheckIcon } from 'lucide-react'

import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'

import './clarification.css'

type ClarificationSummaryProps = {
  questions: ClarificationQuestion[]
  answers: ClarificationAnswer[]
}

/** What the renter cleared up: their own phrase, wired to what they meant by it. */
export function ClarificationSummary({ questions, answers }: ClarificationSummaryProps) {
  const rows = questions.flatMap((q) => {
    const answer = answers.find((a) => a.category_id === q.category_id)
    return answer ? [{ id: q.category_id, category: q.category, meaning: answer.description }] : []
  })

  return (
    <section
      aria-label="Cleared up"
      className="animate-in fade-in-0 duration-200 motion-reduce:animate-none"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="m-0 text-sm font-semibold text-Brand-500">Cleared up</h3>
        <span className="text-xs font-medium text-muted-foreground tabular-nums">
          {rows.length} of {questions.length}
        </span>
      </div>
      <ul className="m-0 mt-3 flex list-none flex-col gap-3 p-0">
        {rows.map((row, i) => (
          <li
            key={row.id}
            className="cl-row grid grid-cols-[20px_minmax(0,1fr)] gap-x-3"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <span
              aria-hidden="true"
              className="mt-px grid size-5 place-items-center rounded-full border-[1.5px] border-Status-Success text-Status-Success"
            >
              <CheckIcon className="size-3" strokeWidth={3} />
            </span>
            <div className="min-w-0">
              <p className="m-0 truncate text-xs leading-5 text-muted-foreground">{row.category}</p>
              <div className="flex items-start gap-1.5">
                <ElbowWire delay={i * 60 + 250} />
                <p className="m-0 line-clamp-2 min-w-0 text-sm leading-snug text-foreground">
                  {row.meaning}
                </p>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Small wheat wire from the renter's phrase down to its meaning, with one travelling light. */
function ElbowWire({ delay }: { delay: number }) {
  return (
    <span aria-hidden="true" className="relative -mt-0.5 h-4 w-3.5 shrink-0">
      <svg viewBox="0 0 14 16" className="size-full overflow-visible" fill="none">
        <path
          d="M1 0 V7 Q1 11 5 11 H12"
          stroke="rgba(94,107,56,0.7)"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <path
          d="M9.5 8.5 L12.5 11 L9.5 13.5"
          stroke="rgba(94,107,56,0.7)"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="cl-spark" style={{ animationDelay: `${delay}ms` }} />
    </span>
  )
}
