import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { getRun as getR1Run } from '@/features/r1-interpretation/api/r1Api'
import type { CategoryMetricPlan, ExtractionOutput } from '@/features/r1-interpretation/types/r1'
import { loadRunId as loadR1RunId } from '@/features/r1-interpretation/utils/runStorage'
import { getR2Run, retryR2Run, startR2Run } from '@/features/r2-proximity/api/r2Api'
import type { R2Result, R2RunView, StartInput } from '@/features/r2-proximity/types/r2'
import { completeSavedRun } from '@/features/r2-proximity/utils/completeSavedRun'
import {
  clearR2Run,
  loadR2Run,
  saveR2Run,
  type SavedR2Run,
} from '@/features/r2-proximity/utils/runStorage'

/** How often a running run is read. The backend asks for about two seconds. */
export const POLL_MS = 2_000
/** Backoff ceiling while the status call keeps failing. */
const POLL_MAX_MS = 10_000
/** After this long the waiting line says it is still going, so it never looks frozen. */
export const SLOW_AFTER_MS = 120_000
/** Consecutive failed reads before the page says the connection is the problem. */
const FAILS_BEFORE_NOTICE = 3

export type R2Phase = 'setup' | 'starting' | 'running' | 'finished' | 'failed'

export type R2Notice =
  /** The run stopped and Retry is allowed (`retryable` true). */
  | { kind: 'failed_retryable' }
  /** The run stopped for good: start a new one. */
  | { kind: 'failed_final' }
  /** The run (or the R1 run it needs) does not exist for this user. */
  | { kind: 'not_found' }
  /** Reads keep failing; polling continues in the background. */
  | { kind: 'connection' }
  /** A start or retry call could not be made (store down, timeout, network). */
  | { kind: 'unavailable' }

export type R1Context = { plan: CategoryMetricPlan[] | null; extraction: ExtractionOutput | null }

type Options = { onUnauthenticated?: () => void }

