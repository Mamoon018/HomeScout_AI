/**
 * The live R3 run behind /places_metrics: start, poll, retry, restore on refresh, and the R1/R2
 * context its result is joined with.
 *
 * Showing a run follows the run's own chain by id (R3 body → its R2 run → that run's R1 run) and
 * never reads tab storage; "the last R2 run in this tab" is used only to start a new run.
 *
 * Every phase is entered by a real event (a request starting, a response, a status, a poll
 * result, a user action); nothing pretends to know progress the backend does not report.
 *
 *   setup     ─ Start ─────────────▶ starting ─ 202 running ─▶ running (polling)
 *   starting  ─ 404 / 4xx / 5xx ───▶ setup + notice
 *   running   ─ poll: finished ────▶ finished (walks R3 → R2 → R1, then shows the result)
 *   running   ─ poll: failed ──────▶ failed + Retry (retryable) or Start again
 *   failed    ─ Retry → 202 ───────▶ running;  Retry → 409 → re-read status and show it
 *   any       ─ Start again ───────▶ setup (?run= cleared)
 *   any       ─ 404 on read ───────▶ setup + "not found";  401 → onUnauthenticated
 *   mount     ─ ?run= ─────────────▶ running (read at once, then as its status says)
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { getRun as getR1Run } from '@/features/r1-interpretation/api/r1Api'
import { getR2Run } from '@/features/r2-proximity/api/r2Api'
import { loadR2Run } from '@/features/r2-proximity/utils/runStorage'
import { getR3Run, retryR3Run, startR3Run } from '@/features/places-metrics/api/r3Api'
import type { PlacesMetricsResult } from '@/features/places-metrics/types/placesMetrics'
import type { R3Result, R3RunView } from '@/features/places-metrics/types/r3Run'
import { buildPlacesMetrics, type PlacesMetricsContext } from '@/features/places-metrics/utils/buildPlacesMetrics'

/** How often a running run is read. The run takes minutes, so a calm interval is enough. */
export const POLL_MS = 4_000
/** Backoff ceiling while the status call keeps failing. */
const POLL_MAX_MS = 20_000
/** After this long the waiting panel says it is still going, so it never looks frozen. */
export const SLOW_AFTER_MS = 4 * 60_000
/** Consecutive failed reads before the page says the connection is the problem. */
const FAILS_BEFORE_NOTICE = 3

export type R3Phase = 'setup' | 'starting' | 'running' | 'finished' | 'failed'

/** Which progress step is current. `writing` = finished, walking the R2/R1 chain. */
export type R3Step = 'websites' | 'research' | 'writing'

export type R3Notice =
  | { kind: 'failed_retryable' }
  | { kind: 'failed_final' }
  /** The R3 run does not exist for this user. */
  | { kind: 'not_found' }
  /** Start refused: no finished amenity search behind the saved R2 run. */
  | { kind: 'r2_missing' }
  /** Reads keep failing; polling continues. */
  | { kind: 'connection' }
  /** A start or retry call could not be made (store down, timeout, network, refused). */
  | { kind: 'unavailable' }
  /** The run finished but its places (R2) or its questions (R1) could not be loaded. */
  | { kind: 'context' }
  /** A body in the chain did not name its parent run, so nothing more is requested. */
  | { kind: 'chain_missing' }

type Options = { onUnauthenticated?: () => void }

