import { useEffect, useRef, useState } from 'react'

/**
 * One loop, 13 phases (about 19.8 s):
 * even phases 0–10 = the light travels wire 0–5, odd phases 1–11 = card 0–5 runs,
 * phase 12 = all done.
 */
export const PHASE_DURATIONS = [500, 1800, 1100, 1800, 1100, 1800, 1100, 1800, 1100, 1800, 1100, 1800, 2200] as const
export const ALL_DONE_PHASE = 12

/** Snapshot shown when motion is reduced: cards 1–2 done, card 3 running. */
export const STATIC_PHASE = 5

export type CardState = 'queued' | 'running' | 'done'
export type WireState = 'ahead' | 'carrying' | 'traveled'

export function cardState(phase: number, card: number): CardState {
  if (phase === ALL_DONE_PHASE || phase > 2 * card + 1) return 'done'
  return phase === 2 * card + 1 ? 'running' : 'queued'
}

export function wireState(phase: number, wire: number): WireState {
  if (phase === 2 * wire) return 'carrying'
  return phase > 2 * wire ? 'traveled' : 'ahead'
}

/** The wire the light is on right now, or null while a card is running. */
export function travelingWire(phase: number): number | null {
  return phase < ALL_DONE_PHASE && phase % 2 === 0 ? phase / 2 : null
}

export function isNodeLit(phase: number) {
  return phase === 0 || phase === ALL_DONE_PHASE
}

/**
 * Advances the phase with a setTimeout chain. Pausing keeps the time left in
 * the current phase, so the light resumes where it stopped instead of jumping.
 */
export function useAgentLoop({ playing, initialPhase = 0 }: { playing: boolean; initialPhase?: number }) {
  const [phase, setPhase] = useState(initialPhase)
  const remainingRef = useRef<number>(PHASE_DURATIONS[initialPhase])

  useEffect(() => {
    if (!playing) return
    const startedAt = performance.now()
    const remaining = remainingRef.current
    let fired = false

    const timer = window.setTimeout(() => {
      fired = true
      const next = (phase + 1) % PHASE_DURATIONS.length
      remainingRef.current = PHASE_DURATIONS[next]
      setPhase(next)
    }, remaining)

    return () => {
      window.clearTimeout(timer)
      if (!fired) {
        remainingRef.current = Math.max(0, remaining - (performance.now() - startedAt))
      }
    }
  }, [playing, phase])

  return phase
}