export function useR2Run({ onUnauthenticated }: Options = {}) {
  const [params, setParams] = useSearchParams()
  const [phase, setPhase] = useState<R2Phase>('setup')
  const [saved, setSavedState] = useState<SavedR2Run | null>(null)
  /** The saved run as of now, for callbacks that must not change identity when it does. */
  const savedRef = useRef<SavedR2Run | null>(null)
  const setSaved = useCallback((run: SavedR2Run | null) => {
    savedRef.current = run
    setSavedState(run)
  }, [])
  const [view, setView] = useState<R2RunView | null>(null)
  const [notice, setNotice] = useState<R2Notice | null>(null)
  const [rejected, setRejected] = useState<string | null>(null)
  const [slow, setSlow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [r1, setR1] = useState<R1Context | null>(null)
  /** The R1 run a new search starts from: Home's, or else the one this run's responses name. */
  const [r1RunId, setR1RunId] = useState<string | null>(() => loadR1RunId())

  /** Bumped on every new start, retry or reset; responses for an older token are ignored. */
  const token = useRef(0)
  const timer = useRef<number | null>(null)
  const slowTimer = useRef<number | null>(null)
  const unauth = useRef(onUnauthenticated)
  useEffect(() => {
    unauth.current = onUnauthenticated
  })

  const stopTimers = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    if (slowTimer.current !== null) window.clearTimeout(slowTimer.current)
    timer.current = null
    slowTimer.current = null
  }, [])

  const toSetup = useCallback(
    (next: R2Notice | null) => {
      token.current++
      stopTimers()
      clearR2Run()
      setSaved(null)
      setView(null)
      setSlow(false)
      setPhase('setup')
      setNotice(next)
      setParams({}, { replace: true })
    },
    [setParams, setSaved, stopTimers],
  )

  /**
   * Applies a run view: the status alone decides the phase. Every response also names the run's
   * R1 run, origin and radius; a run opened from a link in another tab takes them from here.
   */
  const apply = useCallback(
    (v: R2RunView) => {
      const current = savedRef.current
      if (current) {
        const completed = completeSavedRun(current, v)
        if (completed !== current) {
          setSaved(completed)
          saveR2Run(completed)
        }
      }
      // Kept beyond this run, so "Start a new search" in a tab opened from a link has a plan.
      if (v.r1RunId) setR1RunId((known) => known || v.r1RunId)
      setView(v)
      if (v.status === 'running') {
        setPhase('running')
        return
      }
      stopTimers()
      setSlow(false)
      if (v.status === 'finished') {
        setPhase('finished')
        setNotice(null)
      } else {
        setPhase('failed')
        setNotice({ kind: v.retryable ? 'failed_retryable' : 'failed_final' })
      }
    },
    [setSaved, stopTimers],
  )

  const poll = useCallback(
    function tick(runId: string, my: number, fails = 0) {
      const delay = fails === 0 ? POLL_MS : Math.min(POLL_MS * 2 ** fails, POLL_MAX_MS)
      timer.current = window.setTimeout(async () => {
        const res = await getR2Run(runId)
        if (my !== token.current) return
        if (res.ok) {
          setNotice((n) => (n?.kind === 'connection' ? null : n))
          apply(res.view)
          if (res.view.status === 'running') tick(runId, my, 0)
          return
        }
        switch (res.error.kind) {
          case 'unauthenticated':
            stopTimers()
            unauth.current?.()
            return
          case 'not_found':
            toSetup({ kind: 'not_found' })
            return
          default:
            if (fails + 1 >= FAILS_BEFORE_NOTICE) setNotice({ kind: 'connection' })
            tick(runId, my, fails + 1)
        }
      }, delay)
    },
    [apply, stopTimers, toSetup],
  )

  /** Enters the running phase for a run and starts reading it. */
  const follow = useCallback(
    (run: SavedR2Run, first: R2RunView | null) => {
      const my = ++token.current
      stopTimers()
      setSaved(run)
      saveR2Run(run)
      setParams({ run: run.runId }, { replace: true })
      setSlow(false)
      slowTimer.current = window.setTimeout(() => {
        if (my === token.current) setSlow(true)
      }, SLOW_AFTER_MS)
      if (first) {
        apply(first)
        if (first.status === 'running') poll(run.runId, my)
      } else {
        setPhase('running')
        // A restored run: read it at once rather than after a poll interval.
        void getR2Run(run.runId).then((res) => {
          if (my !== token.current) return
          if (res.ok) {
            apply(res.view)
            if (res.view.status === 'running') poll(run.runId, my)
          } else if (res.error.kind === 'not_found') {
            toSetup({ kind: 'not_found' })
          } else if (res.error.kind === 'unauthenticated') {
            unauth.current?.()
          } else {
            poll(run.runId, my, 1)
          }
        })
      }
    },
    [apply, poll, setParams, setSaved, stopTimers, toSetup],
  )

  // Restore on load: the URL names the run; storage carries the R1 run, origin and radius.
  useEffect(() => {
    const urlRun = params.get('run')
    const stored = loadR2Run()
    // State is synced from the URL and sessionStorage, which only exist outside React.
    if (urlRun && stored?.runId === urlRun) {
      follow(stored, null)
    } else if (urlRun) {
      // Opened from a link in another tab: nothing is known yet but the run. Its first response
      // names the R1 run, origin and radius, and apply() fills them in (completeSavedRun).
      follow({ runId: urlRun, r1RunId: '', latitude: NaN, longitude: NaN, radiusKm: NaN }, null)
    } else if (stored) {
      follow(stored, null)
    }
    return () => {
      // Deliberately the live ref: a response for any run started before unmount must be dropped.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      token.current++
      stopTimers()
    }
    // Runs once on mount; later changes come from the actions below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The R1 run gives the category order, the renter's words and the empty categories.
  const r1Id = saved?.r1RunId || r1RunId
  useEffect(() => {
    if (!r1Id) return
    let live = true
    void getR1Run(r1Id).then((res) => {
      if (live && res.ok) setR1({ plan: res.view.plan, extraction: res.view.extraction })
    })
    return () => {
      live = false
    }
  }, [r1Id])

  const handleCallError = useCallback(
    (res: Extract<R2Result, { ok: false }>) => {
      switch (res.error.kind) {
        case 'unauthenticated':
          unauth.current?.()
          return
        case 'rejected':
          setRejected(res.error.message || 'The location or radius was not accepted.')
          return
        case 'not_found':
          toSetup({ kind: 'not_found' })
          return
        default:
          setNotice({ kind: 'unavailable' })
      }
    },
    [toSetup],
  )

  const start = useCallback(
    async (input: StartInput) => {
      if (busy) return
      setBusy(true)
      setRejected(null)
      setNotice(null)
      setPhase('starting')
      const my = ++token.current
      const res = await startR2Run(input)
      setBusy(false)
      if (my !== token.current) return
      if (res.ok) {
        follow({ ...input, runId: res.view.runId }, res.view)
      } else {
        setPhase('setup')
        handleCallError(res)
      }
    },
    [busy, follow, handleCallError],
  )

  const retry = useCallback(async () => {
    if (busy || !saved) return
    setBusy(true)
    const my = ++token.current
    const res = await retryR2Run(saved.runId)
    setBusy(false)
    if (my !== token.current) return
    if (res.ok) {
      setNotice(null)
      follow(saved, res.view)
      return
    }
    if (res.error.kind === 'conflict') {
      // Not retryable now (already running, finished, or its one retry used): show what it is.
      const now = await getR2Run(saved.runId)
      if (now.ok) follow(saved, now.view)
      else handleCallError(now)
      return
    }
    handleCallError(res)
  }, [busy, follow, handleCallError, saved])

  const startAgain = useCallback(() => toSetup(null), [toSetup])

  return {
    phase,
    view,
    saved,
    notice,
    rejected,
    slow,
    busy,
    r1,
    /** The R1 run a new search would start from (Home's in this tab, else the run's own). */
    r1RunId: saved?.r1RunId || r1RunId,
    start,
    retry,
    startAgain,
  }
}
