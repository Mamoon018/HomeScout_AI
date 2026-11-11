import { useCallback, useEffect, useRef, useState } from 'react'

import { RUN_TIMING, STEP_COUNT } from '@/features/search-progress/utils/searchSteps'

export type HeadingState = 'shown' | 'fading' | 'hidden'

export type SearchRunState = {
  /** P1 welcome heading: fades once on the first run and never comes back. */
  headingState: HeadingState
  /** P2 composer has moved to the top of the content area. */
  movedUp: boolean
  /** P2 composer is read-only while a run is in progress. */
  locked: boolean
  timelineVisible: boolean
  /** -1 = all pending, 0..4 = active step, STEP_COUNT = all completed. */
  activeStep: number
  resultVisible: boolean
  /** Result and map are fading out before a re-run starts. */
  resetting: boolean
}

const INITIAL_STATE: SearchRunState = {
  headingState: 'shown',
  movedUp: false,
  locked: false,
  timelineVisible: false,
  activeStep: -1,
  resultVisible: false,
  resetting: false,
}

/**
 * Drives the dummy search run: intro (heading fade, composer move), then each
 * step active for 3s, then the result. Replace the timers with real progress
 * events once the backend reports them.
 */
export function useSearchRun() {
  const [state, setState] = useState<SearchRunState>(INITIAL_STATE)
  const timersRef = useRef<number[]>([])
  const stateRef = useRef(state)

  useEffect(() => {
    stateRef.current = state
  }, [state])

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  const at = useCallback((delay: number, patch: Partial<SearchRunState>) => {
    const id = window.setTimeout(() => setState((prev) => ({ ...prev, ...patch })), delay)
    timersRef.current.push(id)
  }, [])

  const scheduleSteps = useCallback(
    (startAt: number) => {
      at(startAt, { timelineVisible: true, activeStep: 0 })
      for (let step = 1; step < STEP_COUNT; step += 1) {
        at(startAt + step * RUN_TIMING.stepDuration, { activeStep: step })
      }
      at(startAt + STEP_COUNT * RUN_TIMING.stepDuration, {
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
      scheduleSteps(RUN_TIMING.headingFade + RUN_TIMING.composerMove)
      return
    }

    // Re-run: fade out result + map, reset every step to pending, restart.
    setState((prev) => ({ ...prev, locked: true, resetting: true }))
    at(RUN_TIMING.resetFade, { resetting: false, resultVisible: false, activeStep: -1 })
    scheduleSteps(RUN_TIMING.resetFade + RUN_TIMING.resetSettle)
  }, [at, clearTimers, scheduleSteps])

  useEffect(() => clearTimers, [clearTimers])

  return { ...state, start }
}
