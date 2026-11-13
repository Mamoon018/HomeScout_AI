import { useCallback, useEffect, useRef, useState } from 'react'

import {
  CLARITY_STEP_INDEX,
  RUN_TIMING,
  STEP_COUNT,
} from '@/features/search-progress/utils/searchSteps'
import type {
  ClarificationAnswer,
  ClarificationPhase,
  ClarificationQuestion,
} from '@/features/search-progress/types/clarification'

export type HeadingState = 'shown' | 'fading' | 'hidden'

export type SearchRunState = {
  /** P1 welcome heading: fades once on the first run and never comes back. */
  headingState: HeadingState
  /** P2 composer has moved to the top of the content area. */
  movedUp: boolean
  /** P2 composer is read-only while a run is in progress. */
  locked: boolean
  timelineVisible: boolean
  /** -1 = all pending, 0..1 = active step, STEP_COUNT = all completed. */
  activeStep: number
  resultVisible: boolean
  /** Result and map are fading out before a re-run starts. */
  resetting: boolean
  /** none = nothing to ask · asking = run paused on the questions · answered = summary shown. */
  clarification: ClarificationPhase
  answers: ClarificationAnswer[]
}

const INITIAL_STATE: SearchRunState = {
  headingState: 'shown',
  movedUp: false,
  locked: false,
  timelineVisible: false,
  activeStep: -1,
  resultVisible: false,
  resetting: false,
  clarification: 'none',
  answers: [],
}

/**
 * Drives the dummy search run: intro (heading fade, composer move), then each
 * step active for 3s, then the result. When `questions` is not empty the run
 * pauses on the clarity-check step until the renter answers them. Replace the
 * timers with real progress events once the backend reports them.
 */
export function useSearchRun(questions: ClarificationQuestion[] = []) {
  const [state, setState] = useState<SearchRunState>(INITIAL_STATE)
  const timersRef = useRef<number[]>([])
  const stateRef = useRef(state)
  const questionsRef = useRef(questions)

  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    questionsRef.current = questions
  }, [questions])

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  const at = useCallback((delay: number, patch: Partial<SearchRunState>) => {
    const id = window.setTimeout(() => setState((prev) => ({ ...prev, ...patch })), delay)
    timersRef.current.push(id)
  }, [])

  /**
   * Schedules steps `fromStep`..last, `fromStep` landing at `startAt`. With questions to ask,
   * the run stops on the clarity-check step and waits for `submitAnswers`.
   */
  const scheduleFrom = useCallback(
    (fromStep: number, startAt: number) => {
      for (let step = fromStep; step < STEP_COUNT; step += 1) {
        const when = startAt + (step - fromStep) * RUN_TIMING.stepDuration
        if (step === CLARITY_STEP_INDEX && questionsRef.current.length > 0) {
          at(when, { timelineVisible: true, activeStep: step, clarification: 'asking' })
          return
        }
        at(when, { timelineVisible: true, activeStep: step })
      }
      at(startAt + (STEP_COUNT - fromStep) * RUN_TIMING.stepDuration, {
        activeStep: STEP_COUNT,
        resultVisible: true,
        locked: false,
      })
    },
    [at],
  )

  const start = useCallback(() => {
    const current = stateRef.current
    if (current.locked) {
      return
    }
    clearTimers()

    if (!current.movedUp) {
      // First run: fade the heading, move the composer up, then show the timeline.
      setState((prev) => ({ ...prev, headingState: 'fading', locked: true }))
      at(RUN_TIMING.headingFade, { headingState: 'hidden', movedUp: true })
      scheduleFrom(0, RUN_TIMING.headingFade + RUN_TIMING.composerMove)
      return
    }

    // Re-run: fade out result + previews, reset every step to pending, restart.
    setState((prev) => ({ ...prev, locked: true, resetting: true }))
    at(RUN_TIMING.resetFade, {
      resetting: false,
      resultVisible: false,
      activeStep: -1,
      clarification: 'none',
      answers: [],
    })
    scheduleFrom(0, RUN_TIMING.resetFade + RUN_TIMING.resetSettle)
  }, [at, clearTimers, scheduleFrom])

  /** The renter finished the questions: the clarity step completes and the run moves on. */
  const submitAnswers = useCallback(
    async (answers: ClarificationAnswer[]) => {
      if (stateRef.current.clarification !== 'asking') {
        return
      }
      setState((prev) => ({
        ...prev,
        clarification: 'answered',
        answers,
        activeStep: CLARITY_STEP_INDEX + 1,
      }))
      scheduleFrom(CLARITY_STEP_INDEX + 2, RUN_TIMING.stepDuration)
    },
    [scheduleFrom],
  )

  useEffect(() => clearTimers, [clearTimers])

  return { ...state, start, submitAnswers }
}
