import { useCallback, useEffect, useRef, useState } from 'react'

import type { R1Phase } from '@/features/r1-interpretation/types/r1'
import { R1_TIMING } from '@/features/r1-interpretation/utils/timing'
import type { ClarificationAnswer } from '@/features/search-progress/types/clarification'

export type HeadingState = 'shown' | 'fading' | 'hidden'

export type R1RunState = {
  /** Welcome heading: fades on the first run and never comes back. */
  headingState: HeadingState
  /** The composer has moved to the top of the page. */
  movedUp: boolean
  /** The composer is read-only while R1 is working. */
  locked: boolean
  phase: R1Phase
  /** What the renter typed, shown back to them above the breakdown. */
  brief: string
  answers: ClarificationAnswer[]
  /** The breakdown and result fade out before a re-run starts. */
  resetting: boolean
}

const INITIAL_STATE: R1RunState = {
  headingState: 'shown',
  movedUp: false,
  locked: false,
  phase: 'idle',
  brief: '',
  answers: [],
  resetting: false,
}

/**
 * Drives the dummy R1 run: intro (heading fade, composer move), extraction, an optional
 * pause for questions, planning, then the result. Replace the timers with the run view's
 * `status` (running · needs_answers · finished) once the endpoints are wired.
 */
export function useR1Run(hasQuestions: boolean) {
  const [state, setState] = useState<R1RunState>(INITIAL_STATE)
  const timersRef = useRef<number[]>([])
  const stateRef = useRef(state)
  const hasQuestionsRef = useRef(hasQuestions)

  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    hasQuestionsRef.current = hasQuestions
  }, [hasQuestions])

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  const at = useCallback((delay: number, patch: Partial<R1RunState>) => {
    const id = window.setTimeout(() => setState((prev) => ({ ...prev, ...patch })), delay)
    timersRef.current.push(id)
  }, [])

  /** Extraction → (questions →) planning → done, with `startAt` as extraction's start. */
  const schedulePipeline = useCallback(
    (startAt: number, brief: string) => {
      at(startAt, { phase: 'extracting', brief })
      const extracted = startAt + R1_TIMING.extract
      if (hasQuestionsRef.current) {
        at(extracted, { phase: 'asking' })
        return
      }
      at(extracted, { phase: 'planning' })
      at(extracted + R1_TIMING.plan, { phase: 'done', locked: false })
    },
    [at],
  )

  const start = useCallback(
    (submitted?: { brief?: string }) => {
      const current = stateRef.current
      if (current.locked) {
        return
      }
      clearTimers()
      const brief = submitted?.brief?.trim() ?? current.brief

      if (!current.movedUp) {
        setState((prev) => ({ ...prev, headingState: 'fading', locked: true, brief }))
        at(R1_TIMING.headingFade, { headingState: 'hidden', movedUp: true })
        schedulePipeline(R1_TIMING.headingFade + R1_TIMING.composerMove, brief)
        return
      }

      setState((prev) => ({ ...prev, locked: true, resetting: true }))
      at(R1_TIMING.resetFade, { resetting: false, phase: 'idle', answers: [], brief })
      schedulePipeline(R1_TIMING.resetFade + R1_TIMING.resetSettle, brief)
    },
    [at, clearTimers, schedulePipeline],
  )

  /** The renter answered every question: R1 moves on to deciding what to look for. */
  const submitAnswers = useCallback(
    async (answers: ClarificationAnswer[]) => {
      if (stateRef.current.phase !== 'asking') {
        return
      }
      setState((prev) => ({ ...prev, answers, phase: 'planning' }))
      at(R1_TIMING.plan, { phase: 'done', locked: false })
    },
    [at],
  )

  useEffect(() => clearTimers, [clearTimers])

  return { ...state, start, submitAnswers }
}