export function useR3Run({ onUnauthenticated }: Options = {}) {
  const [params, setParams] = useSearchParams()
  const [phase, setPhase] = useState<R3Phase>('setup')
  /** The run on screen; the address bar (`?run=`) is its only other copy. */
  const [runId, setRunId] = useState<string | null>(null)
  const [view, setView] = useState<R3RunView | null>(null)
  const [result, setResult] = useState<PlacesMetricsResult | null>(null)
  const [notice, setNotice] = useState<R3Notice | null>(null)
  const [slow, setSlow] = useState(false)
  const [busy, setBusy] = useState(false)
  /** The finished amenity search a new run would start from (the last one in this tab). */
  const [r2RunId] = useState<string | null>(() => loadR2Run()?.runId ?? null)

  /** Bumped on every new start, retry, reset or unmount; responses for an older token are dropped. */
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
    (next: R3Notice | null) => {
      token.current++
      stopTimers()
      setRunId(null)
      setView(null)
      setResult(null)
      setSlow(false)
      setPhase('setup')
      setNotice(next)
      setParams({}, { replace: true })
    },
    [setParams, stopTimers],
  )

  /**
   * Joins a finished run with its own places and questions by following the chain: the R3 body
   * names its R2 run, whose body names its R1 run. Each step waits for the one before (its id is
   * in that reply). No id means no call: the page stops with a notice and never falls back to tab
   * storage. Every reply is checked against the token, so a late reply for an older run is dropped.
   */
  const walkChain = useCallback(async (finished: R3RunView, my: number) => {
    setNotice(null)
    if (!finished.r2RunId) {
      setNotice({ kind: 'chain_missing' })
      return
    }
    const r2 = await getR2Run(finished.r2RunId)
    if (my !== token.current) return
    if (!r2.ok && r2.error.kind === 'unauthenticated') {
      unauth.current?.()
      return
    }
    if (!r2.ok || !r2.view.result) {
      setNotice({ kind: 'context' })
      return
    }
    if (!r2.view.r1RunId) {
      setNotice({ kind: 'chain_missing' })
      return
    }
    const r1 = await getR1Run(r2.view.r1RunId)
    if (my !== token.current) return
    if (!r1.ok && r1.error.kind === 'unauthenticated') {
      unauth.current?.()
      return
    }
    // Strict: without R1 the questions would be worded differently, with no sign anything changed.
    if (!r1.ok) {
      setNotice({ kind: 'context' })
      return
    }
    const ctx: PlacesMetricsContext = {
      plan: r1.view.plan,
      askedIds: r1.view.extraction ? new Set(r1.view.extraction.explicit_categories.map((c) => c.category_id)) : null,
      r2: r2.view.result,
      origin: r2.view.origin,
    }
    setResult(buildPlacesMetrics(finished.result ?? [], ctx))
  }, [])

  /** Applies a run view: the status alone decides the phase. */
  const apply = useCallback(
    (v: R3RunView, my: number) => {
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
        void walkChain(v, my)
      } else {
        setPhase('failed')
        setNotice({ kind: v.retryable ? 'failed_retryable' : 'failed_final' })
      }
    },
    [walkChain, stopTimers],
  )

  const poll = useCallback(
    function tick(id: string, my: number, fails = 0) {
      const delay = fails === 0 ? POLL_MS : Math.min(POLL_MS * 2 ** fails, POLL_MAX_MS)
      timer.current = window.setTimeout(async () => {
        const res = await getR3Run(id)
        if (my !== token.current) return
        if (res.ok) {
          setNotice((n) => (n?.kind === 'connection' ? null : n))
          apply(res.view, my)
          if (res.view.status === 'running') tick(id, my, 0)
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
            tick(id, my, fails + 1)
        }
      }, delay)
    },
    [apply, stopTimers, toSetup],
  )

  /** Follows a run: puts it in the address bar, then applies its first view or reads it at once. */
  const follow = useCallback(
    (id: string, first: R3RunView | null) => {
      const my = ++token.current
      stopTimers()
      setRunId(id)
      setResult(null)
      setParams({ run: id }, { replace: true })
      setSlow(false)
      slowTimer.current = window.setTimeout(() => {
        if (my === token.current) setSlow(true)
      }, SLOW_AFTER_MS)
      if (first) {
        apply(first, my)
        if (first.status === 'running') poll(id, my)
        return
      }
      setPhase('running')
      void getR3Run(id).then((res) => {
        if (my !== token.current) return
        if (res.ok) {
          apply(res.view, my)
          if (res.view.status === 'running') poll(id, my)
        } else if (res.error.kind === 'not_found') {
          toSetup({ kind: 'not_found' })
        } else if (res.error.kind === 'unauthenticated') {
          unauth.current?.()
        } else {
          poll(id, my, 1)
        }
      })
    },
    [apply, poll, setParams, stopTimers, toSetup],
  )

  // Restore on load: the address bar is the only source; the run's body names its own parents.
  useEffect(() => {
    const urlRun = params.get('run')
    if (urlRun) follow(urlRun, null)
    return () => {
      // The live ref on purpose: any response for a run started before unmount must be dropped.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      token.current++
      stopTimers()
    }
    // Runs once on mount; later changes come from the actions below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const callFailed = useCallback(
    (res: Extract<R3Result, { ok: false }>, onStart: boolean) => {
      switch (res.error.kind) {
        case 'unauthenticated':
          unauth.current?.()
          return
        case 'not_found':
          if (onStart) setNotice({ kind: 'r2_missing' })
          else toSetup({ kind: 'not_found' })
          return
        default:
          setNotice({ kind: 'unavailable' })
      }
    },
    [toSetup],
  )

  const start = useCallback(async () => {
    if (busy || !r2RunId) return
    setBusy(true)
    setNotice(null)
    setPhase('starting')
    const my = ++token.current
    const res = await startR3Run(r2RunId)
    setBusy(false)
    if (my !== token.current) return
    if (res.ok) {
      follow(res.view.runId, res.view)
    } else {
      setPhase('setup')
      callFailed(res, true)
    }
  }, [busy, callFailed, follow, r2RunId])

  const retry = useCallback(async () => {
    if (busy || !runId) return
    setBusy(true)
    const my = ++token.current
    const res = await retryR3Run(runId)
    setBusy(false)
    if (my !== token.current) return
    if (res.ok) {
      setNotice(null)
      follow(runId, res.view)
      return
    }
    if (res.error.kind === 'conflict') {
      // Not retryable now (running, finished, or its one retry used): show what it is.
      const now = await getR3Run(runId)
      if (my !== token.current) return
      if (now.ok) follow(runId, now.view)
      else callFailed(now, false)
      return
    }
    callFailed(res, false)
  }, [busy, callFailed, follow, runId])

  /** Re-walks the finished run's chain (its places and questions) after a failed load. */
  const reloadContext = useCallback(() => {
    if (!view || view.status !== 'finished') return
    void walkChain(view, token.current)
  }, [walkChain, view])

  const startAgain = useCallback(() => toSetup(null), [toSetup])

  const step: R3Step = phase === 'finished' ? 'writing' : view?.completedStep === 'discovery_batch' ? 'research' : 'websites'

  return {
    phase,
    step,
    result,
    notice,
    slow,
    busy,
    /** True when this tab has an amenity search a new run can start from. */
    canStart: r2RunId !== null,
    start,
    retry,
    startAgain,
    reloadContext,
  }
}
