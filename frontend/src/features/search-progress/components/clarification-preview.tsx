import { useLayoutEffect, useRef } from 'react'

import { ClarificationCard } from '@/features/search-progress/components/clarification-card'
import { ClarificationSummary } from '@/features/search-progress/components/clarification-summary'
import type {
  ClarificationAnswer,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'
import { cn } from '@/lib/utils'

import './clarification.css'

export type ClarificationPreviewProps = {
  phase: 'asking' | 'answered'
  questions: ClarificationQuestion[]
  answers: ClarificationAnswer[]
  onSubmit: (answers: ClarificationAnswer[]) => Promise<void> | void
  /** Fades out before a re-run removes it. */
  leaving?: boolean
  className?: string
}

/**
 * The preview under the "clarity check" step. One shell holds both the question card and
 * the summary, so Submit reads as the card settling into a smaller one, not a swap.
 */
export function ClarificationPreview({
  phase,
  questions,
  answers,
  onSubmit,
  leaving = false,
  className,
}: ClarificationPreviewProps) {
  const clipRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  // Ease the shell between heights whenever its content grows or shrinks.
  useLayoutEffect(() => {
    const clip = clipRef.current
    const content = contentRef.current
    if (!clip || !content || typeof ResizeObserver === 'undefined') {
      return
    }
    let last = content.getBoundingClientRect().height
    const observer = new ResizeObserver(() => {
      const next = content.getBoundingClientRect().height
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      if (Math.abs(next - last) > 1 && !reduced && typeof clip.animate === 'function') {
        clip.animate(
          [
            { height: `${last}px`, overflow: 'hidden' },
            { height: `${next}px`, overflow: 'hidden' },
          ],
          { duration: 250, easing: 'cubic-bezier(0, 0, 0.2, 1)' },
        )
      }
      last = next
    })
    observer.observe(content)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      className={cn(
        'w-full rounded-2xl border border-Border-Subtle bg-(--fs-tile) transition-opacity duration-200 ease-Easing-Out',
        leaving ? 'opacity-0' : 'opacity-100',
        className,
      )}
    >
      <div ref={clipRef}>
        <div ref={contentRef} className="p-4">
          {phase === 'asking' ? (
            <ClarificationCard questions={questions} onSubmit={onSubmit} />
          ) : (
            <ClarificationSummary questions={questions} answers={answers} />
          )}
        </div>
      </div>
    </div>
  )
}
