import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getRun,
  retryRun,
  startRun,
  submitAnswers as postAnswers,
  toWireAnswers,
} from '@/features/r1-interpretation/api/r1Api'
import type {
  CategoryMetricPlan,
  ExtractionOutput,
  R1Phase,
} from '@/features/r1-interpretation/types/r1'
import type { R1Error, RunView } from '@/features/r1-interpretation/types/run'
import { ANSWERS_REJECTED_COPY, briefRejectionCopy } from '@/features/r1-interpretation/utils/copy'
import { clearRunId, loadRunId, saveRunId } from '@/features/r1-interpretation/utils/runStorage'
import { R1_TIMING } from '@/features/r1-interpretation/utils/timing'
import {
  AnswersRejectedError,
  type ClarificationAnswer,
  type ClarificationQuestion,
} from '@/features/search-progress/types/clarification'

export type HeadingState = 'shown' | 'fading' | 'hidden'

/** What the renter is told when the run stops, and which way out each case has. */
export type R1Notice =
  /** R1 failed on the server. The run is saved; Retry is offered only while one is left. */
  | { kind: 'failed'; retryable: boolean }
  /** The page could not reach the server or could not read its answer. */
  | { kind: 'offline'; again: 'reload' | 'start' }
  /** The run no longer exists for this user. */
  | { kind: 'gone' }

/** Which call the page is waiting on, so the wait can say what is happening. */
export type R1Waiting = 'start' | 'answers' | 'retry' | 'resume'

export type R1RunState = {
  /** Welcome heading: fades on the first run and never comes back. */
  headingState: HeadingState
  /** The composer has moved to the top of the page. */
  movedUp: boolean
  /** The composer cannot send while a run is working or waiting on the renter. */
  locked: boolean
  phase: R1Phase
  /** What the renter last sent. Start again re-sends it. */
  brief: string
  answers: ClarificationAnswer[]
  /** The breakdown and result fade out before a re-run starts. */
  resetting: boolean
  runId: string | null
  /** The extraction output; null until the run has saved that step. */
  extraction: ExtractionOutput | null
  questions: ClarificationQuestion[]
  /** Counts each time the run asks, so a card that stuck on "sending" starts fresh. */
  asked: number
  plan: CategoryMetricPlan[] | null
  /** Set while the run is stopped and the renter has to choose what to do. */
  notice: R1Notice | null
  /** The server's reason for refusing the brief, shown at the composer. */
  composerError: string | null
  waiting: R1Waiting | null
}

const INITIAL_STATE: R1RunState = {
  headingState: 'shown',
  movedUp: false,
  locked: false,
  phase: 'idle',
  brief: '',
  answers: [],
  resetting: false,
  runId: null,
  extraction: null,
  questions: [],
  asked: 0,
  plan: null,
  notice: null,
  composerError: null,
  waiting: null,
}

/** A running run is read again this often until it settles. */
const POLL_MS = 3000
/** The server marks a run it lost track of as failed after 3 minutes; stop a little after. */
const MAX_POLLS = 70

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))

type Options = {
  /** Called when the session is gone (a 401 that refreshing did not fix). */
  onUnauthenticated?: () => void
}

/**
 * Drives the R1 run from the real endpoints: start, answers, retry and status. Each UI phase is
 * entered by an event of the run (a request pending, a response, a status), never by a timer.
 * Only the intro (heading fade, composer move) and the re-run fade keep their timers.
 *
 * Every call takes a sequence number; a response that arrives after a newer call began is
 * dropped, so an old answer never overwrites the screen.
 */
export function useR1Run({ onUnauthenticated }: Options = {}) {
  const [state, setState] = useState<R1RunState>(INITIAL_STATE)
  const stateRef = useRef(state)
  const timersRef = useRef<number[]>([])
  const seqRef = useRef(0)
  const aliveRef = useRef(true)
  const onUnauthenticatedRef = useRef(onUnauthenticated)

  useEffect(() => {
    onUnauthenticatedRef.current = onUnauthenticated
  }, [onUnauthenticated])

  /** Updates state and the ref together, so the next line of an async flow reads the new value. */
  const patch = useCallback((changes: Partial<R1RunState>) => {
    stateRef.current = { ...stateRef.current, ...changes }
    setState(stateRef.current)
  }, [])

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  const at = useCallback(
    (delay: number, changes: Partial<R1RunState>) => {
      timersRef.current.push(window.setTimeout(() => patch(changes), delay))
    },
    [patch],
  )

  /** A new call supersedes every call before it, including a poll in flight. */
  const begin = useCallback(() => {
    clearTimers()
    seqRef.current += 1
    return seqRef.current
  }, [clearTimers])

  const stale = (seq: number) => seq !== seqRef.current || !aliveRef.current

  const goIdle = useCallback(() => {
    clearRunId()
    patch({
      phase: 'idle',
      locked: false,
      runId: null,
      extraction: null,
      questions: [],
      plan: null,
      answers: [],
      notice: null,
      waiting: null,
    })
  }, [patch])

  /** Shows a run the way its status says. */
  function applyView(view: RunView, seq: number) {
    saveRunId(view.runId)
    const extraction = view.extraction ?? stateRef.current.extraction
    const shared = { runId: view.runId, extraction, composerError: null, notice: null, waiting: null }
    switch (view.status) {
      case 'needs_answers':
        patch({
          ...shared,
          phase: 'asking',
          questions: view.questions,
          asked: stateRef.current.asked + 1,
          plan: null,
          locked: true,
        })
        return
      case 'finished':
        patch({ ...shared, phase: 'done', plan: view.plan, locked: false })
        return
      case 'running':
        patch({
          ...shared,
          phase: extraction ? 'planning' : 'extracting',
          waiting: 'resume',
          locked: true,
        })
        poll(view.runId, seq, 0)
        return
      case 'failed':
        patch({
          ...shared,
          phase: extraction ? 'planning' : 'extracting',
          locked: false,
          notice: { kind: 'failed', retryable: view.retryable === true },
        })
        return
    }
  }

  /** Reads a running run again every few seconds until it is no longer running. */
  function poll(runId: string, seq: number, count: number) {
    timersRef.current.push(
      window.setTimeout(async () => {
        if (stale(seq)) return
        const result = await getRun(runId)
        if (stale(seq)) return
        if (!result.ok) {
          await onError(result.error, { seq, runId, from: 'read' })
          return
        }
        if (result.view.status === 'running' && count + 1 < MAX_POLLS) {
          poll(runId, seq, count + 1)
          return
        }
        if (result.view.status === 'running') {
          patch({ notice: { kind: 'offline', again: 'reload' }, waiting: null, locked: false })
          return
        }
        applyView(result.view, seq)
      }, POLL_MS),
    )
  }

  /** Reads the run's real state after a call whose outcome the page cannot be sure of. */
  async function reread(runId: string, seq: number) {
    const result = await getRun(runId)
    if (stale(seq)) return
    if (result.ok) {
      applyView(result.view, seq)
      return
    }
    // A second failure ends the loop: ask the renter instead of reading again and again.
    if (result.error.kind === 'not_found' || result.error.kind === 'unauthenticated') {
      await onError(result.error, { seq, runId, from: 'read' })
      return
    }
    patch({
      notice: { kind: 'offline', again: 'reload' },
      runId,
      waiting: null,
      locked: false,
    })
  }

  /** One place that decides what each failed call means for the screen. */
  async function onError(error: R1Error, ctx: { seq: number; runId: string | null; from: 'start' | 'answers' | 'retry' | 'read' }) {
    const { seq, runId, from } = ctx
    switch (error.kind) {
      case 'unauthenticated':
        goIdle()
        onUnauthenticatedRef.current?.()
        return
      case 'not_found':
        clearRunId()
        patch({ notice: { kind: 'gone' }, runId: null, waiting: null, locked: false })
        return
      case 'rejected':
        if (from === 'start') {
          patch({
            composerError: briefRejectionCopy(error.message),
            phase: 'idle',
            waiting: null,
            locked: false,
          })
        } else {
          patch({ notice: { kind: 'offline', again: 'reload' }, waiting: null, locked: false })
        }
        return
      case 'conflict': {
        // The run moved on (another tab, a double click): show where it really is.
        const id = error.runId ?? runId
        if (id) {
          await reread(id, seq)
        } else {
          patch({ notice: { kind: 'offline', again: 'start' }, waiting: null, locked: false })
        }
        return
      }
      case 'run_failed':
        saveRunId(error.runId)
        patch({
          runId: error.runId,
          phase: stateRef.current.extraction ? 'planning' : 'extracting',
          notice: { kind: 'failed', retryable: error.retryable },
          waiting: null,
          locked: false,
        })
        // The failed run still holds what it finished (the extraction): show it too.
        if (!stateRef.current.extraction) {
          const result = await getRun(error.runId)
          if (!stale(seq) && result.ok && result.view.status === 'failed') {
            applyView(result.view, seq)
          }
        }
        return
      case 'timeout':
      case 'network':
      case 'unavailable':
        // With a run id the server may have kept working: read it. Without one, nothing
        // was created that the page can find, so the only way on is to send the brief again.
        if (runId && from !== 'read') {
          await reread(runId, seq)
        } else {
          patch({
            notice: { kind: 'offline', again: runId ? 'reload' : 'start' },
            waiting: null,
            locked: false,
          })
        }
        return
    }
  }

  function start(submitted?: { brief?: string }) {
    const current = stateRef.current
    if (current.locked) {
      return
    }
    const brief = submitted?.brief?.trim() ?? current.brief
    if (brief === '') {
      return
    }
    const seq = begin()
    clearRunId()
    const first = !current.movedUp
    const intro = first
      ? R1_TIMING.headingFade + R1_TIMING.composerMove
      : R1_TIMING.resetFade + R1_TIMING.resetSettle

    // The request goes out at once; the intro runs beside it.
    const request = startRun(brief)
    if (first) {
      patch({ headingState: 'fading', locked: true, brief, composerError: null, notice: null })
      at(R1_TIMING.headingFade, { headingState: 'hidden', movedUp: true })
    } else {
      patch({ locked: true, resetting: true, brief, composerError: null, notice: null })
      at(R1_TIMING.resetFade, {
        resetting: false,
        phase: 'idle',
        answers: [],
        extraction: null,
        questions: [],
        plan: null,
        runId: null,
      })
    }
    at(intro, { phase: 'extracting', waiting: 'start' })

    void Promise.all([request, sleep(intro)]).then(([result]) => {
      if (stale(seq)) return
      if (result.ok) {
        applyView(result.view, seq)
      } else {
        void onError(result.error, { seq, runId: null, from: 'start' })
      }
    })
  }

  /** The renter answered every question: R1 moves on to deciding what to look for. */
  async function submitAnswers(answers: ClarificationAnswer[]) {
    const current = stateRef.current
    if (current.phase !== 'asking' || current.runId === null) {
      return
    }
    const runId = current.runId
    const seq = begin()
    patch({ answers, phase: 'planning', waiting: 'answers', notice: null })
    const result = await postAnswers(runId, toWireAnswers(answers, current.questions))
    if (stale(seq)) return
    if (result.ok) {
      applyView(result.view, seq)
      return
    }
    if (result.error.kind === 'rejected') {
      // The questions are still open: hand the message back to the card, which stays on them.
      patch({ answers: [], phase: 'asking', waiting: null })
      throw new AnswersRejectedError(ANSWERS_REJECTED_COPY)
    }
    await onError(result.error, { seq, runId, from: 'answers' })
  }

  /** Resumes a failed run at the step that failed. */
  async function retry() {
    const current = stateRef.current
    if (current.runId === null || current.notice?.kind !== 'failed' || !current.notice.retryable) {
      return
    }
    const runId = current.runId
    const seq = begin()
    patch({ notice: null, waiting: 'retry', locked: true })
    const result = await retryRun(runId)
    if (stale(seq)) return
    if (result.ok) {
      applyView(result.view, seq)
      return
    }
    await onError(result.error, { seq, runId, from: 'retry' })
  }

  /** Throws the run away and sends the same brief again; with no brief, just clears the screen. */
  function startAgain() {
    const { brief } = stateRef.current
    begin()
    patch({ notice: null, locked: false })
    if (brief === '') {
      goIdle()
      return
    }
    start({ brief })
  }

  /** Tries the read again after the page could not reach the run. */
  function reload() {
    const { runId } = stateRef.current
    if (runId === null) {
      startAgain()
      return
    }
    const seq = begin()
    patch({ notice: null, waiting: 'resume', locked: true })
    void reread(runId, seq)
  }

  const clearComposerError = useCallback(() => {
    if (stateRef.current.composerError !== null) {
      patch({ composerError: null })
    }
  }, [patch])

  // A refresh while a run was on screen: pick it up again from the status endpoint.
  useEffect(() => {
    const saved = loadRunId()
    if (saved === null) {
      return
    }
    const seq = begin()
    patch({
      headingState: 'hidden',
      movedUp: true,
      locked: true,
      phase: 'extracting',
      waiting: 'resume',
      runId: saved,
    })
    void getRun(saved).then((result) => {
      if (stale(seq)) return
      if (result.ok) {
        applyView(result.view, seq)
      } else {
        void onError(result.error, { seq, runId: saved, from: 'read' })
      }
    })
    // Once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
      clearTimers()
    }
  }, [clearTimers])

  return { ...state, start, submitAnswers, retry, startAgain, reload, clearComposerError }
}
